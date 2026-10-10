"""Antes do evento (ordem e antecedência) e ocorrências anteriores (recorrência)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from forja.domain import (
    Event,
    EventContext,
    EventStatus,
    Quality,
    Resolution,
    Severity,
    WhatChangedItem,
)
from forja.events.pre_event import EARLY_WARNING_PT, NO_DEPARTURE_PT, pre_event_summary
from forja.events.recurrence import recurrence

pytestmark = pytest.mark.unit

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def item(
    tag: str, label: str, started_s_before: float | None, first: bool = False
) -> WhatChangedItem:
    return WhatChangedItem(
        tag=tag,
        label_pt=label,
        unit="",
        before=1.0,
        now=2.0,
        delta=1.0,
        delta_kind="abs",
        changed_first=first,
        ts_start_utc=None if started_s_before is None else T0 - timedelta(seconds=started_s_before),
        text_pt="mudou",
    )


def event(
    items: tuple[WhatChangedItem, ...],
    *,
    start: datetime = T0,
    origin: str = "RULE",
    type_: str = "BELT_LOAD_LOW",
    duration_s: float | None = None,
    resolution_class: str = "UNKNOWN",
) -> Event:
    extra: dict[str, object] = {}
    if duration_s is not None:
        extra = {
            "end_utc": start + timedelta(seconds=duration_s),
            "status": EventStatus.RESOLVED,
            "resolution": Resolution(
                resolved_at_utc=start + timedelta(seconds=duration_s),
                resolved_by="forja",
                resolution_class=resolution_class,  # type: ignore[arg-type]
            ),
        }
    return Event(
        equipment_id="EQ",
        type=type_,
        title_pt="Pouco material sobre a correia",
        start_utc=start,
        severity=Severity.ATTENTION,
        summary_pt="resumo",
        rule_id="R-TESTE-001",
        context=EventContext(pre_window_s=60, post_window_s=30, what_changed=items),
        quality=Quality.SIMULATED,
        dedupe_key="EQ:R-TESTE-001",
        origin=origin,  # type: ignore[arg-type]
        **extra,  # type: ignore[arg-type]
    )


def test_quem_saiu_primeiro_quanto_antes_e_quem_mudou_junto() -> None:
    ev = event(
        (
            item("belt_load", "Material na correia", 42, first=True),
            item("drive_command", "Esforço do acionamento", 30),
            item("mass_flow", "Vazão", 2),
        )
    )
    summary = pre_event_summary(ev)
    assert summary["first_tag"] == "belt_load"
    assert summary["lead_s"] == pytest.approx(42)
    assert summary["together"] == [["Material na correia", "Esforço do acionamento"]]
    text = " ".join(summary["narrative_pt"])
    assert "Material na correia saiu do padrão primeiro, 42 s antes da abertura" in text
    assert "Vazão: 2 s antes da abertura" in text
    assert "não causa" in text


def test_empate_no_primeiro_instante_vira_saida_conjunta() -> None:
    ev = event(
        (
            item("drive_command", "Esforço do acionamento", 47, first=True),
            item("belt_load", "Material na correia", 47),
            item("mass_flow", "Vazão", 10),
        )
    )
    summary = pre_event_summary(ev)
    assert [c["first"] for c in summary["changes"]] == [True, True, False]
    assert summary["narrative_pt"][0] == (
        "Esforço do acionamento e Material na correia saíram do padrão primeiro, juntas, "
        "47 s antes da abertura do evento."
    )
    assert summary["narrative_pt"][1] == "Vazão: 10 s antes da abertura."


def test_sem_saida_do_padrao_diz_isso() -> None:
    assert pre_event_summary(event((item("rpm", "Velocidade", None),)))["narrative_pt"] == [
        NO_DEPARTURE_PT
    ]
    ew = event((), origin="EARLY_WARNING")
    assert pre_event_summary(ew)["narrative_pt"] == [EARLY_WARNING_PT]


def test_recorrencia_conta_ordem_e_duracao() -> None:
    first = item("belt_load", "Material na correia", 40, first=True)
    other = item("drive_command", "Esforço do acionamento", 40, first=True)
    events = [
        event((first,), start=T0 - timedelta(days=3), duration_s=300),
        event((first,), start=T0 - timedelta(days=2), duration_s=600, resolution_class="FAULT"),
        event((other,), start=T0 - timedelta(days=1), duration_s=900),
        event((), start=T0, type_="SPEED_FEEDBACK_ZERO"),
    ]
    groups = recurrence(events)
    assert [g["type"] for g in groups] == ["SPEED_FEEDBACK_ZERO", "BELT_LOAD_LOW"]
    belt = groups[1]
    assert belt["count"] == 3
    assert belt["first_changed"] == {
        "tag": "belt_load",
        "label_pt": "Material na correia",
        "count": 2,
    }
    assert belt["typical_duration_s"] == pytest.approx(600)
    assert belt["resolutions"] == {"FAULT": 1}
    assert belt["origin_pt"] == "Evento detectado pela Forja"
    assert "Material na correia saiu do padrão primeiro em 2 de 3" in " ".join(belt["narrative_pt"])
    assert groups[0]["open_count"] == 1


def test_aviso_antecipado_e_evento_ficam_em_grupos_separados() -> None:
    groups = recurrence(
        [event((), type_="X_CODE"), event((), type_="X_CODE", origin="EARLY_WARNING")]
    )
    assert {g["origin"] for g in groups} == {"RULE", "EARLY_WARNING"}
