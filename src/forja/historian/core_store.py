"""SqliteCoreStore: eventos, diagnosticos e trilha de auditoria em ``forja_core.db``.

O JSON validado pelo Pydantic (``model_dump_json``) e a fonte da verdade do objeto; as colunas
(equipment_id, start_ms, status, dedupe_key, type...) sao copia indexada para as consultas reais.
``PRAGMA foreign_keys=ON``: um diagnostico so existe para um evento gravado.

Implementa ``EventRepository`` (save/get/list/find_open) e ``DiagnosisRepository``
(save/get_for_event/list). As duas portas compartilham os nomes ``save`` e ``list``; por isso:
- no proprio store, ``save`` despacha pelo tipo (Event ou Diagnosis) e ``list`` devolve eventos
  (``list_diagnoses`` para diagnosticos);
- as vistas ``store.events`` e ``store.diagnoses`` expoem cada porta sem ambiguidade. Use-as no
  Container (``events_repo=store.events``, ``diagnoses_repo=store.diagnoses``).

``audit_log`` e append-only: UPDATE/DELETE abortam por trigger (sqlite3.IntegrityError).
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Final, TypeVar

from pydantic import ValidationError

from forja.domain.diagnosis import Diagnosis
from forja.domain.errors import HistorianError
from forja.domain.events import Event
from forja.domain.ports import Clock
from forja.historian.migrate import MIGRATIONS_DIR, migrate
from forja.historian.queries import from_ms, to_ms
from forja.historian.writer import (
    SqliteWriter,
    connect_ro,
    connect_rw,
    timestamp_label,
    unique_path,
)

T = TypeVar("T")

CORE_TABLES: Final[tuple[str, ...]] = ("events", "diagnoses", "audit_log")

# A classe define um metodo chamado ``list``; estes apelidos evitam a sombra nas anotacoes.
EventList = list[Event]
DiagnosisList = list[Diagnosis]
AuditRows = list[dict[str, Any]]

# ----------------------------------------------------------------------------- SQL

SQL_UPSERT_EVENT: Final[str] = """
INSERT INTO events (id, equipment_id, type, status, severity, start_ms, end_ms,
                    dedupe_key, rule_id, updated_ms, event_json)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (id) DO UPDATE SET
    equipment_id = excluded.equipment_id, type = excluded.type, status = excluded.status,
    severity = excluded.severity, start_ms = excluded.start_ms, end_ms = excluded.end_ms,
    dedupe_key = excluded.dedupe_key, rule_id = excluded.rule_id,
    updated_ms = excluded.updated_ms, event_json = excluded.event_json
"""
SQL_GET_EVENT: Final[str] = "SELECT event_json FROM events WHERE id = ?"
SQL_FIND_OPEN: Final[str] = """
SELECT event_json FROM events
WHERE equipment_id = ? AND dedupe_key = ? AND end_ms IS NULL
ORDER BY start_ms DESC LIMIT 1
"""

SQL_UPSERT_DIAGNOSIS: Final[str] = """
INSERT INTO diagnoses (diagnosis_id, event_id, equipment_id, generated_ms,
                       schema_version, engine_version, diagnosis_json)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (diagnosis_id) DO UPDATE SET
    event_id = excluded.event_id, equipment_id = excluded.equipment_id,
    generated_ms = excluded.generated_ms, schema_version = excluded.schema_version,
    engine_version = excluded.engine_version, diagnosis_json = excluded.diagnosis_json
"""
SQL_DIAGNOSIS_FOR_EVENT: Final[str] = """
SELECT diagnosis_json FROM diagnoses WHERE event_id = ?
ORDER BY generated_ms DESC LIMIT 1
"""
SQL_LIST_DIAGNOSES: Final[str] = (
    "SELECT diagnosis_json FROM diagnoses ORDER BY generated_ms DESC LIMIT ?"
)
SQL_LIST_DIAGNOSES_EQ: Final[str] = (
    "SELECT diagnosis_json FROM diagnoses WHERE equipment_id = ? ORDER BY generated_ms DESC LIMIT ?"
)

SQL_INSERT_AUDIT: Final[str] = """
INSERT INTO audit_log (ts_ms, user, action, entity_type, entity_id, before_json, after_json,
                       reason_pt)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""
