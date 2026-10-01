"""Cenarios e modelo fisico do simulador WBF: 9 cenarios, determinismo, comportamento."""

from __future__ import annotations

import statistics

import pytest

from forja.domain import ConfigError, is_known_tag
from forja.drivers.simulator.physics_wbf import (
    SIM_ALARM_BAD_SFT_STATUS,
    SIM_ALARM_BELTLOAD_LOW,
    SIM_ALARM_NONE,
    SIM_MDU_STATUS_STOP,
    SIM_SFT_STATUS_FAULT,
    SIM_SFT_STATUS_NORMAL,
    SIM_STOP_BY_LABELS,
    SIM_STOP_BY_NONE,
    SIM_STOP_BY_STOP_INPUT,
    SIM_TAGS,
    SimMachineState,
    WbfModel,
    noise,
)
from forja.drivers.simulator.scenarios import SCENARIO_COUNT, Scenario, scenario_from_text
from tests.unit.block1_helpers import TEST_REFS

pytestmark = pytest.mark.unit

EXPECTED_SCENARIOS = frozenset(
    {
        "NORMAL_OPERATION",
        "BELTLOAD_LOW",
        "RATE_LOW",
        "ENCODER_FAILURE",
        "SFT_FAILURE",
        "DRIVE_COMMAND_HIGH",
        "INT_CHANNEL_DEGRADED",
        "COMMUNICATION_FAILURE",
        "STOP_NORMAL",
    }
)
SEED = 7
SETPOINT = TEST_REFS["setpoint_ref"]
BELT_LOAD_REF = TEST_REFS["belt_load_ref"]
RPM_REF = TEST_REFS["rpm_ref"]


@pytest.fixture
def model() -> WbfModel:
    return WbfModel(TEST_REFS)


def _rel(value: float, ref: float) -> float:
    return abs(value / ref - 1.0)


# --- cenarios ---------------------------------------------------------------------------------


def test_exactly_nine_scenarios() -> None:
    assert {s.value for s in Scenario} == EXPECTED_SCENARIOS
    assert len(Scenario) == 9
    assert SCENARIO_COUNT == 9


def test_refill_does_not_exist() -> None:
    assert "REFILL" not in Scenario.__members__
    with pytest.raises(ConfigError, match="desconhecido"):
        scenario_from_text("REFILL")


@pytest.mark.parametrize("scenario", list(Scenario))
def test_scenario_has_pt_texts_and_code_is_not_title(scenario: Scenario) -> None:
    assert scenario.title_pt.strip()
    assert scenario.description_pt.strip()
    assert scenario.title_pt != scenario.value
    assert scenario.value not in scenario.title_pt
    assert "_" not in scenario.title_pt


def test_scenario_from_text_normalizes_and_rejects() -> None:
    assert scenario_from_text(" beltload_low ") is Scenario.BELTLOAD_LOW
    assert scenario_from_text(Scenario.STOP_NORMAL) is Scenario.STOP_NORMAL
    with pytest.raises(ConfigError):
        scenario_from_text(None)
    with pytest.raises(ConfigError):
        scenario_from_text(42)


# --- modelo: estrutura e determinismo -------------------------------------------------------


def test_values_cover_all_sim_tags_and_tags_are_known(model: WbfModel) -> None:
    out = model.values(Scenario.NORMAL_OPERATION, 12.0, SEED)
    assert set(out) == set(SIM_TAGS)
    assert all(is_known_tag(tag) for tag in SIM_TAGS)


@pytest.mark.parametrize("scenario", list(Scenario))
def test_deterministic_by_seed(scenario: Scenario, model: WbfModel) -> None:
    other = WbfModel(TEST_REFS)
    for t in (0.0, 0.3, 17.5, 60.0, 120.0):
        a = model.values(scenario, t, SEED)
        b = model.values(scenario, t, SEED)
        c = other.values(scenario, t, SEED)
        assert a == b == c


def test_different_seed_changes_noise(model: WbfModel) -> None:
    a = [model.values(Scenario.NORMAL_OPERATION, t, 1)["mass_flow"] for t in range(30)]
    b = [model.values(Scenario.NORMAL_OPERATION, t, 2)["mass_flow"] for t in range(30)]
    assert a != b


