"""Componente 'O QUE MUDOU': antes/agora/variacao e quem saiu do padrao primeiro.

Discretas (estado, alarme, modo) so entram quando mudaram, em palavras, sem decimais.
"""

from __future__ import annotations

import re

from forja.domain import Quality, Sample
from forja.events.what_changed import (
    compute_what_changed,
    delta_kind_for,
    delta_text_pt,
    discrete_value_pt,
    fmt_number_pt,
)
from tests.fixtures.synthetic_batches import EQ, SOURCE, at

DECIMAL = re.compile(r"\d,\d")


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
    # discretas e status brutos nao tem variacao numerica
    assert delta_kind_for("alarm_code") == "none"
    assert delta_kind_for("machine_state") == "none"
    assert delta_kind_for("stop_by") == "none"


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
    # machine_state nao mudou: discreta sem mudanca fica de fora
    assert [i.tag for i in items] == ["belt_load", "drive_command"]
    assert [i.changed_first for i in items] == [True, False]
    assert items[0].ts_start_utc == at(60)
    assert items[1].ts_start_utc == at(65)
    assert items[1].delta_kind == "points"
    assert items[1].delta == 20.0


def test_discrete_enters_only_when_changed_and_in_words() -> None:
    pre = [sample(t, "machine_state", 1) for t in range(10)]
    pre += [sample(t, "machine_state", 0) for t in range(10, 15)]
    (item,) = compute_what_changed(
        pre, {"machine_state": sample(15, "machine_state", 0)}, ["machine_state"]
    )
    assert item.text_pt == "passou de Em operação para Parado"
    assert item.before == 1.0
    assert item.now == 0.0
    assert item.delta is None
    assert item.delta_kind == "none"
    assert item.ts_start_utc == at(10)
    assert item.changed_first is True
    assert not DECIMAL.search(item.text_pt)


def test_discrete_changed_on_detection_batch_starts_now() -> None:
    pre = [sample(t, "machine_state", 1) for t in range(5)]
    (item,) = compute_what_changed(
        pre, {"machine_state": sample(5, "machine_state", 2)}, ["machine_state"]
    )
    assert item.text_pt == "passou de Em operação para Em alarme"
    assert item.ts_start_utc == at(5)


def test_discrete_without_history_or_usable_now_is_excluded() -> None:
    pre = [sample(t, "alarm_active", 0) for t in range(5)]
    assert (
        compute_what_changed([], {"alarm_active": sample(5, "alarm_active", 1)}, ["alarm_active"])
        == ()
    )
    stale_now = {"alarm_active": sample(5, "alarm_active", 1, Quality.STALE)}
    assert compute_what_changed(pre, stale_now, ["alarm_active"]) == ()
    assert compute_what_changed(pre, {}, ["alarm_active"]) == ()


def test_alarm_code_in_words_with_catalog_detail() -> None:
    pre = [sample(t, "alarm_code", 0) for t in range(20)]
    pre += [sample(t, "alarm_code", 56) for t in range(20, 25)]
    now = {"alarm_code": sample(25, "alarm_code", 56)}

    def detail(tag: str, value: float) -> str | None:
        return "Pouco material sobre a correia" if (tag, value) == ("alarm_code", 56.0) else None

    (plain,) = compute_what_changed(pre, now, ["alarm_code"])
    assert plain.text_pt == "passou de nenhum alarme para alarme 56"
    (rich,) = compute_what_changed(pre, now, ["alarm_code"], detail_for=detail)
    assert rich.text_pt == "passou de nenhum alarme para alarme 56 (Pouco material sobre a correia)"
    assert rich.ts_start_utc == at(20)


def test_discrete_value_pt_uses_simulator_encoding_and_falls_back_to_integer() -> None:
    assert discrete_value_pt("machine_state", 0) == "Parado"
    assert discrete_value_pt("machine_state", 1) == "Em operação"
    assert discrete_value_pt("machine_state", 2) == "Em alarme"
    assert discrete_value_pt("machine_state", 7) == "7"  # fora do mapa: inteiro, nunca inventado
    assert discrete_value_pt("alarm_active", 1) == "sim"
    assert discrete_value_pt("alarm_active", 0) == "não"
    assert discrete_value_pt("control_mode", 1) == "gravimétrico"
    assert discrete_value_pt("control_mode", 0) == "volumétrico"
    assert discrete_value_pt("alarm_code", 0) == "nenhum alarme"
    assert discrete_value_pt("alarm_code", 8) == "alarme 8"
    assert discrete_value_pt("stop_by", 0) == "nenhum"
    assert (
        discrete_value_pt("stop_by", 3, "Motivo desconhecido") == "código 3 (Motivo desconhecido)"
    )
    assert discrete_value_pt("sft_status", 385) == "385"
    assert discrete_value_pt("machine_state", None) == "sem leitura"


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
    assert "Agora: sem leitura" in item.text_pt
    assert "sem variação mensurável" in item.text_pt
    assert "—" not in item.text_pt


def test_continuous_without_any_usable_reading_is_excluded() -> None:
    pre = [sample(t, "mass_flow", None, Quality.COMM_ERROR) for t in range(10)]
    now = {"mass_flow": sample(10, "mass_flow", None, Quality.COMM_ERROR)}
    assert compute_what_changed(pre, now, ["mass_flow"]) == ()
    assert compute_what_changed([], {}, ["mass_flow"]) == ()


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
