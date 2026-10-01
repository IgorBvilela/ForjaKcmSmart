"""Historian e core store em SQLite (Bloco 2).

- ``SqliteHistorian``: amostras, agregados 1m/1h, comm_log, retencao, backup (forja_historian.db).
- ``SqliteCoreStore``: eventos, diagnosticos e auditoria append-only (forja_core.db).
- ``backup_all`` / ``restore_all``: copia consistente dos dois com manifesto sha256.
- ``migrate``: migracoes numeradas, so para frente, com checksum.
"""

from forja.historian.backup import (
    MANIFEST_NAME,
    BackupFile,
    BackupManifest,
    backup_all,
    restore_all,
    verify_backup,
)
from forja.historian.core_store import CORE_TABLES, DiagnosesView, EventsView, SqliteCoreStore
from forja.historian.migrate import MIGRATIONS_DIR, current_version, migrate
from forja.historian.sqlite import HISTORIAN_TABLES, SqliteHistorian

__all__ = [
    "CORE_TABLES",
    "HISTORIAN_TABLES",
    "MANIFEST_NAME",
    "MIGRATIONS_DIR",
    "BackupFile",
    "BackupManifest",
    "DiagnosesView",
    "EventsView",
    "SqliteCoreStore",
    "SqliteHistorian",
    "backup_all",
    "current_version",
    "migrate",
    "restore_all",
    "verify_backup",
]
