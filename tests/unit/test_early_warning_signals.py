"""Aviso antecipado: grade sem interpolação, tendência, desvio, proximidade, estado e combinação."""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from forja.domain import ConfigError, Quality, Series, SeriesPoint, SourceRef
from forja.domain.evidence import EvidenceLevel
from forja.events.early_warning import (
    build_grid,
    combine,
    evaluate_rule,
    fit_line,
)
from forja.events.ew_rules import EarlyWarningRule, load_ew_rules

pytestmark = pytest.mark.unit

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
ALLOWED = frozenset({Quality.GOOD, Quality.SIMULATED, Quality.UNCERTAIN})
REPO = Path(__file__).resolve().parents[2]

SOURCE = SourceRef(
    id="SRC-TEST",
    kind="rule",
    title="Regra de teste",
    reference="teste",
    evidence_level=EvidenceLevel.FORJA_RULE,
)


def raw_series(
    tag: str,
    fn: Callable[[float], float | None],
    *,
    seconds: int,
    step_s: int = 5,
    quality: Quality = Quality.SIMULATED,
    end: datetime = T0,
) -> Series:
    """Série bruta de `seconds` até `end`, uma linha a cada `step_s`. fn(t) None = sem valor."""
    start = end - timedelta(seconds=seconds)
    points = []
    for k in range(0, seconds + 1, step_s):
        value = fn(float(k))
        points.append(
            SeriesPoint(
                ts_utc=start + timedelta(seconds=k),
                value=value,
                quality=quality if value is not None else Quality.COMM_ERROR,
            )
        )
    return Series(equipment_id="EQ", tag=tag, resolution="raw", bucket_s=0, points=tuple(points))


def wiggle(t: float, amp: float) -> float:
    """Ruído determinístico pequeno."""
    return amp * math.sin(t / 7.0) * math.cos(t / 13.0)


def rule(signals: list[dict[str, Any]], **over: Any) -> EarlyWarningRule:
    data: dict[str, Any] = {
        "id": "EW-TEST-001",
        "internal_code": "EW_TEST",
        "title_pt": "Aviso de teste",
        "window_s": 900,
        "recent_s": 120,
        "signals": signals,
        "sources": [SOURCE.model_dump()],
    }
    data.update(over)
    return EarlyWarningRule.model_validate(data)


# --- grade ------------------------------------------------------------------------------------


def test_grade_nao_interpola_buraco() -> None:
    def fn(t: float) -> float | None:
        return None if 300 <= t < 600 else 50.0

    series = raw_series("drive_command", fn, seconds=900)
    grid = build_grid(series, T0 - timedelta(seconds=900), T0, ALLOWED, cells=90)
    empty = [i for i, v in enumerate(grid.cells) if v is None]
    assert empty, "trecho sem valor tem de virar célula vazia"
    assert all(29 <= i <= 60 for i in empty)
    assert grid.coverage() == pytest.approx(600 / 900, abs=0.02)


def test_grade_ignora_qualidade_nao_permitida() -> None:
    series = raw_series("drive_command", lambda t: 50.0, seconds=600, quality=Quality.BAD)
    grid = build_grid(series, T0 - timedelta(seconds=600), T0, ALLOWED)
    assert grid.coverage() == 0.0
    assert all(v is None for v in grid.cells)


def test_grade_nao_segura_valor_alem_do_limite() -> None:
    # uma leitura só, há 10 min: vale por no máximo 120 s (degrau), não até agora
    start = T0 - timedelta(seconds=600)
    series = Series(
        equipment_id="EQ",
        tag="drive_command",
        resolution="raw",
        bucket_s=0,
        points=(SeriesPoint(ts_utc=start, value=40.0, quality=Quality.GOOD),),
    )
    grid = build_grid(series, start, T0, ALLOWED, max_hold_s=120)
    assert grid.coverage() == pytest.approx(120 / 600)


def test_reta_plana_tem_ajuste_zero() -> None:
    line = fit_line([0, 1, 2, 3, 4, 5], [7.0] * 6)
    assert line is not None
    assert line.slope == 0
    assert line.r2 == 0


# --- tendência --------------------------------------------------------------------------------


def trend_rule(**signal: Any) -> EarlyWarningRule:
    base = {"tag": "drive_command", "kind": "trend", "direction": "up", "min_change": 8}
    base.update(signal)
    return rule([base])


