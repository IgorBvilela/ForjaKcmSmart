"""Relatório por período de um equipamento: qualidade do dado no tempo, eventos e avisos da Forja,
alarmes que o KCM informou e um resumo em português. Só descreve o que foi gravado; nada é
interpolado e nada vira causa.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Any

from forja.domain import (
    EquipmentProfile,
    Event,
    Quality,
    Sample,
    Series,
    Severity,
    get_tag,
)
from forja.events.early_warning import build_grid
from forja.events.pre_event import pre_event_summary
from forja.events.recurrence import ORIGIN_PT
from forja.events.what_changed import fmt_number_pt, with_unit
from forja.events.window_analysis import fmt_duration_pt

USABLE: frozenset[Quality] = frozenset({Quality.GOOD, Quality.SIMULATED, Quality.UNCERTAIN})
MAX_EVENTS_LISTED = 100
SEVERITY_RANK = {Severity.INFO: 0, Severity.ATTENTION: 1, Severity.CRITICAL: 2}

AlarmTitle = Callable[[str], tuple[str, str]]
"""código -> (título em português, qualificador da evidência)."""


def tag_summary(series: Series, start: datetime, end: datetime) -> dict[str, Any]:
    """Cobertura no tempo, média ponderada e extremos das leituras utilizáveis de uma variável."""
    meta = get_tag(series.tag)
    grid = build_grid(series, start, end, USABLE)
    usable = [p for p in series.points if p.value is not None and p.quality in USABLE]
    lows = [p.min if p.min is not None else p.value for p in usable]
    highs = [p.max if p.max is not None else p.value for p in usable]
    comm = sum(1 for p in series.points if p.quality is Quality.COMM_ERROR)
    qualities = Counter(p.quality.value for p in series.points if p.value is not None)
    coverage = grid.coverage()
    return {
        "tag": series.tag,
        "label_pt": meta.label_pt,
        "unit": meta.unit,
        "decimals": meta.decimals,
        "coverage": coverage,
        "coverage_pt": f"{fmt_number_pt(coverage * 100, 1)}% do período com leitura",
        "average": grid.mean(0.0, grid.span_s),
        "min": min((v for v in lows if v is not None), default=None),
        "max": max((v for v in highs if v is not None), default=None),
        "comm_error_points": comm,
        "qualities": dict(qualities),
        "resolution": series.resolution,
    }


def _event_row(event: Event, start: datetime, end: datetime) -> dict[str, Any]:
    pre = pre_event_summary(event)
    stop = event.end_utc or end
    duration = max(0.0, (min(stop, end) - max(event.start_utc, start)).total_seconds())
    return {
        "id": event.id,
        "origin": event.origin,
        "origin_pt": ORIGIN_PT.get(event.origin, event.origin),
        "type": event.type,
        "title_pt": event.title_pt,
        "severity": event.severity.value,
        "severity_pt": event.severity.label_pt,
        "status": event.status.value,
        "start_utc": event.start_utc.isoformat(),
        "end_utc": event.end_utc.isoformat() if event.end_utc else None,
        "duration_in_period_s": duration,
        "quality": event.quality.value,
        "first_label_pt": pre["first_label_pt"],
        "lead_s": pre["lead_s"],
        "summary_pt": event.summary_pt,
        "acked_by": event.acked_by,
    }


def alarm_episodes(samples: Sequence[Sample], title: AlarmTitle) -> list[dict[str, Any]]:
    """Códigos de alarme diferentes de zero que o KCM informou, com primeira e última vez."""
    seen: dict[str, dict[str, Any]] = {}
    previous: float | None = None
    for s in sorted(samples, key=lambda x: x.ts_utc):
        if s.tag != "alarm_code" or s.value is None or s.quality not in USABLE:
            continue
        value = float(s.value)
        if value != 0 and value != previous:
            code = str(int(value)) if value.is_integer() else str(value)
            item = seen.get(code)
            if item is None:
                title_pt, qualifier = title(code)
                item = seen[code] = {
                    "code": code,
                    "title_pt": title_pt,
                    "qualifier_pt": qualifier,
                    "times": 0,
                    "first_utc": s.ts_utc.isoformat(),
                }
            item["times"] += 1
            item["last_utc"] = s.ts_utc.isoformat()
        previous = value
    return sorted(seen.values(), key=lambda a: a["first_utc"])


def build_period_report(
    profile: EquipmentProfile,
    start: datetime,
    end: datetime,
    series: Mapping[str, Series],
    events: Sequence[Event],
    alarm_samples: Sequence[Sample],
    alarm_title: AlarmTitle,
    *,
    generated_at: datetime,
) -> dict[str, Any]:
    tags = [tag_summary(s, start, end) for s in series.values()]
    in_period = sorted(
        (e for e in events if e.start_utc <= end and (e.end_utc is None or e.end_utc >= start)),
        key=lambda e: e.start_utc,
    )
    rows = [_event_row(e, start, end) for e in in_period]
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for e, row in zip(in_period, rows, strict=True):
        g = groups.setdefault(
            (e.origin, e.type),
            {
                "origin": e.origin,
                "origin_pt": row["origin_pt"],
                "type": e.type,
                "title_pt": e.title_pt,
                "count": 0,
                "duration_in_period_s": 0.0,
                "worst_severity": e.severity.value,
            },
        )
        g["count"] += 1
        g["duration_in_period_s"] += row["duration_in_period_s"]
        if SEVERITY_RANK[e.severity] > SEVERITY_RANK[Severity(g["worst_severity"])]:
            g["worst_severity"] = e.severity.value
    alarms = alarm_episodes(alarm_samples, alarm_title)
    narrative = _narrative(tags, list(groups.values()), alarms, profile)
    return {
        "equipment_id": profile.id,
        "name": profile.name,
        "display_path": profile.display_path,
        "application": profile.application,
        "data_source": "SIMULATED" if profile.is_simulated else "EQUIPMENT",
        "from_utc": start.isoformat(),
        "to_utc": end.isoformat(),
        "period_pt": fmt_duration_pt((end - start).total_seconds()),
        "generated_at_utc": generated_at.isoformat(),
        "narrative_pt": narrative,
        "tags": tags,
        "event_groups": sorted(groups.values(), key=lambda g: -int(g["count"])),
        "events": rows[-MAX_EVENTS_LISTED:],
        "events_total": len(rows),
        "kcm_alarms": alarms,
        "caveats_pt": [
            "Relatório do que a Forja gravou: trecho sem leitura aparece como sem leitura, nunca "
            "preenchido.",
            "Eventos e avisos descrevem ordem e duração; não afirmam causa.",
            "Alarmes listados são os que o KCM informou; o significado vem do catálogo da chave "
            "deste equipamento.",
        ],
    }


def _narrative(
    tags: Sequence[Mapping[str, Any]],
    groups: Sequence[Mapping[str, Any]],
    alarms: Sequence[Mapping[str, Any]],
    profile: EquipmentProfile,
) -> list[str]:
    lines: list[str] = []
    if profile.is_simulated:
        lines.append("Dados simulados: nenhum valor deste relatório representa um KCM real.")
    flow = next((t for t in tags if t["tag"] == "mass_flow"), None) or (tags[0] if tags else None)
    if flow is not None:
        avg = flow["average"]
        avg_pt = (
            f", média de {with_unit(fmt_number_pt(avg, int(flow['decimals'])), str(flow['unit']))}"
            if avg is not None
            else ""
        )
        lines.append(f"{flow['label_pt']}: {flow['coverage_pt']}{avg_pt}.")
    low = [t for t in tags if t["coverage"] < 0.95]
    if low:
        names = ", ".join(str(t["label_pt"]) for t in low[:4])
        lines.append(f"Com leitura em menos de 95% do período: {names}.")
    forja = [g for g in groups if g["origin"] == "RULE"]
    warnings = [g for g in groups if g["origin"] == "EARLY_WARNING"]
    if forja:
        total = sum(int(g["count"]) for g in forja)
        top = ", ".join(f"{g['count']}× {g['title_pt']}" for g in forja[:3])
        lines.append(f"{total} evento(s) detectado(s) pela Forja: {top}.")
    else:
        lines.append("Nenhum evento detectado pela Forja no período.")
    if warnings:
        total = sum(int(g["count"]) for g in warnings)
        lines.append(f"{total} aviso(s) antecipado(s) da Forja no período.")
    if alarms:
        top = ", ".join(f"{a['code']} ({a['title_pt']}) {a['times']}×" for a in alarms[:3])
        lines.append(f"O KCM informou alarme: {top}.")
    else:
        lines.append("O KCM não informou alarme no período (ou o mapping não traz o alarme).")
    return lines


__all__ = ["alarm_episodes", "build_period_report", "tag_summary"]
