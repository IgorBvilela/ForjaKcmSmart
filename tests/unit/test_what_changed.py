"""Componente 'O QUE MUDOU': antes/agora/variacao e quem saiu do padrao primeiro."""

from __future__ import annotations

from forja.domain import Quality, Sample
from forja.events.what_changed import (
    compute_what_changed,
    delta_kind_for,
    delta_text_pt,
    fmt_number_pt,
)
from tests.fixtures.synthetic_batches import EQ, SOURCE, at


def sample(t: float, tag: str, value: float | None, quality: Quality = Quality.SIMULATED) -> Sample:
    return Sample(
        ts_utc=at(t), equipment_id=EQ, tag=tag, value=value, quality=quality, source=SOURCE
    )


def test_delta_kind_by_unit() -> None:
    assert delta_kind_for("mass_flow") == "pct"
    assert delta_kind_for("belt_load") == "pct"
    assert delta_kind_for("net_weight") == "pct"
    assert delta_kind_for("drive_command") == "points"
    assert delta_kind_for("rpm") == "abs"
    assert delta_kind_for("alarm_code") == "abs"


def test_before_is_median_of_baseline_and_delta_pct() -> None:
    pre = [sample(t, "belt_load", 2.0) for t in range(60)]
    pre += [sample(t, "belt_load", 1.6) for t in range(60, 71)]
    now = {"belt_load": sample(71, "belt_load", 1.2)}
    (item,) = compute_what_changed(pre, now, ["belt_load"])
    assert item.before == 2.0
    assert item.now == 1.2
    assert item.delta_kind == "pct"
    assert item.delta is not None
    assert round(item.delta, 1) == -40.0
    assert item.ts_start_utc == at(60)
    assert item.changed_first is True
    assert item.label_pt == "Material na correia"
    assert item.unit == "kg/m"
    assert "Antes: 2,00 kg/m" in item.text_pt
    assert "Agora: 1,20 kg/m" in item.text_pt


def test_ordered_by_departure_with_single_changed_first() -> None:
    pre: list[Sample] = []
    for t in range(80):
        pre.append(sample(t, "belt_load", 2.0 if t < 60 else 1.5))
        pre.append(sample(t, "drive_command", 50.0 if t < 65 else 65.0))
        pre.append(sample(t, "machine_state", 1))
    now = {
        "belt_load": sample(80, "belt_load", 1.2),
        "drive_command": sample(80, "drive_command", 70.0),
        "machine_state": sample(80, "machine_state", 1),
    }
    items = compute_what_changed(pre, now, ["machine_state", "drive_command", "belt_load"])
    assert [i.tag for i in items] == ["belt_load", "drive_command", "machine_state"]
    assert [i.changed_first for i in items] == [True, False, False]
    assert items[0].ts_start_utc == at(60)
    assert items[1].ts_start_utc == at(65)
    assert items[1].delta_kind == "points"
    assert items[1].delta == 20.0
    assert items[2].ts_start_utc is None
    assert items[2].delta == 0.0


def test_unchanged_tag_has_no_departure() -> None:
    pre = [sample(t, "rpm", 62.0) for t in range(30)]
    (item,) = compute_what_changed(pre, {"rpm": sample(30, "rpm", 62.0)}, ["rpm"])
    assert item.ts_start_utc is None
    assert item.changed_first is False
    assert item.delta == 0.0
    assert item.delta_kind == "abs"


def test_ignores_unusable_samples() -> None:
    pre = [sample(t, "rpm", 62.0) for t in range(20)]
    pre += [sample(t, "rpm", None, Quality.COMM_ERROR) for t in range(20, 25)]
    pre += [sample(t, "rpm", 999.0, Quality.BAD) for t in range(25, 30)]
    now = {"rpm": sample(30, "rpm", 0.0)}
    (item,) = compute_what_changed(pre, now, ["rpm"])
    assert item.before == 62.0
    assert item.now == 0.0
    assert item.delta == -62.0
    assert item.delta_kind == "abs"
    # agora com qualidade nao utilizavel vira None
    (bad,) = compute_what_changed(pre, {"rpm": sample(30, "rpm", 0.0, Quality.STALE)}, ["rpm"])
    assert bad.now is None
    assert bad.delta is None
    assert bad.delta_kind == "none"


def test_missing_now_gives_none_delta() -> None:
    pre = [sample(t, "mass_flow", 1300.0) for t in range(10)]
    (item,) = compute_what_changed(pre, {}, ["mass_flow"])
    assert item.before == 1300.0
    assert item.now is None
    assert item.delta is None
    assert item.delta_kind == "none"
    assert "sem variação mensurável" in item.text_pt


def test_duplicate_tags_collapse_and_unknown_order_is_input_order() -> None:
    pre = [sample(t, "rpm", 62.0) for t in range(10)]
    pre += [sample(t, "mass_flow", 1300.0) for t in range(10)]
    now = {"rpm": sample(10, "rpm", 62.0), "mass_flow": sample(10, "mass_flow", 1300.0)}
    items = compute_what_changed(pre, now, ["mass_flow", "rpm", "mass_flow"])
    assert [i.tag for i in items] == ["mass_flow", "rpm"]
    assert not any(i.changed_first for i in items)


def test_portuguese_number_and_delta_text() -> None:
    assert fmt_number_pt(1234.56, 1) == "1234,6"
    assert fmt_number_pt(None, 2) == "—"
    assert delta_text_pt(-40.0, "pct", "kg/m", 2) == "↓ 40,0%"
    assert delta_text_pt(20.0, "points", "%", 1) == "↑ 20 pontos"
    assert delta_text_pt(-62.0, "abs", "rpm", 0) == "↓ 62 rpm"
    assert delta_text_pt(0.0, "abs", "rpm", 0) == "= 0 rpm"
    assert delta_text_pt(None, "pct", "kg/h", 0) == "sem variação mensurável"