def test_subida_gradual_atende_tendencia() -> None:
    r = trend_rule(min_fit=0.6)
    series = raw_series("drive_command", lambda t: 40 + 10 * t / 900 + wiggle(t, 0.4), seconds=900)
    ev = evaluate_rule(r, "EQ", {"drive_command": series}, T0)
    out = ev.signals[0]
    assert out.verdict == "MET"
    assert out.measured == pytest.approx(10, abs=0.8)
    assert out.fit is not None
    assert out.fit > 0.9
    assert "subiu" in out.text_pt
    assert "pontos" in out.text_pt
    assert ev.state == "MET"


def test_oscilacao_sem_tendencia_nao_atende() -> None:
    r = trend_rule(min_fit=0.6)
    series = raw_series(
        "drive_command", lambda t: 40 + 4 * math.sin(2 * math.pi * t / 120), seconds=900
    )
    out = evaluate_rule(r, "EQ", {"drive_command": series}, T0).signals[0]
    assert out.verdict == "NOT_MET"


def test_sentido_errado_nao_atende() -> None:
    r = trend_rule(direction="down")
    series = raw_series("drive_command", lambda t: 40 + 10 * t / 900, seconds=900)
    assert evaluate_rule(r, "EQ", {"drive_command": series}, T0).signals[0].verdict == "NOT_MET"


def test_tendencia_em_percentual_para_kg_por_metro() -> None:
    r = rule([{"tag": "belt_load", "kind": "trend", "direction": "down", "min_change": 10}])
    series = raw_series("belt_load", lambda t: 1.0 - 0.2 * t / 900, seconds=900)
    out = evaluate_rule(r, "EQ", {"belt_load": series}, T0).signals[0]
    assert out.verdict == "MET"
    assert out.measured == pytest.approx(-20, abs=1)
    assert "%" in out.text_pt


def test_pouca_leitura_e_dado_insuficiente() -> None:
    r = rule(
        [{"tag": "drive_command", "kind": "trend", "direction": "up", "min_change": 8}],
        min_coverage=0.8,
    )
    series = raw_series(
        "drive_command", lambda t: None if t < 400 else 40 + 10 * t / 900, seconds=900
    )
    ev = evaluate_rule(r, "EQ", {"drive_command": series}, T0)
    assert ev.signals[0].verdict == "INSUFFICIENT"
    assert "dados insuficientes" in ev.signals[0].text_pt
    assert ev.state == "INSUFFICIENT"


# --- desvio, proximidade e estado -------------------------------------------------------------


def test_desvio_do_inicio_da_janela() -> None:
    r = rule([{"tag": "belt_load", "kind": "deviation", "direction": "down", "min_change": 10}])
    series = raw_series("belt_load", lambda t: 1.0 if t < 450 else 0.85, seconds=900)
    out = evaluate_rule(r, "EQ", {"belt_load": series}, T0).signals[0]
    assert out.verdict == "MET"
    assert out.measured == pytest.approx(-15, abs=0.5)
    assert "abaixo do padrão do início da janela" in out.text_pt


def test_desvio_com_padrao_antes_da_janela() -> None:
    r = rule(
        [{"tag": "rpm", "kind": "deviation", "direction": "down", "min_change": 3}],
        baseline="before_window",
        baseline_s=1800,
    )
    # 30 min de padrão em 50 rpm, depois 15 min em 46 rpm
    series = raw_series("rpm", lambda t: 50.0 if t < 1800 else 46.0, seconds=2700)
    out = evaluate_rule(r, "EQ", {"rpm": series}, T0).signals[0]
    assert out.verdict == "MET"
    assert out.before == pytest.approx(50)
    assert out.now == pytest.approx(46)
    assert "antes da janela" in out.text_pt


def test_proximidade_da_referencia() -> None:
    sig = {
        "tag": "mass_flow",
        "kind": "near_reference",
        "ref_tag": "setpoint",
        "max_deviation_pct": 5,
    }
    r = rule([sig])
    sp = raw_series("setpoint", lambda t: 1000.0, seconds=900)
    near = raw_series("mass_flow", lambda t: 990.0, seconds=900)
    far = raw_series("mass_flow", lambda t: 900.0, seconds=900)
    ok = evaluate_rule(r, "EQ", {"mass_flow": near, "setpoint": sp}, T0).signals[0]
    bad = evaluate_rule(r, "EQ", {"mass_flow": far, "setpoint": sp}, T0).signals[0]
    assert ok.verdict == "MET"
    assert ok.measured == pytest.approx(1.0)
    assert bad.verdict == "NOT_MET"
    assert bad.measured == pytest.approx(10.0)


def test_estado_em_operacao_na_janela() -> None:
    r = rule([{"tag": "machine_state", "kind": "state", "value": 1, "min_fraction": 0.95}])
    running = raw_series("machine_state", lambda t: 1.0, seconds=900)
    stopped_part = raw_series("machine_state", lambda t: 1.0 if t < 700 else 0.0, seconds=900)
    assert evaluate_rule(r, "EQ", {"machine_state": running}, T0).signals[0].verdict == "MET"
    out = evaluate_rule(r, "EQ", {"machine_state": stopped_part}, T0).signals[0]
    assert out.verdict == "NOT_MET"
    assert "Em operação" in out.text_pt


