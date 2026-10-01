"""SimulatorDriver: superficie read-only, tempo pelo Clock, cenarios e controles."""

from __future__ import annotations

import pytest

from forja.domain import (
    ConfigError,
    DriverReadError,
    DriverSupportState,
    DriverTimeout,
    EquipmentProfile,
    Mapping,
    RawFrame,
    ReadBlock,
    ReadOnlyDriver,
    ReadPlan,
)
from forja.drivers.registry import public_surface
from forja.drivers.simulator import (
    SIMULATOR_CONTROLS,
    Scenario,
    SimulatorControlRegistry,
    SimulatorDriver,
    WbfModel,
)
from forja.drivers.simulator.controls import SLIDER_TAGS
from forja.infra.clock import FakeClock
from forja.normalization import ReadPlanCompiler
from tests.unit.block1_helpers import TEST_REFS, load_sim_mapping, sim_profile

pytestmark = pytest.mark.unit

CONTRACT_SURFACE = frozenset({"name", "connect", "disconnect", "read", "health", "capabilities"})


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def mapping() -> Mapping:
    return load_sim_mapping()


@pytest.fixture
def controls() -> SimulatorControlRegistry:
    return SimulatorControlRegistry()


def _make(
    profile: EquipmentProfile,
    mapping: Mapping,
    clock: FakeClock,
    controls: SimulatorControlRegistry,
) -> tuple[SimulatorDriver, ReadPlan]:
    driver = SimulatorDriver(profile, mapping, clock, controls=controls)
    plan = ReadPlanCompiler().compile(profile, mapping)
    return driver, plan


def _payload(frame: RawFrame) -> dict[str, float | None]:
    payload = frame.blocks["sim"].payload
    assert isinstance(payload, dict)
    return payload


def test_public_surface_is_exactly_the_contract() -> None:
    assert public_surface(SimulatorDriver) == CONTRACT_SURFACE
    assert SimulatorDriver.name == "simulator"


async def test_read_requires_connect(mapping: Mapping, clock: FakeClock, controls) -> None:
    driver, plan = _make(sim_profile(), mapping, clock, controls)
    with pytest.raises(DriverReadError, match="sem conexão"):
        await driver.read(plan)


async def test_read_returns_one_block_per_plan_block_with_all_tags(
    mapping: Mapping, clock: FakeClock, controls
) -> None:
    profile = sim_profile()
    driver, plan = _make(profile, mapping, clock, controls)
    await driver.connect()
    frame = await driver.read(plan)
    assert isinstance(driver, ReadOnlyDriver)
    assert frame.equipment_id == profile.id
    assert set(frame.blocks) == {b.block_id for b in plan.blocks} == {"sim"}
    assert set(_payload(frame)) == set(plan.tags)
    assert len(plan.tags) == len(mapping.readable_entries) == 14
    block = frame.blocks["sim"]
    assert frame.ts_utc == block.ts_utc == clock.now_utc()
    assert block.ts_mono_ns == clock.monotonic_ns()
    assert frame.latency_ms == block.latency_ms
    assert all(v is not None for v in _payload(frame).values())


async def test_payload_only_contains_tags_of_each_block(
    mapping: Mapping, clock: FakeClock, controls
) -> None:
    profile = sim_profile()
    driver, _ = _make(profile, mapping, clock, controls)
    plan = ReadPlan(
        equipment_id=profile.id,
        mapping_id="parcial",
        mapping_version=1,
        blocks=(
            ReadBlock(block_id="b1", area="sim", address="sim", count=2, tags=("rpm", "mass_flow")),
            ReadBlock(block_id="b2", area="sim", address="sim", count=1, tags=("belt_load",)),
        ),
    )
    await driver.connect()
    frame = await driver.read(plan)
    assert set(frame.blocks) == {"b1", "b2"}
    assert set(frame.blocks["b1"].payload) == {"rpm", "mass_flow"}
    assert set(frame.blocks["b2"].payload) == {"belt_load"}


