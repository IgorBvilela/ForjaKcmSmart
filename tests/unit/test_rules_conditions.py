"""Cada condicao atomica do motor de regras, avaliada contra lotes sinteticos."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from forja.domain import Quality, SampleBatch, Severity, SourceRef
from forja.events.conditions import EvalContext, evaluate
from forja.events.prewindow import SampleBuffer
from forja.events.rules import Condition, Rule, load_rules
from tests.fixtures.synthetic_batches import (
    RULES_DIR,
    at,
    comm_error_batch,
    make_batch,
    normal_values,
)

ALLOWED = frozenset({Quality.GOOD, Quality.SIMULATED, Quality.UNCERTAIN})


def ctx_from(batches: list[SampleBatch], buffer_s: int = 180) -> EvalContext:
    buf = SampleBuffer(buffer_s)
    for b in batches:
        buf.add(b)
    last = batches[-1]
    return EvalContext(
        ts=last.ts_utc,
        now={s.tag: s for s in last.samples},
        batch_quality=last.quality,
        history=buf,
        allowed=ALLOWED,
    )


def run(values_by_second: dict[int, dict[str, float]], **kw: object) -> EvalContext:
    batches = [make_batch(at(t), v, **kw) for t, v in sorted(values_by_second.items())]  # type: ignore[arg-type]
    return ctx_from(batches)


def test_gt_true_and_false() -> None:
    cond = Condition(tag="drive_command", op="gt", value=85)
    assert evaluate(cond, run({0: {"drive_command": 90.0}})) is True
    assert evaluate(cond, run({0: {"drive_command": 80.0}})) is False


def test_lt_with_ref_tag_scales_threshold() -> None:
    cond = Condition(tag="mass_flow", op="lt", value=0.9, ref_tag="setpoint")
    assert evaluate(cond, run({0: {"mass_flow": 1100.0, "setpoint": 1300.0}})) is True
    assert evaluate(cond, run({0: {"mass_flow": 1200.0, "setpoint": 1300.0}})) is False


def test_lt_with_ref_tag_missing_is_false() -> None:
    cond = Condition(tag="mass_flow", op="lt", value=0.9, ref_tag="setpoint")
    assert evaluate(cond, run({0: {"mass_flow": 10.0}})) is False


def test_between_inclusive() -> None:
    cond = Condition(tag="rpm", op="between", value=50, value2=70)
    assert evaluate(cond, run({0: {"rpm": 60.0}})) is True
    assert evaluate(cond, run({0: {"rpm": 70.0}})) is True
    assert evaluate(cond, run({0: {"rpm": 80.0}})) is False


def test_equals_numeric_and_string() -> None:
    assert evaluate(
        Condition(tag="machine_state", op="equals", value=1), run({0: {"machine_state": 1}})
    )
    assert not evaluate(
        Condition(tag="machine_state", op="equals", value=1), run({0: {"machine_state": 0}})
    )
    assert evaluate(
        Condition(tag="machine_state", op="equals", value="1"), run({0: {"machine_state": 1}})
    )


def test_changed_to_value_and_changed_any() -> None:
    to_zero = Condition(tag="machine_state", op="changed", value=0)
    any_change = Condition(tag="machine_state", op="changed")
    ctx = run({0: {"machine_state": 1}, 1: {"machine_state": 0}})
    assert evaluate(to_zero, ctx) is True
    assert evaluate(any_change, ctx) is True
    # sem mudanca entre os dois ultimos lotes
    ctx_same = run({0: {"machine_state": 1}, 1: {"machine_state": 0}, 2: {"machine_state": 0}})
    assert evaluate(to_zero, ctx_same) is False
    # mudou, mas para outro valor
    ctx_other = run({0: {"machine_state": 1}, 1: {"machine_state": 2}})
    assert evaluate(to_zero, ctx_other) is False


def test_changed_without_history_is_false() -> None:
    cond = Condition(tag="machine_state", op="changed", value=0)
    assert evaluate(cond, run({0: {"machine_state": 0}})) is False


def test_quality_is_star_reads_batch_quality() -> None:
    cond = Condition(tag="*", op="quality_is", value="COMM_ERROR")
    assert evaluate(cond, ctx_from([comm_error_batch(at(0))])) is True
    assert evaluate(cond, run({0: normal_values(0)})) is False


def test_quality_is_specific_tag() -> None:
    cond = Condition(tag="rpm", op="quality_is", value="BAD")
    ctx = ctx_from(
        [make_batch(at(0), {"rpm": 5.0, "belt_load": 2.0}, qualities={"rpm": Quality.BAD})]
    )
    assert evaluate(cond, ctx) is True
    assert evaluate(Condition(tag="belt_load", op="quality_is", value="BAD"), ctx) is False


def test_drop_pct_over_window_relative_for_kg_per_m() -> None:
    cond = Condition(tag="belt_load", op="drop_pct_over_window", value=35, window_s=60)
    data = {t: {"belt_load": 2.0 if t < 30 else 1.0} for t in range(61)}
    assert evaluate(cond, run(data)) is True
    # queda pequena (10%) nao atende
    small = {t: {"belt_load": 2.0 if t < 30 else 1.8} for t in range(61)}
    assert evaluate(cond, run(small)) is False


def test_drop_pct_without_enough_history_is_false() -> None:
    cond = Condition(tag="belt_load", op="drop_pct_over_window", value=35, window_s=60)
    data = {t: {"belt_load": 2.0 if t < 5 else 1.0} for t in range(11)}
    assert evaluate(cond, run(data)) is False


def test_rise_pct_over_window_in_points_for_percent_tag() -> None:
    cond = Condition(tag="drive_command", op="rise_pct_over_window", value=15, window_s=60)
    data = {t: {"drive_command": 50.0 if t < 30 else 70.0} for t in range(61)}
    assert evaluate(cond, run(data)) is True
    strict = Condition(tag="drive_command", op="rise_pct_over_window", value=25, window_s=60)
    assert evaluate(strict, run(data)) is False


def test_rate_of_change_per_second() -> None:
    data = {t: {"rpm": 62.0 if t < 30 else 0.0} for t in range(61)}
    fast = Condition(tag="rpm", op="rate_of_change", value=0.5, window_s=60)
    slow = Condition(tag="rpm", op="rate_of_change", value=2.0, window_s=60)
    assert evaluate(fast, run(data)) is True
    assert evaluate(slow, run(data)) is False


def test_persists_for_frozen_value() -> None:
    cond = Condition(tag="rpm", op="persists_for", value=0, persist_s=5)
    frozen = {t: {"rpm": 0.0} for t in range(11)}
    assert evaluate(cond, run(frozen)) is True
    moving = {t: {"rpm": float(t)} for t in range(11)}
    assert evaluate(cond, run(moving)) is False
    short = {t: {"rpm": 0.0} for t in range(3)}
    assert evaluate(cond, run(short)) is False


@pytest.mark.parametrize("quality", [Quality.BAD, Quality.STALE, Quality.COMM_ERROR])
def test_value_conditions_ignore_disallowed_qualities(quality: Quality) -> None:
    cond = Condition(tag="drive_command", op="gt", value=85)
    ctx = run({0: {"drive_command": 95.0}}, quality=quality)
    assert evaluate(cond, ctx) is False


def test_condition_validation_rejects_bad_shapes() -> None:
    with pytest.raises(ValidationError):
        Condition(tag="*", op="gt", value=1)
    with pytest.raises(ValidationError):
        Condition(tag="belt_load", op="drop_pct_over_window", value=35)
    with pytest.raises(ValidationError):
        Condition(tag="tag_inexistente", op="gt", value=1)
    with pytest.raises(ValidationError):
        Condition(tag="*", op="quality_is", value="OTIMA")
    with pytest.raises(ValidationError):
        Condition(tag="rpm", op="between", value=1)


def _source() -> SourceRef:
    return SourceRef(id="SRC-T", kind="rule", title="Regra de teste", evidence_level="FORJA_RULE")


def test_rule_rejects_comm_error_in_allowed_qualities() -> None:
    with pytest.raises(ValidationError):
        Rule(
            id="R-TEST-001",
            internal_code="TESTE_REGRA",
            title_pt="Regra de teste",
            severity=Severity.INFO,
            conditions=[Condition(tag="rpm", op="gt", value=1)],
            allowed_qualities=[Quality.GOOD, Quality.COMM_ERROR],
            diagnosis_ref="x",
            sources=[_source()],
            summary_template_pt="t",
        )


def test_rule_rejects_title_equal_to_internal_code() -> None:
    with pytest.raises(ValidationError):
        Rule(
            id="R-TEST-001",
            internal_code="TESTE_REGRA",
            title_pt="TESTE_REGRA",
            severity=Severity.INFO,
            conditions=[Condition(tag="rpm", op="gt", value=1)],
            diagnosis_ref="x",
            sources=[_source()],
            summary_template_pt="t",
        )


def test_seed_rules_load_and_are_forja_rules() -> None:
    rules = load_rules(RULES_DIR)
    assert [r.id for r in rules] == [
        "R-BELTLOAD-001",
        "R-COMM-001",
        "R-DRIVE-001",
        "R-RATE-001",
        "R-SPEED-001",
        "R-STOP-001",
    ]
    for rule in rules:
        assert rule.threshold_basis == "FORJA_RULE"
        assert all(s.evidence_level == "FORJA_RULE" for s in rule.sources)
        assert rule.title_pt.upper() != rule.internal_code


def test_beltload_rule_tags_and_persistence() -> None:
    rule = next(r for r in load_rules(RULES_DIR) if r.id == "R-BELTLOAD-001")
    assert rule.tags == (
        "belt_load",
        "drive_command",
        "machine_state",
        "mass_flow",
        "rpm",
        "alarm_code",
    )
    assert rule.persist_s == 10
    assert rule.internal_code == "BELT_LOAD_LOW"
