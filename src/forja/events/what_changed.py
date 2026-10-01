"""Componente 'O QUE MUDOU' (spec §27; Documento Mestre §22).

ANTES = mediana do que a variavel fazia antes de sair do padrao.
AGORA = valor no instante da deteccao.
VARIACAO = percentual (kg/h, kg/m, kg), pontos (%) ou absoluta (rpm e outras).
ts_start_utc = primeiro instante em que a variavel saiu do padrao e nao voltou.
A lista sai ordenada por ts_start_utc: a primeira a mudar recebe changed_first=True.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from statistics import median
from typing import Literal

from forja.domain import Quality, Sample, WhatChangedItem, get_tag

DeltaKind = Literal["pct", "points", "abs", "none"]

USABLE: frozenset[Quality] = frozenset(q for q in Quality if q.counts_for_rules)
PCT_UNITS: frozenset[str] = frozenset({"kg/h", "kg/m", "kg"})
MAD_FACTOR = 3.0
MIN_HEAD = 3
HEAD_FRACTION = 0.1
"""Fracao inicial do historico usada como linha de base. Pequena de proposito: uma rampa que
comeca cedo contaminaria a mediana se o 'antes' fosse um terco da janela."""
REL_FLOOR = 0.02
POINTS_FLOOR = 1.0
ABS_FLOOR = 1.0


def delta_kind_for(tag: str) -> DeltaKind:
    unit = get_tag(tag).unit
    if unit in PCT_UNITS:
        return "pct"
    if unit == "%":
        return "points"
    return "abs"


def fmt_number_pt(value: float | None, decimals: int) -> str:
    """Numero em portugues: virgula decimal, sem separador de milhar."""
    if value is None:
        return "—"
    return f"{value:.{decimals}f}".replace(".", ",")


def with_unit(text: str, unit: str) -> str:
    return f"{text} {unit}" if unit else text


def delta_text_pt(delta: float | None, kind: DeltaKind, unit: str, decimals: int) -> str:
    if delta is None or kind == "none":
        return "sem variação mensurável"
    arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "=")
    mag = abs(delta)
    if kind == "pct":
        return f"{arrow} {fmt_number_pt(mag, 1)}%"
    if kind == "points":
        return f"{arrow} {fmt_number_pt(mag, 0)} pontos"
    return f"{arrow} {with_unit(fmt_number_pt(mag, decimals), unit)}"


def compute_delta(before: float | None, now: float | None, kind: DeltaKind) -> float | None:
    if before is None or now is None:
        return None
    if kind == "pct":
        if abs(before) < 1e-12:
            return None
        return (now - before) / abs(before) * 100.0
    return now - before


@dataclass(frozen=True)
class _Departure:
    """Resultado da busca de 'quando saiu do padrao'."""

    out_of_pattern: bool
    ts_start: datetime | None
    before_values: list[float]


def _tolerance(kind: DeltaKind, baseline: float, head: Sequence[float]) -> float:
    mad = float(median([abs(v - baseline) for v in head])) if head else 0.0
    if kind == "points":
        floor = POINTS_FLOOR
    elif abs(baseline) < 1e-12:
        floor = ABS_FLOOR
    else:
        floor = REL_FLOOR * abs(baseline)
    return max(MAD_FACTOR * mad, floor)


def _departure(samples: Sequence[Sample], now: float | None, kind: DeltaKind) -> _Departure:
    """Primeiro instante a partir do qual a variavel ficou fora do padrao ate agora.

    Padrao = mediana dos primeiros 10% das amostras (pelo menos 3). Tolerancia = 3 x MAD,
    com piso de 2% (relativo), 1 ponto (%) ou 1 unidade (absoluto).
    """
    values = [(s.ts_utc, float(s.value)) for s in samples if s.value is not None]
    all_values = [v for _, v in values]
    if not values or now is None:
        return _Departure(False, None, all_values)
    head = all_values[: max(MIN_HEAD, int(len(values) * HEAD_FRACTION))]
    baseline = float(median(head))
    tol = _tolerance(kind, baseline, head)
    direction = now - baseline
    if abs(direction) <= tol:
        return _Departure(False, None, all_values)
    idx = len(values)
    while idx > 0:
        dev = values[idx - 1][1] - baseline
        if abs(dev) > tol and (dev > 0) == (direction > 0):
            idx -= 1
        else:
            break
    if idx == len(values):
        return _Departure(True, None, all_values)
    return _Departure(True, values[idx][0], all_values[:idx] or head)


def _item(tag: str, pre: Sequence[Sample], now_sample: Sample | None) -> WhatChangedItem:
    meta = get_tag(tag)
    kind: DeltaKind = delta_kind_for(tag)
    pre_tag = [s for s in pre if s.tag == tag and s.quality in USABLE and s.value is not None]
    now_value: float | None = None
    if now_sample is not None and now_sample.value is not None and now_sample.quality in USABLE:
        now_value = float(now_sample.value)
    dep = _departure(pre_tag, now_value, kind)
    before = float(median(dep.before_values)) if dep.before_values else None
    delta = compute_delta(before, now_value, kind)
    ts_start = dep.ts_start
    if dep.out_of_pattern and ts_start is None and now_sample is not None:
        ts_start = now_sample.ts_utc
    shown_kind: DeltaKind = kind if delta is not None else "none"
    text = (
        f"Antes: {with_unit(fmt_number_pt(before, meta.decimals), meta.unit)} · "
        f"Agora: {with_unit(fmt_number_pt(now_value, meta.decimals), meta.unit)} · "
        f"{delta_text_pt(delta, shown_kind, meta.unit, meta.decimals)}"
    )
    return WhatChangedItem(
        tag=tag,
        label_pt=meta.label_pt,
        unit=meta.unit,
        before=before,
        now=now_value,
        delta=delta,
        delta_kind=shown_kind,
        changed_first=False,
        ts_start_utc=ts_start,
        text_pt=text,
    )


def compute_what_changed(
    pre: Sequence[Sample], now: Mapping[str, Sample], tags: Sequence[str]
) -> tuple[WhatChangedItem, ...]:
    """ANTES/AGORA/VARIACAO por tag, ordenado por quem saiu do padrao primeiro.

    `pre` sao as amostras anteriores a deteccao (pre-janela + durante), `now` o valor na deteccao.
    Itens sem ts_start ficam ao final, na ordem de `tags`. Empate de ts_start: ordem de `tags`.
    """
    items = [_item(tag, pre, now.get(tag)) for tag in dict.fromkeys(tags)]
    with_ts = [i for i in items if i.ts_start_utc is not None]
    without = [i for i in items if i.ts_start_utc is None]
    with_ts.sort(key=lambda i: i.ts_start_utc or datetime.max)
    ordered = [*with_ts, *without]
    if with_ts:
        ordered[0] = ordered[0].model_copy(update={"changed_first": True})
    return tuple(ordered)
