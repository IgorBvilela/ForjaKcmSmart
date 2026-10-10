"""Core store: histórico de testes somente leitura e comissionamento.

Ambos são evidência: não se apagam."""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from datetime import date, timedelta
from pathlib import Path

import pytest

from forja.domain import (
    CheckResult,
    CommissioningCheck,
    CommissioningHeader,
    CommissioningSession,
    CommissioningStatus,
    HistorianError,
    Quality,
)
from forja.historian import SqliteCoreStore
from forja.infra.clock import FakeClock

pytestmark = pytest.mark.integration

EQ = "EQ_TESTE"


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


def _session(clock: FakeClock) -> CommissioningSession:
    return CommissioningSession(
        equipment_id=EQ,
        created_at_utc=clock.now_utc(),
        updated_at_utc=clock.now_utc(),
        header=CommissioningHeader(technician="tecnico", visit_date=date(2026, 10, 20)),
    )


async def test_testes_de_leitura_ficam_em_ordem_e_nao_se_apagam(
    core: SqliteCoreStore, clock: FakeClock
) -> None:
    first = await core.save_read_test(
        equipment_id=EQ,
        driver="modbus_tcp",
        final_stage="TIMEOUT",
        success=False,
        latency_ms=None,
        fingerprint="a" * 64,
        user="tecnico",
        result={"error_pt": "Timeout"},
    )
    clock.advance(10)
    second = await core.save_read_test(
        equipment_id=EQ,
        driver="modbus_tcp",
        final_stage="READ_OBTAINED",
        success=True,
        latency_ms=12.5,
        fingerprint="b" * 64,
        user="tecnico",
        result={"values": {}},
    )
    assert second > first
    tests = await core.list_read_tests(EQ, limit=10)
    assert [t["final_stage"] for t in tests] == ["READ_OBTAINED", "TIMEOUT"]
    assert tests[0]["success"] is True
    assert tests[0]["result"] == {"values": {}}
    latest = await core.latest_read_test(EQ)
    assert latest is not None
    assert latest["fingerprint"] == "b" * 64
    assert await core.latest_read_test("OUTRO") is None
    conn = sqlite3.connect(core.db_path)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            conn.execute("DELETE FROM read_tests")
    finally:
        conn.close()


async def test_sessao_de_comissionamento_e_conferencias(
    core: SqliteCoreStore, clock: FakeClock
) -> None:
    session = _session(clock)
    await core.save_commissioning(session)
    check = CommissioningCheck(
        session_id=session.id,
        ts_utc=clock.now_utc(),
        tag="mass_flow",
        label_pt="Vazão",
        unit="kg/h",
        address_text="holding 0, 2 registradores",
        forja_value=1290.0,
        forja_quality=Quality.UNCERTAIN,
        kcm_value=1291.5,
        result=CheckResult.MATCH,
        technician="tecnico",
    )
    check_id = await core.add_commissioning_check(check)
    assert check_id > 0
    checks = await core.list_commissioning_checks(session.id)
    assert len(checks) == 1
    assert checks[0].difference == pytest.approx(1.5)
    assert checks[0].id == check_id

    clock.advance(60)
    closed = session.model_copy(
        update={
            "status": CommissioningStatus.CLOSED,
            "updated_at_utc": clock.now_utc(),
            "conclusion_pt": "Vazão confere.",
        }
    )
    await core.save_commissioning(closed)
    loaded = await core.get_commissioning(session.id)
    assert loaded is not None
    assert loaded.status is CommissioningStatus.CLOSED
    assert [s.id for s in await core.list_commissioning(EQ)] == [session.id]

    # encerrada é final: nem editar, nem conferir mais
    with pytest.raises(HistorianError, match="encerrada"):
        await core.save_commissioning(closed.model_copy(update={"conclusion_pt": "outra"}))
    with pytest.raises(HistorianError, match="encerrada"):
        await core.add_commissioning_check(check.model_copy(update={"id": None}))


async def test_conferencia_sem_sessao_e_recusada(core: SqliteCoreStore, clock: FakeClock) -> None:
    orphan = CommissioningCheck(
        session_id="naoexiste01",
        ts_utc=clock.now_utc() - timedelta(seconds=1),
        tag="rpm",
        result=CheckResult.NOT_CHECKED,
        technician="tecnico",
    )
    with pytest.raises(HistorianError):
        await core.add_commissioning_check(orphan)
