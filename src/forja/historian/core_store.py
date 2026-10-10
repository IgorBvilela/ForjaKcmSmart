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
import hashlib
import json
import sqlite3
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Final, TypeVar

from pydantic import ValidationError

from forja.domain.commissioning import CommissioningCheck, CommissioningSession
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

CORE_TABLES: Final[tuple[str, ...]] = (
    "events",
    "diagnoses",
    "audit_log",
    "audit_chain",
    "read_tests",
    "commissioning_sessions",
    "commissioning_checks",
)

# A classe define um metodo chamado ``list``; estes apelidos evitam a sombra nas anotacoes.
EventList = list[Event]
DiagnosisList = list[Diagnosis]
AuditRows = list[dict[str, Any]]
CommissioningList = list[CommissioningSession]
CheckList = list[CommissioningCheck]

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
SQL_LAST_LINK: Final[str] = "SELECT hash FROM audit_chain ORDER BY audit_id DESC LIMIT 1"
SQL_INSERT_LINK: Final[str] = "INSERT INTO audit_chain (audit_id, prev_hash, hash) VALUES (?, ?, ?)"
SQL_CHAIN_WALK: Final[str] = """
SELECT a.id, a.ts_ms, a.user, a.action, a.entity_type, a.entity_id, a.before_json, a.after_json,
       a.reason_pt, c.prev_hash, c.hash
FROM audit_log a LEFT JOIN audit_chain c ON c.audit_id = a.id
ORDER BY a.id
"""
AUDIT_GENESIS: Final[str] = "0" * 64
"""Hash anterior do primeiro elo da cadeia."""


