"""Ocorrências anteriores: "isso já aconteceu antes neste equipamento?".

Agrupa os eventos guardados por origem e tipo e conta quantas vezes, quando foi a primeira e a
última, quanto duraram e qual variável costuma sair do padrão primeiro. Descreve frequência e
ordem; nunca afirma causa.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from statistics import median
from typing import Any

from forja.domain import Event, EventStatus
from forja.events.window_analysis import fmt_duration_pt

ORIGIN_PT: dict[str, str] = {
    "RULE": "Evento detectado pela Forja",
    "EARLY_WARNING": "Aviso antecipado da Forja",
}


def _first_changed(event: Event) -> tuple[str, str] | None:
    for item in event.context.what_changed:
        if item.changed_first:
            return item.tag, item.label_pt
    return None


def recurrence(events: Sequence[Event]) -> list[dict[str, Any]]:
    """Um grupo por (origem, tipo), do mais recente para o mais antigo."""
    groups: dict[tuple[str, str], list[Event]] = {}
    for event in events:
        groups.setdefault((event.origin, event.type), []).append(event)
    out: list[dict[str, Any]] = []
    for (origin, _type), items in groups.items():
        items.sort(key=lambda e: e.start_utc)
        last = items[-1]
        durations = [e.duration_s for e in items if e.duration_s is not None]
        firsts = Counter(f for f in (_first_changed(e) for e in items) if f is not None)
        top = firsts.most_common(1)[0] if firsts else None
        resolutions = Counter(
            e.resolution.resolution_class
            for e in items
            if e.resolution is not None and e.resolution.resolution_class != "UNKNOWN"
        )
        typical = median(durations) if durations else None
        lines = [
            f"{len(items)} ocorrência(s) registrada(s) neste equipamento."
            if len(items) > 1
            else "Uma ocorrência registrada neste equipamento."
        ]
        if top is not None:
            (_, label), count = top
            lines.append(
                f"{label} saiu do padrão primeiro em {count} de {len(items)} ocorrência(s)."
            )
        if typical is not None:
            lines.append(f"Duração típica: {fmt_duration_pt(typical)}.")
        out.append(
            {
                "origin": origin,
                "origin_pt": ORIGIN_PT.get(origin, origin),
                "type": last.type,
                "title_pt": last.title_pt,
                "rule_id": last.rule_id,
                "severity": last.severity.value,
                "count": len(items),
                "open_count": sum(1 for e in items if e.is_open),
                "acknowledged_count": sum(
                    1 for e in items if e.status is EventStatus.ACKNOWLEDGED or e.acked_by
                ),
                "first_start_utc": items[0].start_utc.isoformat(),
                "last_start_utc": last.start_utc.isoformat(),
                "last_event_id": last.id,
                "typical_duration_s": typical,
                "first_changed": (
                    {"tag": top[0][0], "label_pt": top[0][1], "count": top[1]} if top else None
                ),
                "resolutions": dict(resolutions),
                "narrative_pt": lines,
                "recent_event_ids": [e.id for e in reversed(items[-5:])],
            }
        )
    out.sort(key=lambda g: str(g["last_start_utc"]), reverse=True)
    return out


__all__ = ["ORIGIN_PT", "recurrence"]
