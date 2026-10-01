"""Migracoes numeradas, so para frente, com checksum.

Arquivos em ``migrations_dir`` seguem ``<NNNN>_<kind>[_<descricao>].sql``
(ex.: ``0001_historian.sql``). A tabela ``schema_migrations`` guarda versao, nome, instante
e sha256 do arquivo aplicado.

Regras:
- aplica apenas versoes acima da atual, em ordem, cada uma na sua transacao;
- recusa checksum divergente de migracao ja aplicada (arquivo editado depois de aplicado);
- recusa banco com versao maior que a maior conhecida pelo app (downgrade).

A conexao precisa estar em ``autocommit=True`` (controle explicito de transacao).
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from forja.domain.errors import HistorianError

MIGRATIONS_DIR: Path = Path(__file__).resolve().parent / "migrations"
MigrationKind = Literal["historian", "core"]

_SCHEMA_MIGRATIONS_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version       INTEGER NOT NULL,
    name          TEXT    NOT NULL,
    applied_at_ms INTEGER NOT NULL,
    checksum      TEXT    NOT NULL,
    PRIMARY KEY (version)
) STRICT, WITHOUT ROWID
"""


@dataclass(frozen=True, slots=True)
class MigrationFile:
    """Um arquivo .sql de migracao ja lido."""

    version: int
    name: str
    path: Path
    sql: str
    checksum: str


def sha256_text(text: str) -> str:
    """sha256 hex do texto em UTF-8."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _name_pattern(kind: MigrationKind) -> re.Pattern[str]:
    return re.compile(rf"^(\d{{4}})_{re.escape(kind)}(?:_[a-z0-9_]+)?\.sql$")


def list_migrations(migrations_dir: Path, kind: MigrationKind) -> list[MigrationFile]:
    """Le e ordena as migracoes de um tipo. Versao duplicada e erro."""
    if not migrations_dir.is_dir():
        raise HistorianError(f"pasta de migrações não encontrada: {migrations_dir}")
    pattern = _name_pattern(kind)
    files: list[MigrationFile] = []
    for path in sorted(migrations_dir.glob("*.sql")):
        match = pattern.match(path.name)
        if match is None:
            continue
        sql = path.read_text(encoding="utf-8")
        files.append(
            MigrationFile(
                version=int(match.group(1)),
                name=path.stem,
                path=path,
                sql=sql,
                checksum=sha256_text(sql),
            )
        )
    versions = [f.version for f in files]
    if len(set(versions)) != len(versions):
        raise HistorianError(f"versão de migração duplicada em {migrations_dir} ({kind})")
    return sorted(files, key=lambda f: f.version)


def applied_migrations(conn: sqlite3.Connection) -> dict[int, tuple[str, str]]:
    """{versao: (nome, checksum)} ja aplicadas. Cria schema_migrations se nao existir."""
    conn.execute(_SCHEMA_MIGRATIONS_SQL)
    rows = conn.execute("SELECT version, name, checksum FROM schema_migrations").fetchall()
    return {int(v): (str(n), str(c)) for v, n, c in rows}


def current_version(conn: sqlite3.Connection) -> int:
    """Maior versao aplicada (0 se nenhuma)."""
    applied = applied_migrations(conn)
    return max(applied) if applied else 0


def migrate(
    conn: sqlite3.Connection,
    migrations_dir: Path,
    kind: MigrationKind,
    *,
    now_ms: int | None = None,
) -> list[str]:
    """Aplica as migracoes pendentes de ``kind``. Devolve os nomes aplicados (vazio = nada a fazer).

    ``now_ms`` e o instante registrado em applied_at_ms (vem do Clock do chamador). Sem ele,
    usa o relogio do proprio SQLite: e metadado do banco, nao tempo de dominio.
    """
    if getattr(conn, "autocommit", None) is not True:
        raise HistorianError("migrate exige conexão com autocommit=True")
    files = list_migrations(migrations_dir, kind)
    applied = applied_migrations(conn)
    known_max = files[-1].version if files else 0
    db_max = max(applied) if applied else 0
    if db_max > known_max:
        raise HistorianError(
            f"banco {kind} está na versão {db_max}, mas o aplicativo conhece até {known_max}; "
            "downgrade recusado"
        )
    done: list[str] = []
    for mig in files:
        if mig.version in applied:
            _, checksum = applied[mig.version]
            if checksum != mig.checksum:
                raise HistorianError(
                    f"migração {mig.name} já aplicada com checksum diferente do arquivo atual; "
                    "arquivo de migração não pode mudar depois de aplicado"
                )
            continue
        _apply(conn, mig, now_ms)
        done.append(mig.name)
    return done


def _apply(conn: sqlite3.Connection, mig: MigrationFile, now_ms: int | None) -> None:
    """Aplica uma migracao e registra em schema_migrations, na mesma transacao."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.executescript(mig.sql)
        if now_ms is None:
            conn.execute(
                "INSERT INTO schema_migrations (version, name, applied_at_ms, checksum) "
                "VALUES (?, ?, CAST(unixepoch('subsec') * 1000 AS INTEGER), ?)",
                (mig.version, mig.name, mig.checksum),
            )
        else:
            conn.execute(
                "INSERT INTO schema_migrations (version, name, applied_at_ms, checksum) "
                "VALUES (?, ?, ?, ?)",
                (mig.version, mig.name, now_ms, mig.checksum),
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
