"""Medida de tempo por dosador e período: dentro do normal, fora do normal e sem dados.

Classificação: FORJA_RULE (especificação da fase Q, §16; contrato em `CONTRATOS_Q.md`).

- Sem dados: trecho sem leitura válida da variável de referência (buraco, falha de comunicação,
  coleta pausada ou não iniciada). Nunca conta como normal nem como fora do normal.
- Fora do normal: trecho com dado e com evento da Forja aberto (regra, gravidade de atenção para
  cima) ou com o alarme do KCM ativo.
- Dentro do normal: o resto do tempo com dado.

O aviso antecipado não conta como fora do normal: é sinal fraco e aparece à parte. As três partes
somam o período inteiro. Os trechos são segundos desde o início do período.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from forja.domain import Sample, Severity
from forja.events.kcm_alarm import ACTIVE, alarm_state

Interval = tuple[float, float]

COUNTED_ORIGIN = "RULE"
"""Só evento de regra da Forja conta como fora do normal; aviso antecipado fica à parte."""
COUNTED_SEVERITIES = frozenset({Severity.ATTENTION, Severity.CRITICAL})

DEFINITION_PT = (
    "Sem dados: sem leitura válida. Fora do normal: com dado e com evento da Forja aberto "
    "(atenção para cima) ou alarme do KCM ativo. Dentro do normal: o resto do tempo com dado. "
    "O aviso antecipado não conta."
)


class EventLike(Protocol):
    @property
    def start_utc(self) -> datetime: ...
    @property
    def end_utc(self) -> datetime | None: ...
    @property
    def origin(self) -> str: ...
    @property
    def severity(self) -> Severity: ...


def merge(intervals: Iterable[Interval]) -> list[Interval]:
    """Une trechos que se tocam ou se sobrepõem; descarta os vazios."""
    out: list[Interval] = []
    for lo, hi in sorted(i for i in intervals if i[1] > i[0]):
        if out and lo <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], hi))
        else:
            out.append((lo, hi))
    return out


def clip(intervals: Iterable[Interval], lo: float, hi: float) -> list[Interval]:
    return [(max(a, lo), min(b, hi)) for a, b in intervals if min(b, hi) > max(a, lo)]


def intersect(a: Sequence[Interval], b: Sequence[Interval]) -> list[Interval]:
    """Interseção de duas listas já unidas (ordenadas e sem sobreposição)."""
    out: list[Interval] = []
    i = j = 0
    while i < len(a) and j < len(b):
        lo, hi = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        if hi > lo:
            out.append((lo, hi))
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return out


def total(intervals: Iterable[Interval]) -> float:
    return sum(hi - lo for lo, hi in intervals)


@dataclass(frozen=True)
class TimeSplit:
    span_s: float
    normal_s: float
    out_s: float
    no_data_s: float

    def as_dict(self) -> dict[str, Any]:
        def pct(part: float) -> float:
            return round(part / self.span_s * 100, 1) if self.span_s > 0 else 0.0

        return {
            "span_s": self.span_s,
            "normal_s": self.normal_s,
            "out_s": self.out_s,
            "no_data_s": self.no_data_s,
            "normal_pct": pct(self.normal_s),
            "out_pct": pct(self.out_s),
            "no_data_pct": pct(self.no_data_s),
            "evidence_level": "FORJA_RULE",
        }


def split_time(span_s: float, *, data: Iterable[Interval], out: Iterable[Interval]) -> TimeSplit:
    """Divide o período: sem dados fora de `data`; fora do normal só onde há dado."""
    with_data = merge(clip(data, 0.0, span_s))
    out_with_data = intersect(merge(clip(out, 0.0, span_s)), with_data)
    data_s = total(with_data)
    out_s = total(out_with_data)
    return TimeSplit(span_s=span_s, normal_s=data_s - out_s, out_s=out_s, no_data_s=span_s - data_s)


def event_intervals(events: Iterable[EventLike], start: datetime, end: datetime) -> list[Interval]:
    """Trechos com evento de regra da Forja aberto, de atenção para cima. Aberto vai até o fim."""
    span = (end - start).total_seconds()
    raw: list[Interval] = []
    for e in events:
        if e.origin != COUNTED_ORIGIN or e.severity not in COUNTED_SEVERITIES:
            continue
        lo = (e.start_utc - start).total_seconds()
        hi = (e.end_utc - start).total_seconds() if e.end_utc is not None else span
        raw.append((lo, hi))
    return merge(clip(raw, 0.0, span))


def alarm_intervals(
    samples: Iterable[Sample], start: datetime, end: datetime, *, hold_s: float
) -> list[Interval]:
    """Trechos com o alarme do KCM ativo, pela leitura gravada.

    Cada leitura ativa vale até a leitura seguinte, no máximo `hold_s` depois dela (o limite de
    buraco do historiador). Leitura inativa, sem valor ou sem qualidade encerra o trecho.
    """
    span = (end - start).total_seconds()
    by_ts: dict[datetime, list[Sample]] = {}
    for s in samples:
        by_ts.setdefault(s.ts_utc, []).append(s)
    states = [
        ((ts - start).total_seconds(), alarm_state(group)) for ts, group in sorted(by_ts.items())
    ]
    raw: list[Interval] = []
    for i, (t, state) in enumerate(states):
        if state != ACTIVE:
            continue
        nxt = states[i + 1][0] if i + 1 < len(states) else span
        raw.append((t, min(nxt, t + hold_s)))
    return merge(clip(raw, 0.0, span))


__all__ = [
    "DEFINITION_PT",
    "TimeSplit",
    "alarm_intervals",
    "event_intervals",
    "merge",
    "split_time",
]
