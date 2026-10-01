"""Avaliacao instantanea de uma Condition contra o lote atual e o buffer.

Regras de ouro:
- Condicoes de valor so enxergam amostras cuja qualidade esta em rule.allowed_qualities
  (sempre um subconjunto de GOOD/SIMULATED/UNCERTAIN). COMM_ERROR, STALE e BAD nunca viram numero.
- quality_is olha a qualidade em si (e a unica que pode 'ver' COMM_ERROR).
- Nada e interpolado: janela sem historico suficiente = condicao falsa.
- drop/rise_pct_over_window medem em pontos quando a tag e '%' e em percentual nas demais,
  a mesma convencao do componente 'O que mudou'.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median

from forja.domain import Quality, Sample, get_tag
from forja.events.prewindow import SampleBuffer
from forja.events.rules import ANY_TAG, Condition

MIN_WINDOW_COVERAGE = 0.5
"""Fracao minima da janela que o historico precisa cobrir para a referencia valer."""
HEAD_FRACTION = 0.75
"""Amostras com idade >= HEAD_FRACTION x window_s formam a referencia (inicio da janela)."""
EQ_TOL = 1e-9


@dataclass(frozen=True)
class EvalContext:
    """Tudo que uma condicao precisa para ser avaliada em um instante."""

    ts: datetime
    now: Mapping[str, Sample]
    batch_quality: Quality
    history: SampleBuffer
    allowed: frozenset[Quality]


@dataclass(frozen=True)
class WindowRef:
    value: float
    ts: datetime


def usable_now(ctx: EvalContext, tag: str) -> float | None:
    """Valor atual da tag se existir, for numerico e tiver qualidade permitida."""
    s = ctx.now.get(tag)
    if s is None or s.value is None or s.quality not in ctx.allowed:
        return None
    return float(s.value)


def window_reference(ctx: EvalContext, tag: str, window_s: int) -> WindowRef | None:
    """Referencia do inicio da janela [ts - window_s, ts).

    Mediana das amostras com idade >= 75% da janela; se nao houver, a mais antiga.
    Exige que o historico cubra ao menos metade da janela. Caso contrario: None.
    """
    start = ctx.ts - timedelta(seconds=window_s)
    samples = ctx.history.tag_values(tag, start, ctx.ts, ctx.allowed)
    if not samples:
        return None
    oldest_age = (ctx.ts - samples[0].ts_utc).total_seconds()
    if oldest_age < MIN_WINDOW_COVERAGE * window_s:
        return None
    cutoff = ctx.ts - timedelta(seconds=HEAD_FRACTION * window_s)
    head = [s for s in samples if s.ts_utc <= cutoff] or [samples[0]]
    values = [float(s.value) for s in head if s.value is not None]
    return WindowRef(value=float(median(values)), ts=head[0].ts_utc)


def delta_in_kind(tag: str, ref: float, now: float) -> float | None:
    """Variacao em pontos (tag em %) ou em percentual relativo (outras). None se ref == 0."""
    if get_tag(tag).unit == "%":
        return now - ref
    if abs(ref) < EQ_TOL:
        return None
    return (now - ref) / abs(ref) * 100.0


def _threshold(ctx: EvalContext, cond: Condition, value: float) -> float | None:
    if cond.ref_tag is None:
        return value
    ref = usable_now(ctx, cond.ref_tag)
    if ref is None:
        return None
    return value * ref


def _num(value: float | str | None) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError("value numérico esperado")
    return float(value)


def _gt(cond: Condition, ctx: EvalContext) -> bool:
    now = usable_now(ctx, cond.tag)
    limit = _threshold(ctx, cond, _num(cond.value))
    return now is not None and limit is not None and now > limit


def _lt(cond: Condition, ctx: EvalContext) -> bool:
    now = usable_now(ctx, cond.tag)
    limit = _threshold(ctx, cond, _num(cond.value))
    return now is not None and limit is not None and now < limit


def _between(cond: Condition, ctx: EvalContext) -> bool:
    now = usable_now(ctx, cond.tag)
    lo = _threshold(ctx, cond, _num(cond.value))
    hi = _threshold(ctx, cond, _num(cond.value2))
    return now is not None and lo is not None and hi is not None and lo <= now <= hi


def _equals(cond: Condition, ctx: EvalContext) -> bool:
    now = usable_now(ctx, cond.tag)
    if now is None:
        return False
    if isinstance(cond.value, str):
        return str(now) == cond.value or _fmt_plain(now) == cond.value
    return math.isclose(now, _num(cond.value), abs_tol=EQ_TOL)


def _fmt_plain(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)


def _changed(cond: Condition, ctx: EvalContext) -> bool:
    """Valor atual difere do anterior; com value, exige que tenha mudado PARA value."""
    now = usable_now(ctx, cond.tag)
    prev = ctx.history.previous(cond.tag, ctx.ts, ctx.allowed)
    if now is None or prev is None or prev.value is None:
        return False
    if math.isclose(now, float(prev.value), abs_tol=EQ_TOL):
        return False
    if cond.value is None:
        return True
    if isinstance(cond.value, str):
        return _fmt_plain(now) == cond.value
    return math.isclose(now, _num(cond.value), abs_tol=EQ_TOL)


def _quality_is(cond: Condition, ctx: EvalContext) -> bool:
    wanted = Quality(str(cond.value))
    if cond.tag == ANY_TAG:
        return ctx.batch_quality == wanted
    s = ctx.now.get(cond.tag)
    return s is not None and s.quality == wanted


def _drop(cond: Condition, ctx: EvalContext) -> bool:
    return _window_delta(cond, ctx, sign=-1.0)


def _rise(cond: Condition, ctx: EvalContext) -> bool:
    return _window_delta(cond, ctx, sign=1.0)


def _window_delta(cond: Condition, ctx: EvalContext, sign: float) -> bool:
    now = usable_now(ctx, cond.tag)
    ref = window_reference(ctx, cond.tag, int(cond.window_s or 0))
    if now is None or ref is None:
        return False
    delta = delta_in_kind(cond.tag, ref.value, now)
    if delta is None:
        return False
    return sign * delta >= _num(cond.value)


def _rate_of_change(cond: Condition, ctx: EvalContext) -> bool:
    """|variacao por segundo| entre a referencia da janela e agora >= value."""
    now = usable_now(ctx, cond.tag)
    ref = window_reference(ctx, cond.tag, int(cond.window_s or 0))
    if now is None or ref is None:
        return False
    elapsed = (ctx.ts - ref.ts).total_seconds()
    if elapsed <= 0:
        return False
    return abs((now - ref.value) / elapsed) >= _num(cond.value)


def _persists_for(cond: Condition, ctx: EvalContext) -> bool:
    """Leitura congelada: valor identico (e igual a value, se dado) durante persist_s."""
    now = usable_now(ctx, cond.tag)
    if now is None:
        return False
    persist = int(cond.persist_s or 0)
    start = ctx.ts - timedelta(seconds=persist)
    samples = ctx.history.tag_values(cond.tag, start, ctx.ts, ctx.allowed, include_end=True)
    if not samples:
        return False
    span = (ctx.ts - samples[0].ts_utc).total_seconds()
    if span + EQ_TOL < persist:
        return False
    if cond.value is not None and not math.isclose(now, _num(cond.value), abs_tol=EQ_TOL):
        return False
    return all(
        s.value is not None and math.isclose(float(s.value), now, abs_tol=EQ_TOL) for s in samples
    )


_EVALUATORS: dict[str, Callable[[Condition, EvalContext], bool]] = {
    "gt": _gt,
    "lt": _lt,
    "between": _between,
    "equals": _equals,
    "changed": _changed,
    "quality_is": _quality_is,
    "drop_pct_over_window": _drop,
    "rise_pct_over_window": _rise,
    "rate_of_change": _rate_of_change,
    "persists_for": _persists_for,
}


def evaluate(cond: Condition, ctx: EvalContext) -> bool:
    """Avaliacao instantanea (sem persistencia). Persistencia e papel do motor."""
    return _EVALUATORS[cond.op](cond, ctx)
