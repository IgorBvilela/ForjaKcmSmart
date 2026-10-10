"""Antes do evento: quem saiu do padrão primeiro, quanto tempo antes e quem mudou junto.

Lê o "O que mudou" já guardado no evento (instante em que cada variável saiu do padrão na
janela anterior). Descreve ordem e simultaneidade; nunca afirma causa.
"""

from __future__ import annotations

from typing import Any

from forja.domain import Event
from forja.events.window_analysis import DEFAULT_TOGETHER_S, fmt_duration_pt

TIE_S = 1.0
"""Saídas do padrão com menos que isto de diferença contam como o mesmo instante."""
NO_DEPARTURE_PT = (
    "Na janela anterior guardada, nenhuma variável observada saiu do padrão antes da abertura."
)
EARLY_WARNING_PT = (
    "Aviso antecipado: a Forja olhou a tendência da janela inteira; não há um instante único de "
    "saída do padrão. Veja os sinais medidos no resumo."
)


def pre_event_summary(event: Event, together_s: float = DEFAULT_TOGETHER_S) -> dict[str, Any]:
    """Resumo serializável da janela anterior ao evento."""
    timed = sorted(
        (i for i in event.context.what_changed if i.ts_start_utc is not None),
        key=lambda i: i.ts_start_utc or event.start_utc,
    )
    base: dict[str, Any] = {
        "pre_window_s": event.context.pre_window_s,
        "together_s": together_s,
        "first_tag": None,
        "first_label_pt": None,
        "lead_s": None,
        "changes": [],
        "together": [],
    }
    if not timed:
        text = EARLY_WARNING_PT if event.origin == "EARLY_WARNING" else NO_DEPARTURE_PT
        return {**base, "narrative_pt": [text]}

    changes: list[dict[str, Any]] = []
    for item in timed:
        started = item.ts_start_utc or event.start_utc
        changes.append(
            {
                "tag": item.tag,
                "label_pt": item.label_pt,
                "started_utc": started.isoformat(),
                "before_event_s": max(0.0, (event.start_utc - started).total_seconds()),
                "text_pt": item.text_pt,
            }
        )

    groups: list[list[str]] = []
    current: list[dict[str, Any]] = []
    for change, item in zip(changes, timed, strict=True):
        anchor = current[0]["_ts"] if current else None
        ts = item.ts_start_utc or event.start_utc
        if anchor is not None and (ts - anchor).total_seconds() <= together_s:
            current.append({**change, "_ts": ts})
            continue
        if len(current) > 1:
            groups.append([c["label_pt"] for c in current])
        current = [{**change, "_ts": ts}]
    if len(current) > 1:
        groups.append([c["label_pt"] for c in current])

    first = changes[0]
    tied = [c for c in changes if abs(c["before_event_s"] - first["before_event_s"]) < TIE_S]
    for change in changes:
        change["first"] = change in tied
    when = (
        f"{fmt_duration_pt(first['before_event_s'])} antes da abertura do evento"
        if first["before_event_s"] >= 1
        else "no instante da abertura do evento"
    )
    if len(tied) > 1:
        names = ", ".join(c["label_pt"] for c in tied[:-1]) + f" e {tied[-1]['label_pt']}"
        lines = [f"{names} saíram do padrão primeiro, juntas, {when}."]
    else:
        lines = [f"{first['label_pt']} saiu do padrão primeiro, {when}."]
    for change in changes[len(tied) :]:
        lines.append(
            f"{change['label_pt']}: {fmt_duration_pt(change['before_event_s'])} antes da abertura."
            if change["before_event_s"] >= 1
            else f"{change['label_pt']}: no instante da abertura."
        )
    for group in groups:
        lines.append(
            f"Mudaram juntas (diferença de até {fmt_duration_pt(together_s)}): {', '.join(group)}."
        )
    lines.append("Ordem dos acontecimentos, não causa.")
    return {
        **base,
        "first_tag": first["tag"],
        "first_label_pt": first["label_pt"],
        "lead_s": first["before_event_s"],
        "changes": changes,
        "together": groups,
        "narrative_pt": lines,
    }


__all__ = ["EARLY_WARNING_PT", "NO_DEPARTURE_PT", "pre_event_summary"]