SQL_AUDIT_LIST: Final[str] = """
SELECT id, ts_ms, user, action, entity_type, entity_id, before_json, after_json, reason_pt
FROM audit_log ORDER BY ts_ms DESC, id DESC LIMIT ?
"""


def sql_list_events(
    *, with_equipment: bool, with_since: bool, with_until: bool, open_only: bool
) -> str:
    """SELECT de eventos, mais recente primeiro, com filtros opcionais (so placeholders)."""
    where = ["1 = 1"]
    if with_equipment:
        where.append("equipment_id = ?")
    if with_since:
        where.append("start_ms >= ?")
    if with_until:
        where.append("start_ms <= ?")
    if open_only:
        where.append("end_ms IS NULL")
    clause = " AND ".join(where)
    return f"SELECT event_json FROM events WHERE {clause} ORDER BY start_ms DESC LIMIT ?"  # noqa: S608


# ----------------------------------------------------------------------------- store


class SqliteCoreStore:
    """Eventos + diagnosticos + auditoria. Uma thread escritora; leituras em conexao propria."""

    def __init__(self, db_path: Path, clock: Clock) -> None:
        self._path = Path(db_path)
        self._clock = clock
        self._writer: SqliteWriter | None = None
        self.events = EventsView(self)
        self.diagnoses = DiagnosesView(self)

    # ------------------------------------------------------------------ ciclo de vida

    @property
    def db_path(self) -> Path:
        return self._path

    @property
    def clock(self) -> Clock:
        return self._clock

    @property
    def is_open(self) -> bool:
        return self._writer is not None and self._writer.is_running

    async def open(self) -> None:
        if self._writer is not None:
            raise HistorianError("core store já aberto")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        now_ms = to_ms(self._clock.now_utc())
        path = self._path

        def connect() -> sqlite3.Connection:
            conn = connect_rw(path, foreign_keys=True)
            try:
                migrate(conn, MIGRATIONS_DIR, "core", now_ms=now_ms)
            except Exception:
                conn.close()
                raise
            return conn

        writer = SqliteWriter(connect, "core")
        await writer.start()
        self._writer = writer

    async def close(self) -> None:
        writer, self._writer = self._writer, None
        if writer is not None:
            await writer.close()

    def _writer_or_raise(self) -> SqliteWriter:
        if self._writer is None or not self._writer.is_running:
            raise HistorianError("core store não está aberto")
        return self._writer

    async def _read(self, fn: Callable[[sqlite3.Connection], T]) -> T:
        self._writer_or_raise()
        path = self._path

        def run() -> T:
            conn = connect_ro(path)
            try:
                return fn(conn)
            finally:
                conn.close()

        return await asyncio.to_thread(run)

    # ------------------------------------------------------------------ despacho (duas portas)

    async def save(self, obj: Event | Diagnosis) -> None:
        """EventRepository.save e DiagnosisRepository.save: despacha pelo tipo."""
        if isinstance(obj, Event):
            await self.save_event(obj)
        elif isinstance(obj, Diagnosis):
            await self.save_diagnosis(obj)
        else:
            raise HistorianError(f"save() aceita Event ou Diagnosis, não {type(obj).__name__}")

    # ------------------------------------------------------------------ eventos

    async def save_event(self, event: Event) -> None:
        """Insere ou substitui pelo id (o Event e mutavel: OPEN -> ACK -> RESOLVED)."""
        now_ms = to_ms(self._clock.now_utc())
        params = (
            event.id,
            event.equipment_id,
            event.type,
            event.status.value,
            event.severity.value,
            to_ms(event.start_utc),
            None if event.end_utc is None else to_ms(event.end_utc),
            event.dedupe_key,
            event.rule_id,
            now_ms,
            event.model_dump_json(),
        )

        def run(conn: sqlite3.Connection) -> None:
            conn.execute(SQL_UPSERT_EVENT, params)

        await self._writer_or_raise().submit(run)

    async def get(self, event_id: str) -> Event | None:
        def run(conn: sqlite3.Connection) -> Event | None:
            row = conn.execute(SQL_GET_EVENT, (event_id,)).fetchone()
            return None if row is None else _event_from_json(row[0])

        return await self._read(run)

    async def list(
        self,
        equipment_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        open_only: bool = False,
        limit: int = 200,
    ) -> EventList:
        """Eventos por start_utc decrescente. ``since``/``until`` filtram o inicio do evento."""
        params: list[object] = []
        if equipment_id is not None:
            params.append(equipment_id)
        if since is not None:
            params.append(to_ms(since))
        if until is not None:
            params.append(to_ms(until))
        params.append(max(1, int(limit)))
        sql = sql_list_events(
            with_equipment=equipment_id is not None,
            with_since=since is not None,
            with_until=until is not None,
            open_only=open_only,
        )

        def run(conn: sqlite3.Connection) -> list[Event]:
            return [_event_from_json(r[0]) for r in conn.execute(sql, params).fetchall()]

        return await self._read(run)

    async def find_open(self, equipment_id: str, dedupe_key: str) -> Event | None:
        def run(conn: sqlite3.Connection) -> Event | None:
            row = conn.execute(SQL_FIND_OPEN, (equipment_id, dedupe_key)).fetchone()
            return None if row is None else _event_from_json(row[0])

        return await self._read(run)

    # ------------------------------------------------------------------ diagnosticos

    async def save_diagnosis(self, diagnosis: Diagnosis) -> None:
        """Grava o JSON v1.0. Exige evento existente (chave estrangeira)."""
        params = (
            diagnosis.diagnosis_id,
            diagnosis.event_id,
            diagnosis.equipment_id,
            to_ms(diagnosis.generated_at_utc),
            diagnosis.diagnosis_schema_version,
            diagnosis.engine_version,
            diagnosis.model_dump_json(),
        )

        def run(conn: sqlite3.Connection) -> None:
            try:
                conn.execute(SQL_UPSERT_DIAGNOSIS, params)
            except sqlite3.IntegrityError as exc:
                raise HistorianError(
                    f"diagnóstico {diagnosis.diagnosis_id} referencia evento inexistente "
                    f"{diagnosis.event_id}; grave o evento antes"
                ) from exc

        await self._writer_or_raise().submit(run)

    async def get_for_event(self, event_id: str) -> Diagnosis | None:
        """Diagnostico mais recente do evento (None se nao houver)."""

        def run(conn: sqlite3.Connection) -> Diagnosis | None:
            row = conn.execute(SQL_DIAGNOSIS_FOR_EVENT, (event_id,)).fetchone()
            return None if row is None else _diagnosis_from_json(row[0])

        return await self._read(run)

    async def list_diagnoses(
        self, equipment_id: str | None = None, limit: int = 100
    ) -> DiagnosisList:
        lim = max(1, int(limit))

        def run(conn: sqlite3.Connection) -> list[Diagnosis]:
            if equipment_id is None:
                rows = conn.execute(SQL_LIST_DIAGNOSES, (lim,)).fetchall()
            else:
                rows = conn.execute(SQL_LIST_DIAGNOSES_EQ, (equipment_id, lim)).fetchall()
            return [_diagnosis_from_json(r[0]) for r in rows]

        return await self._read(run)

    # ------------------------------------------------------------------ auditoria

    async def audit(
        self,
        user: str,
        action: str,
        entity_type: str,
        entity_id: str,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        reason_pt: str = "",
    ) -> None:
        """Acrescenta uma linha na trilha. Nunca altera nem apaga (triggers garantem)."""
        params = (
            to_ms(self._clock.now_utc()),
            user,
            action,
            entity_type,
            entity_id,
            _json_or_none(before),
            _json_or_none(after),
            reason_pt,
        )

        def run(conn: sqlite3.Connection) -> None:
            conn.execute(SQL_INSERT_AUDIT, params)

        await self._writer_or_raise().submit(run)

    async def audit_list(self, limit: int = 200) -> AuditRows:
        lim = max(1, int(limit))

        def run(conn: sqlite3.Connection) -> list[dict[str, Any]]:
            return [_audit_from_row(r) for r in conn.execute(SQL_AUDIT_LIST, (lim,)).fetchall()]

        return await self._read(run)

    # ------------------------------------------------------------------ manutencao

    async def backup(self, dest_dir: Path) -> Path:
        """Copia consistente e compacta via ``VACUUM INTO``. Devolve o arquivo criado."""
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        label = timestamp_label(self._clock.now_utc())
        target = unique_path(dest, f"forja_core_{label}.db")

        def run(conn: sqlite3.Connection) -> Path:
            conn.execute("VACUUM INTO ?", (str(target),))
            return target

        return await self._writer_or_raise().submit(run)

    async def stats(self) -> dict[str, Any]:
        path = self._path

        def run(conn: sqlite3.Connection) -> dict[str, Any]:
            rows = {t: _count_table(conn, t) for t in CORE_TABLES}
            version = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
            return {
                "db_path": str(path),
                "size_bytes": path.stat().st_size if path.exists() else 0,
                "rows": rows,
                "schema_version": int(version) if version is not None else 0,
            }

        return await self._read(run)