def test_noise_is_bounded_and_deterministic() -> None:
    samples = [noise(SEED, "mass_flow", t / 10) for t in range(600)]
    assert all(-1.0 <= s <= 1.0 for s in samples)
    assert noise(SEED, "mass_flow", 3.3) == noise(SEED, "mass_flow", 3.3)
    assert noise(SEED, "mass_flow", 3.3) != noise(SEED + 1, "mass_flow", 3.3)


def test_negative_time_is_clamped_to_zero(model: WbfModel) -> None:
    assert model.values(Scenario.BELTLOAD_LOW, -5.0, SEED) == model.values(
        Scenario.BELTLOAD_LOW, 0.0, SEED
    )


# --- cenarios: comportamento ----------------------------------------------------------------


@pytest.mark.parametrize("t", [0.0, 30.0, 300.0])
def test_normal_operation(model: WbfModel, t: float) -> None:
    out = model.values(Scenario.NORMAL_OPERATION, t, SEED)
    assert out["machine_state"] == SimMachineState.RUN
    assert _rel(out["mass_flow"], SETPOINT) < 0.02
    assert _rel(out["belt_load"], BELT_LOAD_REF) < 0.02
    assert _rel(out["rpm"], RPM_REF) < 0.02
    assert out["alarm_code"] == SIM_ALARM_NONE
    assert out["alarm_active"] == 0
    assert out["stop_by"] == SIM_STOP_BY_NONE
    assert out["sft_status"] == SIM_SFT_STATUS_NORMAL


def test_beltload_low_reduces_belt_load_and_raises_drive(model: WbfModel) -> None:
    t0 = model.values(Scenario.BELTLOAD_LOW, 0.0, SEED)
    t60 = model.values(Scenario.BELTLOAD_LOW, 60.0, SEED)
    t90 = model.values(Scenario.BELTLOAD_LOW, 90.0, SEED)
    assert _rel(t0["belt_load"], BELT_LOAD_REF) < 0.02
    assert _rel(t90["belt_load"], 0.45 * BELT_LOAD_REF) < 0.05
    assert t90["drive_command"] - t0["drive_command"] >= 15.0
    assert t90["mass_flow"] >= 0.95 * SETPOINT
    assert t90["machine_state"] == SimMachineState.RUN
    # queda progressiva
    loads = [model.values(Scenario.BELTLOAD_LOW, t, SEED)["belt_load"] for t in (10, 30, 60)]
    assert loads[0] > loads[1] > loads[2]
    # alarme simulado 56 so depois de persistir
    assert t60["alarm_code"] == SIM_ALARM_NONE
    assert t60["alarm_active"] == 0
    assert t90["alarm_code"] == SIM_ALARM_BELTLOAD_LOW == 56
    assert t90["alarm_active"] == 1


def test_encoder_failure_rpm_zero_with_drive_positive(model: WbfModel) -> None:
    before = model.values(Scenario.ENCODER_FAILURE, 10.0, SEED)
    after = model.values(Scenario.ENCODER_FAILURE, 30.0, SEED)
    assert before["rpm"] > 0
    assert after["rpm"] == 0
    assert after["drive_command"] > 0
    assert after["machine_state"] == SimMachineState.RUN
    assert after["mass_flow"] > 0


def test_rate_low_flow_below_setpoint_with_drive_at_ceiling(model: WbfModel) -> None:
    for t in (30.0, 60.0, 120.0):
        out = model.values(Scenario.RATE_LOW, t, SEED)
        assert 0.75 <= out["mass_flow"] / SETPOINT <= 0.85
        assert out["drive_command"] >= 99.0
        assert out["machine_state"] == SimMachineState.RUN