def test_combinacao_e_and_com_insuficiente() -> None:
    class Outcome:
        def __init__(self, verdict: str) -> None:
            self.verdict = verdict

    assert combine([Outcome("MET"), Outcome("MET")]) == "MET"  # type: ignore[list-item]
    assert combine([Outcome("MET"), Outcome("INSUFFICIENT")]) == "INSUFFICIENT"  # type: ignore[list-item]
    assert combine([Outcome("INSUFFICIENT"), Outcome("NOT_MET")]) == "NOT_MET"  # type: ignore[list-item]


def test_exemplo_do_esforco_subindo_com_vazao_mantida() -> None:
    # Drive Command subindo aos poucos + vazão perto do setpoint + menos material na correia
    r = rule(
        [
            {
                "tag": "drive_command",
                "kind": "trend",
                "direction": "up",
                "min_change": 8,
                "min_fit": 0.6,
            },
            {
                "tag": "mass_flow",
                "kind": "near_reference",
                "ref_tag": "setpoint",
                "max_deviation_pct": 3,
            },
            {
                "tag": "belt_load",
                "kind": "trend",
                "direction": "down",
                "min_change": 10,
                "min_fit": 0.5,
            },
            {"tag": "machine_state", "kind": "state", "value": 1},
        ]
    )
    series = {
        "drive_command": raw_series("drive_command", lambda t: 40 + 12 * t / 900, seconds=900),
        "mass_flow": raw_series("mass_flow", lambda t: 1000 + wiggle(t, 5), seconds=900),
        "setpoint": raw_series("setpoint", lambda t: 1000.0, seconds=900),
        "belt_load": raw_series("belt_load", lambda t: 1.0 - 0.25 * t / 900, seconds=900),
        "machine_state": raw_series("machine_state", lambda t: 1.0, seconds=900),
    }
    ev = evaluate_rule(r, "EQ", series, T0)
    assert ev.state == "MET"
    assert ev.met_count == 4
    assert ev.quality is Quality.SIMULATED


# --- configuração -----------------------------------------------------------------------------


def test_regras_do_repositorio_carregam() -> None:
    rules = load_ew_rules(REPO / "config" / "early_warning")
    assert rules, "o produto traz regras de aviso antecipado configuradas"
    for r in rules:
        assert r.threshold_basis == "FORJA_RULE"
        assert "não são limites do kcm" in r.threshold_note_pt.lower()
        assert r.severity.value in ("INFO", "ATTENTION")


@pytest.mark.parametrize(
    ("signals", "over", "match"),
    [
        ([{"tag": "drive_command", "kind": "trend"}], {}, "min_change"),
        ([{"tag": "nao_existe", "kind": "trend", "min_change": 1}], {}, "desconhecida"),
        ([{"tag": "mass_flow", "kind": "near_reference", "max_deviation_pct": 3}], {}, "ref_tag"),
        ([{"tag": "machine_state", "kind": "trend", "min_change": 1}], {}, "contínua"),
        ([{"tag": "machine_state", "kind": "state"}], {}, "value"),
        (
            [{"tag": "rpm", "kind": "deviation", "min_change": 1}],
            {"severity": "CRITICAL"},
            "INFO ou ATTENTION",
        ),
        ([{"tag": "rpm", "kind": "deviation", "min_change": 1}], {"recent_s": 600}, "recent_s"),
        (
            [{"tag": "rpm", "kind": "deviation", "min_change": 1}],
            {"baseline": "before_window"},
            "baseline_s",
        ),
        (
            [{"tag": "rpm", "kind": "deviation", "min_change": 1}],
            {"allowed_qualities": ["BAD"]},
            "BAD",
        ),
        (
            [{"tag": "rpm", "kind": "deviation", "min_change": 1}],
            {"title_pt": "EW_TEST"},
            "código interno",
        ),
    ],
)
def test_configuracao_invalida_e_recusada(
    signals: list[dict[str, Any]], over: dict[str, Any], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        rule(signals, **over)


def test_pasta_com_id_duplicado_e_recusada(tmp_path: Path) -> None:
    text = (REPO / "config" / "early_warning").glob("*.yaml")
    first = next(iter(sorted(text)))
    (tmp_path / "a.yaml").write_text(first.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "b.yaml").write_text(first.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(ConfigError, match="duplicado"):
        load_ew_rules(tmp_path)
