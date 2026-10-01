"""Isolamento entre equipamentos: um falhando não derruba os outros nem o processo.

Três equipamentos no mesmo EquipmentManager com FakeClock. Sem sleep real, sem rede.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from forja.acquisition.backoff import Backoff
from forja.acquisition.manager import EquipmentManager
from forja.acquisition.state import ConnectionChanged
from forja.domain import TOPIC_CONNECTION, TOPIC_SAMPLES, ConnectionState, Quality, SampleBatch
from forja.infra import AsyncBus, FakeClock
from tests.fixtures.acquisition_fakes import (
    TAGS,
    Collector,
    DriverLog,
    FakeRegistry,
    InMemoryHistorian,
    exploding_factory,
    fake_pipeline,
    make_paths,
    make_profile,
    make_store,
    ok_factory,
    run_for,
    settle,
)

pytestmark = pytest.mark.integration

A, B, C = "EQ_A", "EQ_B", "EQ_C"


class Rig:
    def __init__(self, tmp_path: Path) -> None:
        self.clock = FakeClock()
        self.bus = AsyncBus()
        self.historian = InMemoryHistorian()
        self.registry = FakeRegistry()
        self.logs = {A: DriverLog(), B: DriverLog(), C: DriverLog()}
        self.store = make_store(
            make_paths(tmp_path), [make_profile(A), make_profile(B), make_profile(C)]
        )
        self.manager = EquipmentManager(
            self.store,
            self.registry,
            self.historian,
            self.bus,
            self.clock,
            pipeline=fake_pipeline(),
            backoff_factory=lambda: Backoff(jitter=0.0, max_s=1.0),
        )
        self.samples = Collector(self.bus, TOPIC_SAMPLES)
        self.connections = Collector(self.bus, TOPIC_CONNECTION)

    async def __aenter__(self) -> Rig:
        self.samples.start()
        self.connections.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.manager.stop_all(timeout_s=1)
        await self.samples.close()
        await self.connections.close()


@pytest.fixture
async def rig(tmp_path: Path) -> AsyncIterator[Rig]:
    async with Rig(tmp_path) as r:
        yield r


async def test_one_failing_equipment_does_not_affect_the_others(rig: Rig) -> None:
    rig.registry.add(A, ok_factory(rig.logs[A]))
    rig.registry.add(B, ok_factory(rig.logs[B]))
    rig.registry.add(C, exploding_factory(rig.logs[C]))

    await rig.manager.start_all()
    await run_for(rig.clock, 30)

    for eid in (A, B):
        status = rig.manager.status(eid)
        assert status.connection is ConnectionState.CONNECTED
        assert status.consecutive_errors == 0
        assert rig.logs[eid].reads >= 30
        assert await rig.historian.count(eid) >= 30 * len(TAGS)
        live = rig.manager.live(eid)
        assert set(live.samples) == set(TAGS)
        assert all(s.quality is Quality.SIMULATED for s in live.samples.values())

    status_c = rig.manager.status(C)
    assert status_c.connection is ConnectionState.ERROR
    assert status_c.consecutive_errors >= 20
    assert "Tempo esgotado" in status_c.detail_pt
    live_c = rig.manager.live(C)
    assert all(s.quality is Quality.COMM_ERROR for s in live_c.samples.values())
    assert all(s.value is None for s in live_c.samples.values())
    assert live_c.is_stale is False, "nunca houve valor bom em C: COMM_ERROR, não STALE"

    # o historian recebe COMM_ERROR como linha (value None); nunca STALE
    assert rig.historian.rows_for(C, Quality.COMM_ERROR)
    assert not [s for s in rig.historian.rows if s.quality is Quality.STALE]


async def test_driver_exploding_every_read_for_100_cycles_kills_nothing(rig: Rig) -> None:
    cycle = {"n": 0}

    def _boom() -> BaseException:
        cycle["n"] += 1
        # alterna tipos de exceção, inclusive uma que não é de driver
        return RuntimeError("explosão fake") if cycle["n"] % 2 else TimeoutError("timeout fake")

    rig.registry.add(A, ok_factory(rig.logs[A]))
    rig.registry.add(B, ok_factory(rig.logs[B]))
    rig.registry.add(C, exploding_factory(rig.logs[C], exc_factory=_boom))

    await rig.manager.start_all()
    await run_for(rig.clock, 120)

    assert rig.logs[C].failures >= 100
    task_c = rig.manager.task_of(C)
    assert task_c is not None
    assert not task_c.done(), "task do equipamento falho continua viva"
    for eid in (A, B):
        task = rig.manager.task_of(eid)
        assert task is not None
        assert not task.done()
        assert rig.logs[eid].reads >= 100
    assert rig.manager.status(C).connection is ConnectionState.ERROR
    assert rig.manager.status(C).reconnect_count >= 99
    assert "Erro inesperado" in rig.manager.status(C).detail_pt


async def test_failing_after_good_values_shows_stale_with_original_value(rig: Rig) -> None:
    rig.registry.add(A, ok_factory(rig.logs[A]))
    rig.registry.add(B, exploding_factory(rig.logs[B], ok_reads=3))
    rig.registry.add(C, ok_factory(rig.logs[C]))

    await rig.manager.start_all()
    await run_for(rig.clock, 2)  # 3 leituras boas (t=0,1,2)
    good = rig.manager.live(B).samples["mass_flow"]
    assert good.quality is Quality.SIMULATED
    assert good.value is not None

    await run_for(rig.clock, 2)  # falhas começam
    status = rig.manager.status(B)
    assert status.connection is ConnectionState.ERROR
    assert status.is_stale is False
    live = rig.manager.live(B)
    assert live.samples["mass_flow"].quality is Quality.SIMULATED, "ainda fresco: não é STALE"
    assert live.samples["mass_flow"].value == good.value

    await run_for(rig.clock, 4)  # passou de stale_after_s (5 s) desde a última leitura boa
    status = rig.manager.status(B)
    assert status.is_stale is True
    assert status.stale_for_s is not None
    assert status.stale_for_s > 0
    live = rig.manager.live(B)
    stale = live.samples["mass_flow"]
    assert stale.quality is Quality.STALE
    assert stale.value == good.value
    assert stale.ts_utc == good.ts_utc
    assert live.ages_s["mass_flow"] is not None
    assert live.ages_s["mass_flow"] >= 5.0
    # os saudáveis seguem frescos
    assert rig.manager.status(A).is_stale is False
    assert rig.manager.status(C).connection is ConnectionState.CONNECTED


async def test_connection_changes_are_published_per_equipment(rig: Rig) -> None:
    rig.registry.add(A, ok_factory(rig.logs[A]))
    rig.registry.add(B, ok_factory(rig.logs[B]))
    rig.registry.add(C, exploding_factory(rig.logs[C]))

    await rig.manager.start_all()
    await run_for(rig.clock, 5)

    a_changes = [c for c in rig.connections.of(A) if isinstance(c, ConnectionChanged)]
    assert [c.current for c in a_changes] == [ConnectionState.CONNECTING, ConnectionState.CONNECTED]
    c_changes = [c.current for c in rig.connections.of(C)]
    assert ConnectionState.ERROR in c_changes
    assert ConnectionState.RECONNECTING in c_changes
    assert all(isinstance(b, SampleBatch) for b in rig.samples.items)
    assert len(rig.samples.of(A)) >= 5
    assert all(b.quality is Quality.COMM_ERROR for b in rig.samples.of(C))
    # comm_log do historian recebeu as transições
    assert any(e.equipment_id == C and e.level == "WARNING" for e in rig.historian.comm)


async def test_historian_failure_does_not_stop_acquisition(rig: Rig) -> None:
    rig.registry.add(A, ok_factory(rig.logs[A]))
    rig.registry.add(B, ok_factory(rig.logs[B]))
    rig.registry.add(C, ok_factory(rig.logs[C]))
    rig.historian.fail_writes = True

    await rig.manager.start_all()
    await run_for(rig.clock, 10)

    for eid in (A, B, C):
        assert rig.manager.status(eid).connection is ConnectionState.CONNECTED
        assert rig.logs[eid].reads >= 10
    assert len(rig.samples.of(A)) >= 10, "o bus continua recebendo mesmo com historian fora"


async def test_start_all_continues_when_one_driver_cannot_be_created(rig: Rig) -> None:
    def _broken(*_args: object) -> object:
        raise ValueError("fábrica quebrada (fake)")

    rig.registry.add(A, ok_factory(rig.logs[A]))
    rig.registry.add(B, _broken)  # type: ignore[arg-type]
    rig.registry.add(C, ok_factory(rig.logs[C]))

    await rig.manager.start_all()
    await run_for(rig.clock, 3)

    assert rig.manager.is_running(A)
    assert rig.manager.is_running(C)
    assert not rig.manager.is_running(B)
    status_b = rig.manager.status(B)
    assert status_b.connection is ConnectionState.ERROR
    assert "Falha ao criar o driver" in status_b.detail_pt


async def test_not_configured_profile_gets_honest_state(tmp_path: Path) -> None:
    clock = FakeClock()
    registry = FakeRegistry()
    registry.set_default(ok_factory())
    store = make_store(
        make_paths(tmp_path),
        [make_profile(A), make_profile(B, driver="modbus_tcp")],
    )
    manager = EquipmentManager(
        store, registry, InMemoryHistorian(), AsyncBus(), clock, pipeline=fake_pipeline()
    )
    await manager.start_all()
    await run_for(clock, 2)
    status_b = manager.status(B)
    assert status_b.connection is ConnectionState.NOT_CONFIGURED
    assert "Disponível após configuração de campo" in status_b.detail_pt
    assert not manager.is_running(B)
    assert manager.status(A).connection is ConnectionState.CONNECTED
    assert manager.live(B).samples == {}
    await manager.stop_all(timeout_s=1)


async def test_stop_all_is_graceful(rig: Rig) -> None:
    rig.registry.add(A, ok_factory(rig.logs[A]))
    rig.registry.add(B, ok_factory(rig.logs[B]))
    rig.registry.add(C, exploding_factory(rig.logs[C]))

    await rig.manager.start_all()
    await run_for(rig.clock, 3)
    tasks = [rig.manager.task_of(e) for e in (A, B, C)]

    await rig.manager.stop_all(timeout_s=1)
    await settle()

    assert all(t is not None and t.done() for t in tasks)
    for eid in (A, B, C):
        assert rig.manager.status(eid).connection is ConnectionState.DISCONNECTED
        assert not rig.manager.is_running(eid)
    assert rig.logs[A].disconnects >= 1
    assert rig.manager.watchdog.watched() == []
    # o último estado publicado de A foi DISCONNECTED
    assert rig.connections.of(A)[-1].current is ConnectionState.DISCONNECTED
    # live continua consultável após parada (idade visível)
    assert set(rig.manager.live(A).samples) == set(TAGS)
    # stop_all de novo é inofensivo
    await rig.manager.stop_all(timeout_s=1)


async def test_real_simulators_from_seed_config_three_equipments(tmp_path: Path) -> None:
    """Perfis-semente de config/ com o simulador real do bloco 1 (um em COMMUNICATION_FAILURE)."""
    pytest.importorskip("forja.drivers.registry", reason="bloco 1 (drivers) ainda não importa")
    pytest.importorskip("forja.normalization.normalizer", reason="bloco 1 (normalização) ausente")
    from forja.acquisition.loop import default_pipeline
    from forja.config import ConfigStore, resolve_paths
    from forja.drivers.registry import build_default_registry
    from forja.drivers.simulator.controls import SIMULATOR_CONTROLS

    store = ConfigStore(resolve_paths()).load_all()
    sims = {eid: p for eid, p in store.profiles.items() if p.communication.driver == "simulator"}
    if len(sims) < 3:
        pytest.skip("config/equipment não tem 3 perfis de simulador")
    failing = [
        eid
        for eid, p in sims.items()
        if str(p.communication.options.get("scenario", "")).upper() == "COMMUNICATION_FAILURE"
    ]
    if not failing:
        pytest.skip("nenhum perfil-semente em COMMUNICATION_FAILURE")
    for eid in sims:
        SIMULATOR_CONTROLS.forget(eid)

    clock = FakeClock()
    bus = AsyncBus()
    historian = InMemoryHistorian()
    manager = EquipmentManager(
        store,
        build_default_registry(),
        historian,
        bus,
        clock,
        pipeline=default_pipeline(),
        backoff_factory=lambda: Backoff(jitter=0.0, max_s=2.0),
    )
    try:
        await manager.start_all()
        await run_for(clock, 12)
        for eid in sims:
            status = manager.status(eid)
            live = manager.live(eid)
            if eid in failing:
                assert status.connection is ConnectionState.ERROR
                assert all(s.quality is Quality.COMM_ERROR for s in live.samples.values())
            else:
                assert status.connection is ConnectionState.CONNECTED, eid
                assert live.samples, eid
                assert all(s.quality is Quality.SIMULATED for s in live.samples.values()), eid
                assert await historian.count(eid) > 0
        assert not [s for s in historian.rows if s.quality is Quality.STALE]
    finally:
        await manager.stop_all(timeout_s=1)
        for eid in sims:
            SIMULATOR_CONTROLS.forget(eid)