async def test_health_and_capabilities(mapping: Mapping, clock: FakeClock, controls) -> None:
    driver, plan = _make(sim_profile(), mapping, clock, controls)
    before = await driver.health()
    assert before.connected is False
    assert before.last_ok_utc is None
    caps = driver.capabilities()
    assert caps.protocol == "simulator"
    assert caps.support_state is DriverSupportState.AVAILABLE
    assert caps.read_areas == ("sim",)
    assert "simulad" in caps.note_pt.lower()

    await driver.connect()
    await driver.read(plan)
    health = await driver.health()
    assert health.connected is True
    assert health.last_ok_utc == clock.now_utc()
    assert health.consecutive_errors == 0
    assert health.latency_ms is not None
    assert 0.0 < health.latency_ms < 5.0

    await driver.disconnect()
    after = await driver.health()
    assert after.connected is False
    assert after.last_ok_utc == clock.now_utc()


async def test_communication_failure_raises_driver_timeout(
    mapping: Mapping, clock: FakeClock, controls
) -> None:
    driver, plan = _make(sim_profile(scenario="COMMUNICATION_FAILURE"), mapping, clock, controls)
    await driver.connect()
    for _ in range(3):
        with pytest.raises(DriverTimeout, match="Tempo esgotado"):
            await driver.read(plan)
    health = await driver.health()
    assert health.connected is True
    assert health.consecutive_errors == 3
    assert health.last_ok_utc is None
    assert "Tempo esgotado" in health.detail_pt


async def test_time_comes_from_clock_not_from_sleep(
    mapping: Mapping, clock: FakeClock, controls
) -> None:
    driver, plan = _make(sim_profile(scenario="BELTLOAD_LOW"), mapping, clock, controls)
    await driver.connect()
    first = _payload(await driver.read(plan))
    again = _payload(await driver.read(plan))
    assert first == again  # sem avancar o relogio, nada muda
    clock.advance(90.0)
    later = _payload(await driver.read(plan))
    assert later["belt_load"] < 0.5 * first["belt_load"]
    assert later["drive_command"] > first["drive_command"] + 15
    assert later["alarm_code"] == 56
    assert later["alarm_active"] == 1


async def test_time_scale_multiplies_elapsed_time(
    mapping: Mapping, clock: FakeClock, controls
) -> None:
    profile = sim_profile(scenario="BELTLOAD_LOW", time_scale=10.0)
    driver, plan = _make(profile, mapping, clock, controls)
    await driver.connect()
    clock.advance(9.0)
    payload = _payload(await driver.read(plan))
    seed = profile.communication.options["seed"]
    expected = WbfModel(TEST_REFS).values(Scenario.BELTLOAD_LOW, 90.0, seed)
    assert payload == expected


async def test_set_scenario_restarts_elapsed_time(
    mapping: Mapping, clock: FakeClock, controls
) -> None:
    profile = sim_profile()
    driver, plan = _make(profile, mapping, clock, controls)
    await driver.connect()
    clock.advance(100.0)
    controls.set_scenario(profile.id, Scenario.ENCODER_FAILURE, clock)
    assert controls.get(profile.id).elapsed_s(clock) == 0.0
    fresh = _payload(await driver.read(plan))
    assert fresh["rpm"] > 0  # t < 20 s no novo cenario
    clock.advance(25.0)
    broken = _payload(await driver.read(plan))
    assert broken["rpm"] == 0
    assert broken["drive_command"] > 0
    health = await driver.health()
    assert Scenario.ENCODER_FAILURE.title_pt in health.detail_pt


async def test_overrides_via_controls(mapping: Mapping, clock: FakeClock, controls) -> None:
    profile = sim_profile()
    driver, plan = _make(profile, mapping, clock, controls)
    await driver.connect()
    controls.set_overrides(profile.id, {"belt_load": 0.123, "rpm": 5})
    payload = _payload(await driver.read(plan))
    assert payload["belt_load"] == 0.123
    assert payload["rpm"] == 5.0
    controls.clear_overrides(profile.id)
    payload = _payload(await driver.read(plan))
    assert payload["belt_load"] != 0.123
    with pytest.raises(ValueError, match="sliders desconhecidos"):
        controls.set_overrides(profile.id, {"alarm_code": 1.0})
    with pytest.raises(ValueError, match="não numérico"):
        controls.set_overrides(profile.id, {"rpm": float("nan")})
    assert set(SLIDER_TAGS) == {
        "setpoint",
        "mass_flow",
        "drive_command",
        "rpm",
        "belt_load",
        "net_weight",
        "int_channel_pct",
    }