# ----------------------------------------------------------------------------- vistas por porta


class EventsView:
    """``EventRepository`` sem ambiguidade de nomes."""

    def __init__(self, store: SqliteCoreStore) -> None:
        self._store = store

    async def save(self, event: Event) -> None:
        await self._store.save_event(event)

    async def get(self, event_id: str) -> Event | None:
        return await self._store.get(event_id)

    async def list(
        self,
        equipment_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        open_only: bool = False,
        limit: int = 200,
    ) -> list[Event]:
        return await self._store.list(equipment_id, since, until, open_only, limit)

    async def find_open(self, equipment_id: str, dedupe_key: str) -> Event | None:
        return await self._store.find_open(equipment_id, dedupe_key)


class DiagnosesView:
    """``DiagnosisRepository`` sem ambiguidade de nomes."""

    def __init__(self, store: SqliteCoreStore) -> None:
        self._store = store

    async def save(self, diagnosis: Diagnosis) -> None:
        await self._store.save_diagnosis(diagnosis)

    async def get_for_event(self, event_id: str) -> Diagnosis | None:
        return await self._store.get_for_event(event_id)

    async def list(self, equipment_id: str | None = None, limit: int = 100) -> list[Diagnosis]:
        return await self._store.list_diagnoses(equipment_id, limit)


