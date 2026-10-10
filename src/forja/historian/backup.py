"""Backup e restauracao dos dois bancos, com manifesto verificavel.

- historian: ``Connection.backup()`` paginado (a escrita ao vivo entra entre os passos);
- core: ``VACUUM INTO`` (copia compacta e consistente);
- ``manifest.json``: sha256, tamanho, versao do schema e contagem por tabela de cada arquivo,
  mais ``PRAGMA integrity_check`` em cada copia antes de assinar o manifesto;
- ``restore_all``: so com o servico parado (bancos fechados). Valida checksum e integridade de
  TODOS os arquivos antes de tocar em qualquer destino; depois copia para um arquivo temporario
  ao lado e troca com ``os.replace``. Arquivo em uso no Windows falha na troca -> HistorianError.
- configuracao: ``config/`` e ``knowledge/`` vao num zip (``config_<instante>.zip``) com sha256
  no manifesto; ``restore_config`` guarda uma copia da configuracao atual antes de trocar.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import sqlite3
import tempfile
import zipfile
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
MANIFEST_VERSION: Final[int] = 2
_SIDE_SUFFIXES: Final[tuple[str, ...]] = ("-wal", "-shm", "-journal")

BackupKind = Literal["historian", "core", "config"]
CONFIG_FOLDERS: Final[tuple[str, ...]] = ("config", "knowledge")
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
    *,
    include_config: bool = True,
) -> BackupManifest:
    """Copia os dois bancos (e a configuracao) para ``dest_dir`` e assina o manifesto.

    Padrao de destino: backups_dir/backup_<instante>.
    """
    now = historian.clock.now_utc()
    dest = (
        Path(dest_dir)
        if dest_dir is not None
        else paths.backups_dir / (f"backup_{timestamp_label(now)}")
    )
    dest.mkdir(parents=True, exist_ok=True)

    hist_file = await historian.backup(dest)
    core_file = await core.backup(dest)
    files = [
        await asyncio.to_thread(describe_backup_file, "historian", hist_file),
        await asyncio.to_thread(describe_backup_file, "core", core_file),
    ]
    if include_config and any((paths.home / f).is_dir() for f in CONFIG_FOLDERS):
        config_zip = await asyncio.to_thread(archive_config, paths, dest, now)
        files.append(await asyncio.to_thread(describe_config_archive, config_zip))
    manifest = BackupManifest(
        created_at_utc=now,
        app_version=__version__,
        sqlite_version=sqlite3.sqlite_version,
        files=tuple(files),
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


def archive_config(paths: ForjaPaths, dest: Path, now: datetime) -> Path:
    """Zip de config/ e knowledge/ (caminhos relativos à pasta de dados)."""
    target = dest / f"config_{timestamp_label(now)}.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for folder in CONFIG_FOLDERS:
            base = paths.home / folder
            if not base.is_dir():
                continue
            for item in sorted(base.rglob("*")):
                if item.is_file():
                    zf.write(item, item.relative_to(paths.home).as_posix())
    return target


def describe_config_archive(path: Path) -> BackupFile:
    names = _checked_config_names(path)
    return BackupFile(
        kind="config",
        file_name=path.name,
        size_bytes=path.stat().st_size,
        sha256=sha256_file(path),
        schema_version=0,
        tables={"arquivos": len(names)},
    )


def _checked_config_names(path: Path) -> list[str]:
    """Nomes do zip, conferidos: CRC ok e todos dentro de config/ ou knowledge/ (sem '..')."""
    try:
        with zipfile.ZipFile(path) as zf:
            broken = zf.testzip()
            names = zf.namelist()
    except zipfile.BadZipFile as exc:
        raise HistorianError(f"configuração do backup ilegível: {path.name}") from exc
    if broken is not None:
        raise HistorianError(f"configuração do backup corrompida em {broken}")
    for name in names:
        parts = Path(name).parts
        if name.startswith(("/", "\\")) or ".." in parts or parts[0] not in CONFIG_FOLDERS:
            raise HistorianError(f"caminho inesperado na configuração do backup: {name!r}")
    return names


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
    if manifest.manifest_version > MANIFEST_VERSION:  # versões 1 (só bancos) e 2 são lidas
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
        if f.kind == "config":
            _checked_config_names(src)
        else:
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
        if f.kind in targets:
            await asyncio.to_thread(_replace_db, manifest_dir / f.file_name, targets[f.kind], f)


async def restore_config(manifest_dir: Path, paths: ForjaPaths, now: datetime) -> Path:
    """Troca config/ e knowledge/ pelos do backup. Antes, copia a configuração atual para
    backups_dir/antes_da_restauracao_<instante>, que é devolvida."""
    manifest_dir = Path(manifest_dir)
    manifest = await asyncio.to_thread(verify_backup, manifest_dir)
    entry = next((f for f in manifest.files if f.kind == "config"), None)
    if entry is None:
        raise HistorianError("este backup não tem a configuração (feito antes da versão 2)")
    return await asyncio.to_thread(_swap_config, manifest_dir / entry.file_name, paths, now)


def _swap_config(archive: Path, paths: ForjaPaths, now: datetime) -> Path:
    safety = paths.backups_dir / f"antes_da_restauracao_{timestamp_label(now)}"
    safety.mkdir(parents=True, exist_ok=True)
    for folder in CONFIG_FOLDERS:
        current = paths.home / folder
        if current.is_dir():
            shutil.copytree(current, safety / folder, dirs_exist_ok=True)
    _checked_config_names(archive)
    with tempfile.TemporaryDirectory(dir=paths.home, prefix=".restaurando_") as tmp:
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(tmp)
        for folder in CONFIG_FOLDERS:
            incoming = Path(tmp) / folder
            if not incoming.is_dir():
                continue
            current = paths.home / folder
            if current.is_dir():
                shutil.rmtree(current)
            shutil.move(str(incoming), str(current))
    return safety


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
