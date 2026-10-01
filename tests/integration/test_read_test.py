"""TESTAR SOMENTE LEITURA: estágios ReadTestStage, valores lidos, nunca escreve."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from forja.acquisition.manager import EquipmentManager
from forja.acquisition.test_read import ReadTestResult, run_read_test
from forja.domain import (
    DriverTimeout,
    NotConfigured,
    Quality,
    ReadTestStage,
    UnsupportedDriver,
)
from forja.domain.ports import ALLOWED_DRIVER_PUBLIC
from forja.infra import AsyncBus, FakeClock
from tests.fixtures.acquisition_fakes import (
    TAGS,
    DriverLog,
    FakeRegistry,
    InMemoryHistorian,
    exploding_factory,
    fake_pipeline,
    make_mapping,
    make_paths,
    make_profile,
    make_store,
    ok_factory,
    refusing_factory,
    run_for,
)

pytestmark = pytest.mark.integration

A = "EQ_A"


async def _run(factory: object, clock: FakeClock | None = None) -> ReadTestResult:
    clock = clock or FakeClock()
    registry = FakeRegistry()
    registry.add(A, factory)  # type: ignore[arg-type]
    return await run_read_test(
        make_profile(A), make_mapping(), registry=registry, pipeline=fake_pipeline(), clock=clock
    )


async def test_read_obtained_with_fake_driver() -> None:
    log = DriverLog()
    result = await _run(ok_factory(log))
    assert result.final is ReadTestStage.READ_OBTAINED
    assert result.ok is True
    assert [s for s, _, _ in result.stages] == [
        ReadTestStage.CONNECTING,
        ReadTestStage.HANDSHAKE,
        ReadTestStage.SESSION_CREATED,
        ReadTestStage.READ_OBTAINED,
    ]
    assert set(result.values) == set(TAGS)
    assert all(s.quality is Quality.SIMULATED for s in result.values.values())
    assert result.latency_ms is not None
    assert result.latency_ms > 0
    assert result.error_pt is None
    assert log.connects == 1
    assert log.disconnects == 1
    assert log.reads == 1
    assert all(text for _, _, text in result.stages), "todo estágio tem texto em português"


async def test_timeout_with_driver_that_raises() -> None:
    log = DriverLog()
    result = await _run(exploding_factory(log, exc_factory=lambda: DriverTimeout("fake")))
    assert result.final is ReadTestStage.TIMEOUT
    assert result.ok is False
    assert result.values == {}
    assert result.latency_ms is None
    assert result.error_pt is not None
    assert "Timeout" in result.error_pt
    assert "Tempo esgotado" in result.error_pt
    assert [s for s, _, _ in result.stages][-1] is ReadTestStage.TIMEOUT
    assert ReadTestStage.SESSION_CREATED in [s for s, _, _ in result.stages]
    assert log.disconnects == 1, "driver descartável é sempre desconectado"


async def test_connection_refused_stage() -> None:
    result = await _run(refusing_factory())
    assert result.final is ReadTestStage.CONNECTION_REFUSED
    assert [s for s, _, _ in result.stages] == [
        ReadTestStage.CONNECTING,
        ReadTestStage.CONNECTION_REFUSED,
    ]
    assert result.error_pt is not None
    assert "Não foi possível conectar" in result.error_pt


async def test_invalid_response_and_unidentified_stages() -> None:
    invalid = await _run(exploding_factory(exc_factory=lambda: ValueError("bytes ruins")))
    assert invalid.final is ReadTestStage.INVALID_RESPONSE
    assert invalid.error_pt is not None
    assert "Resposta inválida" in invalid.error_pt

    weird = await _run(exploding_factory(exc_factory=lambda: RuntimeError("???")))
    assert weird.final is ReadTestStage.UNIDENTIFIED
    assert weird.error_pt is not None
    assert "Erro inesperado" in weird.error_pt


async def test_needs_configuration_raises_not_configured() -> None:
    registry = FakeRegistry()
    with pytest.raises(NotConfigured):
        await run_read_test(
            make_profile(A, driver="modbus_tcp"),
            make_mapping(),
            registry=registry,
            pipeline=fake_pipeline(),
            clock=FakeClock(),
        )
    assert registry.create_calls == {}, "sem IP/protocolo nem tenta criar driver"


async def test_unsupported_driver_propagates() -> None:
    registry = FakeRegistry()  # sem factory para A -> UnsupportedDriver
    with pytest.raises(UnsupportedDriver):
        await run_read_test(
            make_profile(A),
            make_mapping(),
            registry=registry,
            pipeline=fake_pipeline(),
            clock=FakeClock(),
        )


async def test_stage_timestamps_come_from_clock() -> None:
    clock = FakeClock()
    result = await _run(ok_factory(), clock)
    assert all(ts == clock.now_utc() for _, ts, _ in result.stages)


async def test_manager_test_read_does_not_touch_running_loops(tmp_path: Path) -> None:
    clock = FakeClock()
    registry = FakeRegistry()
    running_log, test_log = DriverLog(), DriverLog()
    registry.add(A, ok_factory(running_log), ok_factory(test_log), ok_factory(test_log))
    store = make_store(make_paths(tmp_path), [make_profile(A)])
    manager = EquipmentManager(
        store, registry, InMemoryHistorian(), AsyncBus(), clock, pipeline=fake_pipeline()
    )
    try:
        await manager.start_all()
        await run_for(clock, 2)
        reads_before = running_log.reads
        task_before = manager.task_of(A)
        result = await manager.test_read(make_profile(A), make_mapping())
        assert result.final is ReadTestStage.READ_OBTAINED
        assert test_log.reads == 1
        assert test_log.disconnects == 1
        assert manager.task_of(A) is task_before
        assert running_log.disconnects == 0, "o driver em produção não foi desconectado"
        await run_for(clock, 1)
        assert running_log.reads > reads_before
    finally:
        await manager.stop_all(timeout_s=1)


def test_read_test_result_is_frozen_and_forbids_extras() -> None:
    result = ReadTestResult(
        stages=[], final=ReadTestStage.UNIDENTIFIED, values={}, latency_ms=None, error_pt="x"
    )
    with pytest.raises(ValidationError):
        result.final = ReadTestStage.READ_OBTAINED  # type: ignore[misc]
    with pytest.raises(ValidationError):
        ReadTestResult(
            stages=[],
            final=ReadTestStage.TIMEOUT,
            values={},
            latency_ms=None,
            error_pt=None,
            write=True,  # type: ignore[call-arg]
        )


# --- simulador real do bloco 1 (se já importar) ---------------------------------------------


def _real_profile(equipment_id: str, scenario: str) -> object:
    return make_profile(
        equipment_id, mapping_id="sim_rt", options={"scenario": scenario, "seed": 3}
    )


def _real_mapping() -> object:
    return make_mapping("sim_rt", tags=("machine_state", "mass_flow", "belt_load", "rpm"))


@pytest.fixture
def real_registry_pipeline() -> tuple[object, object]:
    pytest.importorskip("forja.drivers.registry", reason="bloco 1 (drivers) ainda não importa")
    pytest.importorskip("forja.normalization.normalizer", reason="bloco 1 (normalização) ausente")
    from forja.acquisition.loop import default_pipeline
    from forja.drivers.registry import build_default_registry

    return build_default_registry(), default_pipeline()


async def test_real_simulator_read_obtained(real_registry_pipeline: tuple[object, object]) -> None:
    from forja.drivers.simulator.controls import SIMULATOR_CONTROLS

    eid = "RT_SIM_OK"
    SIMULATOR_CONTROLS.forget(eid)
    registry, pipeline = real_registry_pipeline
    try:
        result = await run_read_test(
            _real_profile(eid, "NORMAL_OPERATION"),  # type: ignore[arg-type]
            _real_mapping(),  # type: ignore[arg-type]
            registry=registry,  # type: ignore[arg-type]
            pipeline=pipeline,  # type: ignore[arg-type]
            clock=FakeClock(),
        )
    finally:
        SIMULATOR_CONTROLS.forget(eid)
    assert result.final is ReadTestStage.READ_OBTAINED
    assert set(result.values) == {"machine_state", "mass_flow", "belt_load", "rpm"}
    assert all(s.quality is Quality.SIMULATED for s in result.values.values())
    assert result.values["mass_flow"].value is not None
    assert result.values["mass_flow"].value > 0


async def test_real_simulator_communication_failure_is_timeout(
    real_registry_pipeline: tuple[object, object],
) -> None:
    from forja.drivers.simulator.controls import SIMULATOR_CONTROLS

    eid = "RT_SIM_FAIL"
    SIMULATOR_CONTROLS.forget(eid)
    registry, pipeline = real_registry_pipeline
    try:
        result = await run_read_test(
            _real_profile(eid, "COMMUNICATION_FAILURE"),  # type: ignore[arg-type]
            _real_mapping(),  # type: ignore[arg-type]
            registry=registry,  # type: ignore[arg-type]
            pipeline=pipeline,  # type: ignore[arg-type]
            clock=FakeClock(),
        )
    finally:
        SIMULATOR_CONTROLS.forget(eid)
    assert result.final is ReadTestStage.TIMEOUT
    assert result.values == {}
    assert result.error_pt is not None
    assert "Tempo esgotado" in result.error_pt


def test_real_simulator_surface_is_read_only(real_registry_pipeline: tuple[object, object]) -> None:
    from forja.drivers.simulator.controls import SIMULATOR_CONTROLS

    eid = "RT_SIM_SURFACE"
    SIMULATOR_CONTROLS.forget(eid)
    registry, _ = real_registry_pipeline
    try:
        driver = registry.create(  # type: ignore[attr-defined]
            _real_profile(eid, "NORMAL_OPERATION"), _real_mapping(), FakeClock()
        )
    finally:
        SIMULATOR_CONTROLS.forget(eid)
    public = {n for n in dir(driver) if not n.startswith("_")}
    assert public == set(ALLOWED_DRIVER_PUBLIC)
