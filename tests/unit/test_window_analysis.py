"""Análise de janela para Tendências: o que mudou, quando começou, quem mudou primeiro."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from forja.domain import Quality, Sample
from forja.events.window_analysis import analyze_window

pytestmark = pytest.mark.unit

T0 = datetime(2026, 10, 1, 17, 0, 0, tzinfo=UTC)
EQ = "EQ_TESTE"


def _s(tag: str, second: int, value: float | None, quality: Quality = Quality.GOOD) -> Sample:
    return Sample(
        ts_utc=T0 + timedelta(seconds=second),
        equipment_id=EQ,
        tag=tag,
        value=value,
        quality=quality,
        source="teste",
    )


def _series(tag: str, values: list[float | None]) -> list[Sample]:
    return [_s(tag, i * 10, v) for i, v in enumerate(values)]


def _ramp(base: float, end: float, start_idx: int, n: int) -> list[float | None]:
    out: list[float | None] = []
    for i in range(n):
        if i < start_idx:
            out.append(base)
        else:
            out.append(base + (end - base) * (i - start_idx + 1) / (n - start_idx))
    return out


def test_ordena_por_quem_mudou_primeiro_e_calcula_antecedencia() -> None:
    drive = _series("drive_command", _ramp(60.0, 90.0, 20, 60))
    flow = _series("mass_flow", _ramp(1300.0, 1000.0, 30, 60))
    belt = _series("belt_load", [2.0] * 60)
    result = analyze_window(
        {"drive_command": drive, "mass_flow": flow, "belt_load": belt},
        ["mass_flow", "drive_command", "belt_load"],
        timezone="America/Sao_Paulo",
        resolution_s=10,
    )
    tags = [c.item.tag for c in result.changes]
    assert tags[:2] == ["drive_command", "mass_flow"]
    first = result.changes[0]
    assert first.item.changed_first is True
    assert first.offset_s == 0
    second = result.changes[1]
    assert second.offset_s is not None
    assert second.offset_s > 0
    assert result.first_changed_tag == "drive_command"
    assert any("Esforço do acionamento" in line for line in result.narrative_pt)
    assert any("depois" in line for line in result.narrative_pt)
    assert "belt_load" in result.unchanged_tags


def test_variaveis_que_mudaram_juntas_sao_agrupadas() -> None:
    drive = _series("drive_command", _ramp(60.0, 90.0, 20, 60))
    belt = _series("belt_load", _ramp(2.0, 1.0, 20, 60))
    result = analyze_window(
        {"drive_command": drive, "belt_load": belt},
        ["drive_command", "belt_load"],
        timezone="America/Sao_Paulo",
        resolution_s=10,
        together_s=30,
    )
    assert result.together == [["drive_command", "belt_load"]] or result.together == [
        ["belt_load", "drive_command"]
    ]
    assert any("juntas" in line for line in result.narrative_pt)


def test_janela_sem_mudanca_diz_isso_com_honestidade() -> None:
    flow = _series("mass_flow", [1300.0] * 30)
    result = analyze_window(
        {"mass_flow": flow}, ["mass_flow"], timezone="America/Sao_Paulo", resolution_s=10
    )
    assert result.changes == []
    assert result.first_changed_tag is None
    assert any("Nenhuma variável saiu do padrão" in line for line in result.narrative_pt)


def test_falha_de_comunicacao_nunca_e_interpolada_e_vira_ressalva() -> None:
    values: list[float | None] = [1300.0] * 10 + [None] * 5 + [1300.0] * 10
    samples = [
        _s("mass_flow", i * 10, v, Quality.GOOD if v is not None else Quality.COMM_ERROR)
        for i, v in enumerate(values)
    ]
    result = analyze_window(
        {"mass_flow": samples}, ["mass_flow"], timezone="America/Sao_Paulo", resolution_s=10
    )
    stats = result.stats["mass_flow"]
    assert stats.comm_error_points == 5
    assert stats.min == 1300.0
    assert stats.max == 1300.0
    assert any("sem comunicação" in c for c in result.caveats_pt)
    assert any("interpolad" in c for c in result.caveats_pt)


def test_estatisticas_por_tag_e_qualidades_contadas() -> None:
    samples = [
        _s("mass_flow", 0, 1000.0, Quality.SIMULATED),
        _s("mass_flow", 10, 1200.0, Quality.SIMULATED),
        _s("mass_flow", 20, 1100.0, Quality.UNCERTAIN),
        _s("mass_flow", 30, None, Quality.BAD),
    ]
    result = analyze_window(
        {"mass_flow": samples}, ["mass_flow"], timezone="America/Sao_Paulo", resolution_s=10
    )
    stats = result.stats["mass_flow"]
    assert (stats.min, stats.max) == (1000.0, 1200.0)
    assert stats.first == 1000.0
    assert stats.last == 1100.0
    assert stats.qualities == {"SIMULATED": 2, "UNCERTAIN": 1, "BAD": 1}
    assert any("simulados" in c.lower() for c in result.caveats_pt)


def test_nunca_fala_em_causa() -> None:
    drive = _series("drive_command", _ramp(60.0, 90.0, 20, 60))
    result = analyze_window(
        {"drive_command": drive}, ["drive_command"], timezone="America/Sao_Paulo", resolution_s=10
    )
    text = " ".join(result.narrative_pt + result.caveats_pt).lower()
    assert "causa" not in text or "não é causa" in text


def test_antes_e_o_padrao_do_inicio_mesmo_com_dois_ciclos_na_janela() -> None:
    # ciclo 1: sobe de 40 para 87; volta a 40; ciclo 2: sobe de novo e fica em 87
    values: list[float | None] = [40.0] * 10 + [87.0] * 20 + [40.0] * 5 + [87.0] * 15
    result = analyze_window(
        {"drive_command": _series("drive_command", values)},
        ["drive_command"],
        timezone="America/Sao_Paulo",
        resolution_s=10,
    )
    change = result.changes[0]
    assert change.item.before == pytest.approx(40.0)
    assert change.item.now == pytest.approx(87.0)
    assert change.item.delta == pytest.approx(47.0)
    # a condição atual começou no segundo ciclo (índice 35 → 350 s)
    assert change.item.ts_start_utc == T0 + timedelta(seconds=350)
