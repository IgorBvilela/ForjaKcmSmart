"""Core store: eventos, diagnosticos, auditoria append-only e migracoes."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import pytest

from forja.domain import (
    OFFICIAL_SECTIONS_PT,
    DiagnosisRepository,
    EventRepository,
    EventStatus,
    HistorianError,
)
from forja.historian import MIGRATIONS_DIR, SqliteCoreStore, migrate
from forja.infra.clock import FakeClock
from tests.integration._historian_helpers import (
    EQ,
    fetch_all,
    make_diagnosis,
    make_event,
    raw_conn,
    table_count,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
async def core(tmp_path: Path, clock: FakeClock) -> AsyncIterator[SqliteCoreStore]:
    store = SqliteCoreStore(tmp_path / "forja_core.db", clock)
    await store.open()
    try:
        yield store
    finally:
        await store.close()


# ----------------------------------------------------------------------------- esquema


async def test_open_cria_tabelas_triggers_e_migracao(core: SqliteCoreStore) -> None:
    assert core.is_open
    names = {
        (r[0], r[1])
        for r in fetch_all(
            core.db_path, "SELECT type, name FROM sqlite_master WHERE type IN ('table','trigger')"
        )
    }
    assert {
        ("table", "events"),
        ("table", "diagnoses"),
        ("table", "audit_log"),
        ("table", "schema_migrations"),
        ("trigger", "audit_log_no_update"),
        ("trigger", "audit_log_no_delete"),
    } <= names
    assert fetch_all(core.db_path, "SELECT version, name FROM schema_migrations") == [
        (1, "0001_core")
    ]
    assert fetch_all(core.db_path, "PRAGMA journal_mode") == [("wal",)]
    st = await core.stats()
    assert st["rows"] == {"events": 0, "diagnoses": 0, "audit_log": 0}
    assert st["schema_version"] == 1


# ----------------------------------------------------------------------------- eventos


async def test_save_get_evento_round_trip(core: SqliteCoreStore, clock: FakeClock) -> None:
    ev = make_event(clock)
    await core.save(ev)
    got = await core.get(ev.id)
    assert got == ev
    assert got is not None
    assert got.context.pre_samples[0].value == 2.0
    assert got.context.what_changed[0].changed_first is True
    assert got.start_utc.tzinfo is not None
    assert await core.get("nao-existe") is None
    # colunas indexadas sao copia do JSON
    row = fetch_all(
        core.db_path, "SELECT equipment_id, type, status, dedupe_key, end_ms FROM events"
    )
    assert row == [(EQ, "BELT_LOAD_LOW", "OPEN", f"{EQ}:R-BELTLOAD-001", None)]


async def test_save_mesmo_id_atualiza(core: SqliteCoreStore, clock: FakeClock) -> None:
    ev = make_event(clock)
    await core.events.save(ev)
    clock.advance(5)
    ev.status = EventStatus.ACKNOWLEDGED
    ev.acked_by = "maria"
    ev.acked_at_utc = clock.now_utc()
    await core.save(ev)

    assert table_count(core.db_path, "events") == 1
    got = await core.get(ev.id)
    assert got is not None
    assert got.status is EventStatus.ACKNOWLEDGED
    assert got.acked_by == "maria"
    assert got.acked_at_utc == clock.now_utc()
    assert fetch_all(core.db_path, "SELECT status FROM events") == [("ACKNOWLEDGED",)]


async def test_list_filtra_e_ordena(core: SqliteCoreStore, clock: FakeClock) -> None:
    t0 = clock.now_utc()
    e1 = make_event(clock, "EQ1", "EQ1:R-A", start=t0)
    e2 = make_event(clock, "EQ2", "EQ2:R-A", start=t0 + timedelta(minutes=10))
    e3 = make_event(
        clock, "EQ1", "EQ1:R-B", start=t0 + timedelta(minutes=20), end=t0 + timedelta(minutes=25)
    )
    for e in (e1, e2, e3):
        await core.save(e)

    ids = [e.id for e in await core.list()]
    assert ids == [e3.id, e2.id, e1.id]
    assert [e.id for e in await core.list(equipment_id="EQ1")] == [e3.id, e1.id]
    assert [e.id for e in await core.list(open_only=True)] == [e2.id, e1.id]
    assert [e.id for e in await core.list(since=t0 + timedelta(minutes=5))] == [e3.id, e2.id]
    assert [e.id for e in await core.list(until=t0 + timedelta(minutes=15))] == [e2.id, e1.id]
    assert [e.id for e in await core.list(limit=1)] == [e3.id]
    assert [e.id for e in await core.events.list(equipment_id="EQ2")] == [e2.id]
    assert await core.list(equipment_id="EQ9") == []


async def test_find_open_por_dedupe_key(core: SqliteCoreStore, clock: FakeClock) -> None:
    ev = make_event(clock, dedupe_key="EQ:R-1")
    await core.save(ev)
    assert await core.find_open(EQ, "EQ:R-1") == ev
    assert await core.find_open(EQ, "EQ:R-2") is None
    assert await core.find_open("OUTRO", "EQ:R-1") is None

    clock.advance(60)
    ev.end_utc = clock.now_utc()
    ev.status = EventStatus.RESOLVED
    await core.save(ev)
    assert await core.find_open(EQ, "EQ:R-1") is None

    ev2 = make_event(clock, dedupe_key="EQ:R-1")
    await core.events.save(ev2)
    assert await core.events.find_open(EQ, "EQ:R-1") == ev2
    assert await core.events.get(ev.id) == ev


# ----------------------------------------------------------------------------- diagnosticos


async def test_diagnostico_save_get_list(core: SqliteCoreStore, clock: FakeClock) -> None:
    ev = make_event(clock)
    await core.save(ev)
    d1 = make_diagnosis(ev, clock)
    await core.save(d1)
    clock.advance(5)
    d2 = make_diagnosis(ev, clock)
    await core.diagnoses.save(d2)

    got = await core.get_for_event(ev.id)
    assert got == d2  # o mais recente
    assert await core.get_for_event("nao-existe") is None
    assert [d.diagnosis_id for d in await core.diagnoses.list()] == [
        d2.diagnosis_id,
        d1.diagnosis_id,
    ]
    assert [d.diagnosis_id for d in await core.list_diagnoses(limit=1)] == [d2.diagnosis_id]
    assert await core.list_diagnoses(equipment_id="OUTRO") == []
    assert len(await core.diagnoses.list(equipment_id=EQ)) == 2

    # o JSON gravado e o contrato v1.0, com as 7 secoes oficiais
    (raw, schema_version) = fetch_all(
        core.db_path,
        "SELECT diagnosis_json, schema_version FROM diagnoses WHERE diagnosis_id = ?",
        (d2.diagnosis_id,),
    )[0]
    payload = json.loads(str(raw))
    assert schema_version == "1.0"
    for key, _title in OFFICIAL_SECTIONS_PT:
        assert key in payload
    assert payload["hypotheses"][0]["text_pt"].startswith("Comportamento compatível com")


async def test_diagnostico_sem_evento_e_recusado(core: SqliteCoreStore, clock: FakeClock) -> None:
    ev = make_event(clock)  # nunca gravado
    d = make_diagnosis(ev, clock)
    with pytest.raises(HistorianError, match="evento inexistente"):
        await core.save(d)
    assert table_count(core.db_path, "diagnoses") == 0


async def test_save_de_tipo_desconhecido_e_recusado(core: SqliteCoreStore) -> None:
    with pytest.raises(HistorianError, match="Event ou Diagnosis"):
        await core.save("texto qualquer")  # type: ignore[arg-type]


async def test_vistas_satisfazem_as_portas(core: SqliteCoreStore) -> None:
    assert isinstance(core.events, EventRepository)
    assert isinstance(core.diagnoses, DiagnosisRepository)
    assert isinstance(core, EventRepository)
    assert isinstance(core, DiagnosisRepository)


# ----------------------------------------------------------------------------- auditoria


async def test_audit_e_append_only(core: SqliteCoreStore, clock: FakeClock) -> None:
    t0 = clock.now_utc()
    await core.audit(
        "maria", "ACK", "event", "ev-1", {"status": "OPEN"}, {"status": "ACKNOWLEDGED"}, "ciente"
    )
    clock.advance(1)
    await core.audit("sistema", "BACKUP", "database", "forja_core.db", None, {"ok": True})

    rows = await core.audit_list()
    assert [r["action"] for r in rows] == ["BACKUP", "ACK"]
    assert rows[1]["ts_utc"] == t0
    assert rows[1]["user"] == "maria"
    assert rows[1]["before"] == {"status": "OPEN"}
    assert rows[1]["after"] == {"status": "ACKNOWLEDGED"}
    assert rows[1]["reason_pt"] == "ciente"
    assert rows[0]["before"] is None
    assert rows[0]["after"] == {"ok": True}
    assert [r["action"] for r in await core.audit_list(limit=1)] == ["BACKUP"]

    conn = raw_conn(core.db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("UPDATE audit_log SET action = 'X'")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("DELETE FROM audit_log")
    finally:
        conn.close()
    assert table_count(core.db_path, "audit_log") == 2


# ----------------------------------------------------------------------------- migracoes


def test_migracao_idempotente_e_recusa_versao_maior() -> None:
    conn = sqlite3.connect(":memory:", autocommit=True)
    try:
        assert migrate(conn, MIGRATIONS_DIR, "core") == ["0001_core"]
        assert migrate(conn, MIGRATIONS_DIR, "core") == []
        conn.execute(
            "INSERT INTO schema_migrations (version, name, applied_at_ms, checksum) "
            "VALUES (99, '0099_core_futuro', 0, 'x')"
        )
        with pytest.raises(HistorianError, match="downgrade"):
            migrate(conn, MIGRATIONS_DIR, "core")
    finally:
        conn.close()


def test_migracao_recusa_checksum_alterado() -> None:
    conn = sqlite3.connect(":memory:", autocommit=True)
    try:
        migrate(conn, MIGRATIONS_DIR, "historian")
        conn.execute("UPDATE schema_migrations SET checksum = 'abc' WHERE version = 1")
        with pytest.raises(HistorianError, match="checksum"):
            migrate(conn, MIGRATIONS_DIR, "historian")
    finally:
        conn.close()


def test_migracao_exige_autocommit() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        with pytest.raises(HistorianError, match="autocommit"):
            migrate(conn, MIGRATIONS_DIR, "core")
    finally:
        conn.close()


async def test_open_recusa_banco_de_versao_maior(tmp_path: Path, clock: FakeClock) -> None:
    path = tmp_path / "forja_core.db"
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE schema_migrations (version INTEGER NOT NULL, name TEXT NOT NULL, "
            "applied_at_ms INTEGER NOT NULL, checksum TEXT NOT NULL, PRIMARY KEY (version)) "
            "STRICT, WITHOUT ROWID"
        )
        conn.execute("INSERT INTO schema_migrations VALUES (7, '0007_core_futuro', 0, 'deadbeef')")
        conn.commit()
    finally:
        conn.close()

    store = SqliteCoreStore(path, clock)
    with pytest.raises(HistorianError, match="downgrade"):
        await store.open()
    assert not store.is_open
