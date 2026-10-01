"""Backup e restauracao dos dois bancos, com manifesto verificavel.

- historian: ``Connection.backup()`` paginado (a escrita ao vivo entra entre os passos);
- core: ``VACUUM INTO`` (copia compacta e consistente);
- ``manifest.json``: sha256, tamanho, versao do schema e contagem por tabela de cada arquivo,
  mais ``PRAGMA integrity_check`` em cada copia antes de assinar o manifesto;
- ``restore_all``: so com o servico parado (bancos fechados). Valida checksum e integridade de
  TODOS os arquivos antes de tocar em qualquer destino; depois copia para um arquivo temporario
  ao lado e troca com ``os.replace``. Arquivo em uso no Windows falha na troca -> HistorianError.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal

from pydantic import BaseModel, ConfigDict

from forja.config.paths import ForjaPaths
from forja.domain.errors import HistorianError
from forja.historian.core_store import CORE_TABLES
from forja.historian.sqlite import HISTORIAN_TABLES
from forja.historian.writer import connect_immutable, timestamp_label
from forja.version import __version__

if TYPE_CHECKING:
    from forja.historian.core_store import SqliteCoreStore
    from forja.historian.sqlite import SqliteHistorian

MANIFEST_NAME: Final[str] = "manifest.json"
MANIFEST_VERSION: Final[int] = 1
_SIDE_SUFFIXES: Final[tuple[str, ...]] = ("-wal", "-shm", "-journal")

BackupKind = Literal["historian", "core"]
_TABLES_BY_KIND: Final[dict[str, tuple[str, ...]]] = {
    "historian": HISTORIAN_TABLES,
    "core": CORE_TABLES,
}


class BackupFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: BackupKind
    file_name: str
    size_bytes: int
    sha256: str
    schema_version: int
    tables: dict[str, int]
    """Linhas por tabela no momento do backup."""


class BackupManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    manifest_version: int = MANIFEST_VERSION
    created_at_utc: datetime
    app_version: str
    sqlite_version: str
    files: tuple[BackupFile, ...]

    def file_for(self, kind: BackupKind) -> BackupFile:
        for f in self.files:
            if f.kind == kind:
                return f
        raise HistorianError(f"manifesto sem arquivo do tipo {kind}")


# ----------------------------------------------------------------------------- backup


async def backup_all(
    historian: SqliteHistorian,
    core: SqliteCoreStore,
    paths: ForjaPaths,
    dest_dir: Path | None = None,
) -> BackupManifest:
    """Copia os dois bancos para ``dest_dir`` (padrao: backups_dir/backup_<instante>) e assina."""
    now = historian.clock.now_utc()
    dest = (
        Path(dest_dir)
        if dest_dir is not None
        else paths.backups_dir / (f"backup_{timestamp_label(now)}")
    )
    dest.mkdir(parents=True, exist_ok=True)

    hist_file = await historian.backup(dest)
    core_file = await core.backup(dest)
    files = (
        await asyncio.to_thread(describe_backup_file, "historian", hist_file),
        await asyncio.to_thread(describe_backup_file, "core", core_file),
    )
    manifest = BackupManifest(
        created_at_utc=now,
        app_version=__version__,
        sqlite_version=sqlite3.sqlite_version,
        files=files,
    )
    (dest / MANIFEST_NAME).write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return manifest


def describe_backup_file(kind: BackupKind, path: Path) -> BackupFile:
    """integrity_check + contagens + sha256 de uma copia parada (aberta como immutable)."""
    check_integrity(path)
    tables = _TABLES_BY_KIND[kind]
    conn = connect_immutable(path)
    try:
        counts = {t: _count(conn, t, tables) for t in tables}
        row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
        version = int(row[0]) if row is not None and row[0] is not None else 0
    finally:
        conn.close()
    return BackupFile(
        kind=kind,
        file_name=path.name,
        size_bytes=path.stat().st_size,
        sha256=sha256_file(path),
        schema_version=version,
        tables=counts,
    )


def check_integrity(path: Path) -> None:
    """``PRAGMA integrity_check`` deve responder exatamente 'ok'."""
    conn = connect_immutable(path)
    try:
        rows = conn.execute("PRAGMA integrity_check").fetchall()
    finally:
        conn.close()
    if len(rows) != 1 or rows[0][0] != "ok":
        detail = "; ".join(str(r[0]) for r in rows[:5])
        raise HistorianError(f"integridade falhou em {path.name}: {detail}")


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _count(conn: sqlite3.Connection, table: str, allowed: tuple[str, ...]) -> int:
    if table not in allowed:
        raise HistorianError(f"tabela desconhecida: {table}")
    row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()  # noqa: S608 - allowlist
    return int(row[0]) if row is not None else 0


# ----------------------------------------------------------------------------- restore


def read_manifest(manifest_dir: Path) -> BackupManifest:
    mpath = Path(manifest_dir) / MANIFEST_NAME
    if not mpath.is_file():
        raise HistorianError(f"manifesto não encontrado: {mpath}")
    manifest = BackupManifest.model_validate_json(mpath.read_text(encoding="utf-8"))
    if manifest.manifest_version > MANIFEST_VERSION:
        raise HistorianError(
            f"manifesto versão {manifest.manifest_version}; este aplicativo lê até "
            f"{MANIFEST_VERSION}"
        )
    return manifest


def verify_backup(manifest_dir: Path) -> BackupManifest:
    """Confere existencia, sha256 e integridade de todos os arquivos do manifesto."""
    manifest_dir = Path(manifest_dir)
    manifest = read_manifest(manifest_dir)
    for f in manifest.files:
        src = manifest_dir / f.file_name
        if not src.is_file():
            raise HistorianError(f"arquivo do backup ausente: {src}")
        actual = sha256_file(src)
        if actual != f.sha256:
            raise HistorianError(
                f"checksum divergente em {f.file_name}: esperado {f.sha256[:12]}..., "
                f"obtido {actual[:12]}...; backup corrompido ou alterado"
            )
        check_integrity(src)
    return manifest


async def restore_all(manifest_dir: Path, paths: ForjaPaths) -> None:
    """Substitui forja_historian.db e forja_core.db pelos arquivos do backup.

    Exige servico parado (bancos fechados). Valida tudo antes de tocar em qualquer destino.
    """
    manifest_dir = Path(manifest_dir)
    manifest = await asyncio.to_thread(verify_backup, manifest_dir)
    targets: dict[str, Path] = {"historian": paths.historian_db, "core": paths.core_db}
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    for f in manifest.files:
        await asyncio.to_thread(_replace_db, manifest_dir / f.file_name, targets[f.kind], f)


def _replace_db(src: Path, target: Path, expected: BackupFile) -> None:
    tmp = target.with_name(target.name + ".restore-tmp")
    try:
        shutil.copyfile(src, tmp)
        if sha256_file(tmp) != expected.sha256:
            raise HistorianError(f"cópia de {src.name} divergiu do manifesto; disco com problema?")
        for suffix in _SIDE_SUFFIXES:
            side = Path(str(target) + suffix)
            if side.exists():
                side.unlink()
        os.replace(tmp, target)
    except PermissionError as exc:
        raise HistorianError(
            f"não foi possível substituir {target.name}: arquivo em uso. Pare o serviço antes."
        ) from exc
    finally:
        if tmp.exists():
            tmp.unlink()