# ----------------------------------------------------------------------------- helpers


def _event_from_json(raw: object) -> Event:
    try:
        return Event.model_validate_json(str(raw))
    except ValidationError as exc:
        raise HistorianError(f"evento gravado em formato incompatível: {exc}") from exc


def _diagnosis_from_json(raw: object) -> Diagnosis:
    try:
        return Diagnosis.model_validate_json(str(raw))
    except ValidationError as exc:
        raise HistorianError(f"diagnóstico gravado em formato incompatível: {exc}") from exc


def _json_or_none(value: dict[str, Any] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)


def _load_json(raw: object) -> dict[str, Any] | None:
    if raw is None:
        return None
    loaded = json.loads(str(raw))
    return loaded if isinstance(loaded, dict) else {"value": loaded}


def _audit_from_row(row: tuple[object, ...]) -> dict[str, Any]:
    id_, ts_ms, user, action, entity_type, entity_id, before, after, reason_pt = row
    return {
        "id": int(id_),  # type: ignore[call-overload]
        "ts_utc": from_ms(int(ts_ms)),  # type: ignore[call-overload]
        "user": str(user),
        "action": str(action),
        "entity_type": str(entity_type),
        "entity_id": str(entity_id),
        "before": _load_json(before),
        "after": _load_json(after),
        "reason_pt": str(reason_pt),
    }


def _count_table(conn: sqlite3.Connection, table: str) -> int:
    if table not in CORE_TABLES:
        raise HistorianError(f"tabela desconhecida: {table}")
    row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()  # noqa: S608 - allowlist
    return int(row[0]) if row is not None else 0