async def test_two_drivers_same_seed_produce_identical_frames(
    mapping: Mapping, clock: FakeClock
) -> None:
    profile = sim_profile()
    driver_a, plan = _make(profile, mapping, clock, SimulatorControlRegistry())
    driver_b, _ = _make(profile, mapping, clock, SimulatorControlRegistry())
    await driver_a.connect()
    await driver_b.connect()
    for _ in range(5):
        clock.advance(1.0)
        fa = await driver_a.read(plan)
        fb = await driver_b.read(plan)
        assert _payload(fa) == _payload(fb)
        assert fa.latency_ms == fb.latency_ms


async def test_different_seed_produces_different_frames(mapping: Mapping, clock: FakeClock) -> None:
    driver_a, plan = _make(sim_profile(seed=1), mapping, clock, SimulatorControlRegistry())
    driver_b, _ = _make(sim_profile(seed=2), mapping, clock, SimulatorControlRegistry())
    await driver_a.connect()
    await driver_b.connect()
    clock.advance(3.0)
    assert _payload(await driver_a.read(plan)) != _payload(await driver_b.read(plan))


@pytest.mark.parametrize(
    "options",
    [
        {"scenario": "REFILL", "seed": 1},
        {"scenario": "NORMAL_OPERATION", "seed": "7"},
        {"scenario": "NORMAL_OPERATION", "seed": True},
        {"scenario": "NORMAL_OPERATION", "seed": 1, "time_scale": 0},
        {"scenario": "NORMAL_OPERATION", "seed": 1, "time_scale": 5000},
        {"scenario": "NORMAL_OPERATION", "seed": 1, "time_scale": "rapido"},
    ],
)
def test_invalid_options_raise_config_error(
    mapping: Mapping, clock: FakeClock, controls, options: dict[str, object]
) -> None:
    profile = sim_profile()
    profile = profile.model_copy(
        update={"communication": profile.communication.model_copy(update={"options": options})}
    )
    with pytest.raises(ConfigError):
        SimulatorDriver(profile, mapping, clock, controls=controls)


def test_invalid_reference_values_raise_config_error(
    mapping: Mapping, clock: FakeClock, controls
) -> None:
    with pytest.raises(ConfigError, match="setpoint_ref"):
        SimulatorDriver(sim_profile(refs={"setpoint_ref": 0}), mapping, clock, controls=controls)


def test_default_controls_singleton_is_used_when_none_given(
    mapping: Mapping, clock: FakeClock
) -> None:
    profile = sim_profile("SIM_TESTE_SINGLETON", scenario="RATE_LOW", seed=3)
    SIMULATOR_CONTROLS.forget(profile.id)
    try:
        SimulatorDriver(profile, mapping, clock)
        state = SIMULATOR_CONTROLS.get(profile.id)
        assert state.scenario is Scenario.RATE_LOW
        assert state.seed == 3
        assert state.scenario_started_mono_ns == clock.monotonic_ns()
    finally:
        SIMULATOR_CONTROLS.forget(profile.id)
    assert not SIMULATOR_CONTROLS.has(profile.id)


def test_existing_controls_are_not_overwritten_by_new_driver(
    mapping: Mapping, clock: FakeClock, controls
) -> None:
    profile = sim_profile(scenario="NORMAL_OPERATION")
    controls.set_scenario(profile.id, Scenario.STOP_NORMAL, clock)
    SimulatorDriver(profile, mapping, clock, controls=controls)
    assert controls.get(profile.id).scenario is Scenario.STOP_NORMAL