def audit_link_hash(prev_hash: str, row: Sequence[object]) -> str:
    """sha256(hash anterior | conteúdo canônico da linha de audit_log, na ordem das colunas)."""
    content = json.dumps(list(row), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(f"{prev_hash}|{content}".encode()).hexdigest()


def verify_audit_chain(conn: sqlite3.Connection) -> dict[str, Any]:
    """Refaz a cadeia do começo. Para no primeiro elo que não confere e diz qual."""
    before_chain = 0
    chained = 0
    prev = AUDIT_GENESIS
    started = False

    def broken(audit_id: int | None, reason_pt: str) -> dict[str, Any]:
        where = f" no registro {audit_id}" if audit_id is not None else ""
        return {
            "ok": False,
            "chained": chained,
            "before_chain": before_chain,
            "broken_at": audit_id,
            "message_pt": f"Trilha de auditoria alterada fora do Forja{where}: {reason_pt}.",
        }

    for row in conn.execute(SQL_CHAIN_WALK):
        audit_row, prev_hash, link = row[:9], row[9], row[10]
        audit_id = int(row[0])
        if prev_hash is None:
            if started:
                return broken(audit_id, "registro sem elo da cadeia")
            before_chain += 1
            continue
        started = True
        if prev_hash != prev:
            return broken(audit_id, "elo anterior não confere")
        if audit_link_hash(str(prev_hash), audit_row) != link:
            return broken(audit_id, "conteúdo diferente do encadeado")
        prev = str(link)
        chained += 1
    total_links = int(conn.execute("SELECT COUNT(*) FROM audit_chain").fetchone()[0])
    if total_links != chained:
        return broken(None, "elo sem registro correspondente")
    note = (
        f" {before_chain} registro(s) anteriores ao encadeamento ficam fora da cadeia."
        if before_chain
        else ""
    )
    return {
        "ok": True,
        "chained": chained,
        "before_chain": before_chain,
        "broken_at": None,
        "message_pt": f"Trilha de auditoria íntegra: {chained} registro(s) encadeado(s).{note}",
    }


SQL_AUDIT_LIST: Final[str] = """
SELECT id, ts_ms, user, action, entity_type, entity_id, before_json, after_json, reason_pt
FROM audit_log ORDER BY ts_ms DESC, id DESC LIMIT ?
"""

SQL_INSERT_READ_TEST: Final[str] = """
INSERT INTO read_tests (equipment_id, ts_ms, driver, final_stage, success, latency_ms,
                        fingerprint, user, result_json)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""
SQL_LIST_READ_TESTS: Final[str] = """
SELECT id, equipment_id, ts_ms, driver, final_stage, success, latency_ms, fingerprint, user,
       result_json
FROM read_tests WHERE equipment_id = ? ORDER BY ts_ms DESC, id DESC LIMIT ?
"""

SQL_UPSERT_COMMISSIONING: Final[str] = """
INSERT INTO commissioning_sessions (id, equipment_id, created_ms, updated_ms, status, session_json)
VALUES (?, ?, ?, ?, ?, ?)
ON CONFLICT (id) DO UPDATE SET
    updated_ms = excluded.updated_ms, status = excluded.status,
    session_json = excluded.session_json
"""
SQL_GET_COMMISSIONING: Final[str] = "SELECT session_json FROM commissioning_sessions WHERE id = ?"
SQL_COMMISSIONING_STATUS: Final[str] = "SELECT status FROM commissioning_sessions WHERE id = ?"
SQL_LIST_COMMISSIONING: Final[str] = (
    "SELECT session_json FROM commissioning_sessions ORDER BY created_ms DESC LIMIT ?"
)
SQL_LIST_COMMISSIONING_EQ: Final[str] = (
    "SELECT session_json FROM commissioning_sessions WHERE equipment_id = ? "
    "ORDER BY created_ms DESC LIMIT ?"
)
SQL_INSERT_COMMISSIONING_CHECK: Final[str] = """
INSERT INTO commissioning_checks (session_id, ts_ms, tag, check_json) VALUES (?, ?, ?, ?)
"""
SQL_LIST_COMMISSIONING_CHECKS: Final[str] = """
SELECT id, check_json FROM commissioning_checks WHERE session_id = ? ORDER BY ts_ms, id
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
            # Registro e elo da cadeia na mesma transação: nunca um sem o outro.
            conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = conn.execute(SQL_INSERT_AUDIT, params)
                audit_id = int(cursor.lastrowid or 0)
                last = conn.execute(SQL_LAST_LINK).fetchone()
                prev_hash = str(last[0]) if last is not None else AUDIT_GENESIS
                link = audit_link_hash(prev_hash, (audit_id, *params))
                conn.execute(SQL_INSERT_LINK, (audit_id, prev_hash, link))
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

        await self._writer_or_raise().submit(run)

    async def verify_audit(self) -> dict[str, Any]:
        """Confere a cadeia de hash da trilha de auditoria (só leitura)."""
        return await self._read(verify_audit_chain)

    async def audit_list(self, limit: int = 200) -> AuditRows:
        lim = max(1, int(limit))

        def run(conn: sqlite3.Connection) -> list[dict[str, Any]]:
            return [_audit_from_row(r) for r in conn.execute(SQL_AUDIT_LIST, (lim,)).fetchall()]

        return await self._read(run)

    # ------------------------------------------------------------------ testes somente leitura

    async def save_read_test(
        self,
        *,
        equipment_id: str,
        driver: str,
        final_stage: str,
        success: bool,
        latency_ms: float | None,
        fingerprint: str,
        user: str,
        result: dict[str, Any],
    ) -> int:
        """Registra um teste somente leitura (sucesso ou falha). Devolve o id da linha."""
        params = (
            equipment_id,
            to_ms(self._clock.now_utc()),
            driver,
            final_stage,
            1 if success else 0,
            latency_ms,
            fingerprint,
            user,
            json.dumps(result, ensure_ascii=False, default=str),
        )

        def run(conn: sqlite3.Connection) -> int:
            cur = conn.execute(SQL_INSERT_READ_TEST, params)
            return int(cur.lastrowid or 0)

        return await self._writer_or_raise().submit(run)

    async def list_read_tests(self, equipment_id: str, limit: int = 50) -> AuditRows:
        lim = max(1, int(limit))

        def run(conn: sqlite3.Connection) -> list[dict[str, Any]]:
            rows = conn.execute(SQL_LIST_READ_TESTS, (equipment_id, lim)).fetchall()
            return [_read_test_from_row(r) for r in rows]

        return await self._read(run)

    async def latest_read_test(self, equipment_id: str) -> dict[str, Any] | None:
        rows = await self.list_read_tests(equipment_id, limit=1)
        return rows[0] if rows else None

    # ------------------------------------------------------------------ comissionamento

    async def save_commissioning(self, session: CommissioningSession) -> None:
        """Cria ou atualiza a sessão. Sessão encerrada é final (trigger recusa)."""
        params = (
            session.id,
            session.equipment_id,
            to_ms(session.created_at_utc),
            to_ms(session.updated_at_utc),
            session.status.value,
            session.model_dump_json(),
        )

        def run(conn: sqlite3.Connection) -> None:
            try:
                conn.execute(SQL_UPSERT_COMMISSIONING, params)
            except sqlite3.IntegrityError as exc:
                raise HistorianError(
                    f"sessão de comissionamento {session.id} encerrada: não pode ser alterada"
                ) from exc

        await self._writer_or_raise().submit(run)

    async def get_commissioning(self, session_id: str) -> CommissioningSession | None:
        def run(conn: sqlite3.Connection) -> CommissioningSession | None:
            row = conn.execute(SQL_GET_COMMISSIONING, (session_id,)).fetchone()
            return None if row is None else _commissioning_from_json(row[0])

        return await self._read(run)

    async def list_commissioning(
        self, equipment_id: str | None = None, limit: int = 50
    ) -> CommissioningList:
        lim = max(1, int(limit))

        def run(conn: sqlite3.Connection) -> list[CommissioningSession]:
            if equipment_id is None:
                rows = conn.execute(SQL_LIST_COMMISSIONING, (lim,)).fetchall()
            else:
                rows = conn.execute(SQL_LIST_COMMISSIONING_EQ, (equipment_id, lim)).fetchall()
            return [_commissioning_from_json(r[0]) for r in rows]

        return await self._read(run)

    async def add_commissioning_check(self, check: CommissioningCheck) -> int:
        """Acrescenta uma conferência a uma sessão ABERTA. Devolve o id."""
        params = (
            check.session_id,
            to_ms(check.ts_utc),
            check.tag,
            check.model_dump_json(exclude={"id"}),
        )

        def run(conn: sqlite3.Connection) -> int:
            row = conn.execute(SQL_COMMISSIONING_STATUS, (check.session_id,)).fetchone()
            if row is None:
                raise HistorianError(f"sessão de comissionamento {check.session_id} não existe")
            if row[0] != "OPEN":
                raise HistorianError(
                    f"sessão de comissionamento {check.session_id} encerrada: nova conferência "
                    "recusada"
                )
            cur = conn.execute(SQL_INSERT_COMMISSIONING_CHECK, params)
            return int(cur.lastrowid or 0)

        return await self._writer_or_raise().submit(run)

    async def list_commissioning_checks(self, session_id: str) -> CheckList:
        def run(conn: sqlite3.Connection) -> list[CommissioningCheck]:
            rows = conn.execute(SQL_LIST_COMMISSIONING_CHECKS, (session_id,)).fetchall()
            return [_check_from_row(r) for r in rows]

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
        """Trilha de auditoria do core (o reconhecimento de evento grava por aqui)."""
        await self._store.audit(user, action, entity_type, entity_id, before, after, reason_pt)

    async def audit_list(self, limit: int = 200) -> AuditRows:
        return await self._store.audit_list(limit)


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


def _read_test_from_row(row: tuple[object, ...]) -> dict[str, Any]:
    id_, eq, ts_ms, driver, stage, success, latency, fingerprint, user, result = row
    loaded = json.loads(str(result)) if result else {}
    return {
        "id": int(id_),  # type: ignore[call-overload]
        "equipment_id": str(eq),
        "ts_utc": from_ms(int(ts_ms)),  # type: ignore[call-overload]
        "driver": str(driver),
        "final_stage": str(stage),
        "success": bool(success),
        "latency_ms": None if latency is None else float(latency),  # type: ignore[arg-type]
        "fingerprint": str(fingerprint),
        "user": str(user),
        "result": loaded if isinstance(loaded, dict) else {"value": loaded},
    }


def _commissioning_from_json(raw: object) -> CommissioningSession:
    try:
        return CommissioningSession.model_validate_json(str(raw))
    except ValidationError as exc:
        raise HistorianError(f"sessão de comissionamento em formato incompatível: {exc}") from exc


def _check_from_row(row: tuple[object, ...]) -> CommissioningCheck:
    id_, raw = row
    try:
        check = CommissioningCheck.model_validate_json(str(raw))
    except ValidationError as exc:
        raise HistorianError(f"conferência em formato incompatível: {exc}") from exc
    return check.model_copy(update={"id": int(id_)})  # type: ignore[call-overload]


def _count_table(conn: sqlite3.Connection, table: str) -> int:
    if table not in CORE_TABLES:
        raise HistorianError(f"tabela desconhecida: {table}")
    row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()  # noqa: S608 - allowlist
    return int(row[0]) if row is not None else 0