def test_sft_failure_changes_raw_status_and_alarm_after_persistence(model: WbfModel) -> None:
    t10 = model.values(Scenario.SFT_FAILURE, 10.0, SEED)
    t35 = model.values(Scenario.SFT_FAILURE, 35.0, SEED)
    t50 = model.values(Scenario.SFT_FAILURE, 50.0, SEED)
    assert t10["sft_status"] == SIM_SFT_STATUS_NORMAL == 0x0000_0181
    assert t10["alarm_code"] == SIM_ALARM_NONE
    assert t35["sft_status"] == SIM_SFT_STATUS_FAULT == 0x0000_0183
    assert t35["alarm_code"] == SIM_ALARM_NONE
    assert t50["alarm_code"] == SIM_ALARM_BAD_SFT_STATUS == 8
    assert t50["alarm_active"] == 1
    normal = [
        model.values(Scenario.NORMAL_OPERATION, t / 2, SEED)["net_weight"] for t in range(80, 120)
    ]
    faulty = [model.values(Scenario.SFT_FAILURE, t / 2, SEED)["net_weight"] for t in range(80, 120)]
    assert statistics.pstdev(faulty) > 5 * statistics.pstdev(normal)


def test_drive_command_high_between_88_and_96_with_flow_at_setpoint(model: WbfModel) -> None:
    for t in range(20, 125, 5):
        out = model.values(Scenario.DRIVE_COMMAND_HIGH, float(t), SEED)
        assert 88.0 <= out["drive_command"] <= 96.0, (t, out["drive_command"])
        assert _rel(out["mass_flow"], SETPOINT) <= 0.02


def test_int_channel_degraded_drops_from_95_to_40(model: WbfModel) -> None:
    t0 = model.values(Scenario.INT_CHANNEL_DEGRADED, 0.0, SEED)
    t90 = model.values(Scenario.INT_CHANNEL_DEGRADED, 90.0, SEED)
    assert 94.0 <= t0["int_channel_pct"] <= 96.0
    assert 39.0 <= t90["int_channel_pct"] <= 41.0
    assert _rel(t90["mass_flow"], SETPOINT) < 0.02
    assert t90["alarm_code"] == SIM_ALARM_NONE


def test_communication_failure_model_is_pure_and_driver_is_who_fails(model: WbfModel) -> None:
    # O modelo nao sabe falhar; quem levanta DriverTimeout e o driver (test_simulator_driver).
    out = model.values(Scenario.COMMUNICATION_FAILURE, 10.0, SEED)
    assert set(out) == set(SIM_TAGS)


def test_stop_normal_everything_zero_except_belt_load(model: WbfModel) -> None:
    out = model.values(Scenario.STOP_NORMAL, 42.0, SEED)
    assert out["machine_state"] == SimMachineState.STOP == 0
    assert out["mass_flow"] == 0
    assert out["rpm"] == 0
    assert out["drive_command"] == 0
    assert out["stop_by"] == SIM_STOP_BY_STOP_INPUT
    assert SIM_STOP_BY_LABELS[out["stop_by"]] == "Stop Input"
    assert _rel(out["belt_load"], BELT_LOAD_REF) < 0.02
    assert out["mdu_status"] == SIM_MDU_STATUS_STOP
    assert out["alarm_code"] == SIM_ALARM_NONE


def test_machine_state_encoding_is_documented_and_no_scenario_emits_alarm_state(
    model: WbfModel,
) -> None:
    assert (SimMachineState.STOP, SimMachineState.RUN, SimMachineState.ALARM) == (0, 1, 2)
    for scenario in Scenario:
        state = model.values(scenario, 100.0, SEED)["machine_state"]
        assert state in (SimMachineState.STOP, SimMachineState.RUN)


def test_overrides_fix_tags_and_unknown_is_ignored(model: WbfModel) -> None:
    out = model.values(
        Scenario.NORMAL_OPERATION, 5.0, SEED, {"belt_load": 0.3, "rpm": 12, "foo": 1.0}
    )
    assert out["belt_load"] == 0.3
    assert out["rpm"] == 12.0
    assert "foo" not in out
    assert _rel(out["mass_flow"], SETPOINT) < 0.02


@pytest.mark.parametrize(
    "refs",
    [
        {"setpoint_ref": 0},
        {"rpm_ref": -1},
        {"belt_load_ref": float("nan")},
        {"setpoint_ref": float("inf")},
    ],
)
def test_invalid_reference_values_raise(refs: dict[str, float]) -> None:
    with pytest.raises(ValueError, match="deve ser > 0"):
        WbfModel(refs)


def test_default_refs_when_profile_has_none() -> None:
    out = WbfModel(None).values(Scenario.NORMAL_OPERATION, 0.0, SEED)
    assert out["setpoint"] > 0
    assert out["mass_flow"] > 0
