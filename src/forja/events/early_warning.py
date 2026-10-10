"""Aviso antecipado: avaliação de tendência, desvio do padrão e combinação de variáveis.

Entrada: séries do historiador (as mesmas dos gráficos). Cada série vira uma grade regular em
que cada célula guarda a média ponderada no tempo das leituras utilizáveis. Leitura sem valor,
qualidade fora de `allowed_qualities` e trecho sem leitura ficam vazios: nada é interpolado.
Em resolução bruta, cada leitura vale até a próxima linha gravada (store-on-change), limitada a
`max_hold_s`, a mesma leitura em degrau dos gráficos.

Saída de cada sinal: atendido, não atendido ou dados insuficientes, com o número medido e o
texto em português. A regra combina os sinais por AND. Nada aqui prevê falha nem fala com o KCM.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from forja.domain import Quality, Series, get_tag, worst
from forja.events.ew_rules import EarlyWarningRule, Signal
from forja.events.what_changed import compute_delta, delta_kind_for, fmt_number_pt, with_unit
from forja.events.window_analysis import fmt_duration_pt

DEFAULT_CELLS = 120
DEFAULT_MAX_HOLD_S = 120.0
MIN_CELL_FILL = 0.5
"""Célula com menos que esta fração do tempo coberto por leitura fica vazia."""
MIN_FIT_POINTS = 5
EQ_TOL = 1e-9

SignalVerdict = Literal["MET", "NOT_MET", "INSUFFICIENT"]
RuleState = Literal["MET", "NOT_MET", "INSUFFICIENT"]


@dataclass(frozen=True)
class Segment:
    """Trecho [start_s, end_s) com valor constante (segundos desde o início da leitura)."""

    start_s: float
    end_s: float
    value: float


@dataclass(frozen=True)
class Grid:
    """Grade regular de uma variável entre `start` e `end`."""

    tag: str
    start: datetime
    end: datetime
    cell_s: float
    cells: tuple[float | None, ...]
    segments: tuple[Segment, ...]
    quality: Quality | None
    """Pior qualidade utilizável vista (SIMULATED quando o dado é do simulador)."""

    @property
    def span_s(self) -> float:
        return (self.end - self.start).total_seconds()

    def coverage(self, from_s: float = 0.0, to_s: float | None = None) -> float:
        """Fração do trecho [from_s, to_s) coberta por leitura utilizável."""
        to = self.span_s if to_s is None else to_s
        if to <= from_s:
            return 0.0
        covered = sum(max(0.0, min(s.end_s, to) - max(s.start_s, from_s)) for s in self.segments)
        return covered / (to - from_s)

    def mean(self, from_s: float, to_s: float) -> float | None:
        """Média ponderada no tempo das leituras em [from_s, to_s). None sem leitura."""
        total = 0.0
        weighted = 0.0
        for s in self.segments:
            overlap = min(s.end_s, to_s) - max(s.start_s, from_s)
            if overlap > 0:
                total += overlap
                weighted += overlap * s.value
        return weighted / total if total > 0 else None

    def fraction_equal(self, value: float, from_s: float = 0.0, to_s: float | None = None) -> float:
        """Fração do tempo COM leitura em que a variável ficou igual a `value`."""
        to = self.span_s if to_s is None else to_s
        covered = 0.0
        equal = 0.0
        for s in self.segments:
            overlap = min(s.end_s, to) - max(s.start_s, from_s)
            if overlap > 0:
                covered += overlap
                if math.isclose(s.value, value, abs_tol=EQ_TOL):
                    equal += overlap
        return equal / covered if covered > 0 else 0.0


def build_grid(
    series: Series,
    start: datetime,
    end: datetime,
    allowed: frozenset[Quality],
    *,
    cells: int = DEFAULT_CELLS,
    max_hold_s: float = DEFAULT_MAX_HOLD_S,
) -> Grid:
    """Série do historiador -> grade regular, sem interpolar buraco."""
    span = (end - start).total_seconds()
    points = sorted(series.points, key=lambda p: p.ts_utc)
    raw = series.resolution == "raw"
    segments: list[Segment] = []
    qualities: list[Quality] = []
    for i, point in enumerate(points):
        t0 = (point.ts_utc - start).total_seconds()
        if raw:
            nxt = (points[i + 1].ts_utc - start).total_seconds() if i + 1 < len(points) else span
            t1 = min(nxt, t0 + max_hold_s)
        else:
            t1 = t0 + max(1, series.bucket_s)
        t0, t1 = max(t0, 0.0), min(t1, span)
        usable = point.value is not None and point.quality in allowed
        if usable and t1 > t0 and math.isfinite(float(point.value or 0.0)):
            segments.append(Segment(t0, t1, float(point.value or 0.0)))
            qualities.append(point.quality)
    cell_s = span / cells if cells > 0 else span
    values: list[float | None] = []
    for c in range(cells):
        lo, hi = c * cell_s, (c + 1) * cell_s
        covered = sum(max(0.0, min(s.end_s, hi) - max(s.start_s, lo)) for s in segments)
        if covered < MIN_CELL_FILL * cell_s:
            values.append(None)
            continue
        weighted = sum(max(0.0, min(s.end_s, hi) - max(s.start_s, lo)) * s.value for s in segments)
        values.append(weighted / covered)
    return Grid(
        tag=series.tag,
        start=start,
        end=end,
        cell_s=cell_s,
        cells=tuple(values),
        segments=tuple(segments),
        quality=worst(qualities) if qualities else None,
    )


@dataclass(frozen=True)
class LineFit:
    slope: float
    """Unidade da variável por segundo."""
    intercept: float
    r2: float
    points: int


def fit_line(xs: Sequence[float], ys: Sequence[float]) -> LineFit | None:
    """Mínimos quadrados. Série plana tem R² 0 (não há tendência para explicar)."""
    n = len(xs)
    if n < MIN_FIT_POINTS:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    if sxx <= 0:
        return None
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys, strict=True))
    r2 = 0.0 if ss_tot <= EQ_TOL else max(0.0, 1.0 - ss_res / ss_tot)
    return LineFit(slope=slope, intercept=intercept, r2=r2, points=n)


@dataclass(frozen=True)
class SignalOutcome:
    """Resultado de um sinal numa avaliação."""

    signal: Signal
    verdict: SignalVerdict
    before: float | None
    """Referência: início da reta (tendência) ou padrão (desvio)."""
    now: float | None
    measured: float | None
    """Variação (tendência, desvio), distância em % (proximidade) ou fração (estado)."""
    fit: float | None
    coverage: float
    text_pt: str
    limit_pt: str


@dataclass(frozen=True)
class RuleEvaluation:
    rule: EarlyWarningRule
    equipment_id: str
    ts_utc: datetime
    state: RuleState
    signals: tuple[SignalOutcome, ...]
    quality: Quality | None
    cells: Mapping[str, tuple[float | None, ...]] = field(default_factory=dict)
    """Grade de cada variável lida (para o mini gráfico da tela). None = sem leitura."""
    cell_s: float = 0.0

    @property
    def met_count(self) -> int:
        return sum(1 for s in self.signals if s.verdict == "MET")


def _change_unit(tag: str) -> tuple[str, int]:
    """Unidade e casas do limite `min_change` para a variável."""
    kind = delta_kind_for(tag)
    if kind == "pct":
        return "%", 1
    if kind == "points":
        return " pontos", 1
    meta = get_tag(tag)
    return f" {meta.unit}" if meta.unit else "", max(0, meta.decimals)


def _fmt_change(tag: str, value: float, *, limit: bool = False) -> str:
    """Variação com a unidade da convenção. Limite configurado inteiro sai sem casas."""
    unit, decimals = _change_unit(tag)
    if limit and float(value).is_integer():
        decimals = 0
    return f"{fmt_number_pt(abs(value), decimals)}{unit}"


def _is_zero_shown(text: str) -> bool:
    """True quando o número exibido arredonda para zero ("0,0 pontos", "0%")."""
    digits = [c for c in text if c.isdigit()]
    return bool(digits) and all(c == "0" for c in digits)


def _fmt_limit(value: float, decimals: int = 1) -> str:
    return fmt_number_pt(value, 0 if float(value).is_integer() else decimals)


def _value_pt(tag: str, value: float | None) -> str:
    meta = get_tag(tag)
    if value is None:
        return "sem leitura"
    return with_unit(fmt_number_pt(value, meta.decimals), meta.unit)


def _direction_ok(direction: str, delta: float, min_change: float) -> bool:
    if direction == "up":
        return delta >= min_change
    if direction == "down":
        return delta <= -min_change
    return abs(delta) >= min_change


def _direction_limit_pt(signal: Signal, span_pt: str) -> str:
    amount = _fmt_change(signal.tag, signal.min_change or 0.0, limit=True)
    verb = {"up": "subir", "down": "cair"}.get(signal.direction, "variar")
    return f"{verb} pelo menos {amount} em {span_pt}"


def _insufficient(signal: Signal, coverage: float, need: float, limit_pt: str) -> SignalOutcome:
    text = (
        f"dados insuficientes: leitura em {fmt_number_pt(coverage * 100, 0)}% do trecho "
        f"(mínimo {fmt_number_pt(need * 100, 0)}%)"
    )
    return SignalOutcome(signal, "INSUFFICIENT", None, None, None, None, coverage, text, limit_pt)


def evaluate_trend(signal: Signal, grid: Grid, rule: EarlyWarningRule) -> SignalOutcome:
    from_s = grid.span_s - rule.window_s
    span_pt = fmt_duration_pt(rule.window_s)
    limit = _direction_limit_pt(signal, span_pt)
    if signal.min_fit > 0:
        limit += f", reta com ajuste (R²) de pelo menos {fmt_number_pt(signal.min_fit, 2)}"
    coverage = grid.coverage(from_s)
    if coverage < rule.min_coverage:
        return _insufficient(signal, coverage, rule.min_coverage, limit)
    xs: list[float] = []
    ys: list[float] = []
    for i, value in enumerate(grid.cells):
        center = (i + 0.5) * grid.cell_s
        if value is not None and center >= from_s:
            xs.append(center - from_s)
            ys.append(value)
    line = fit_line(xs, ys)
    if line is None:
        return _insufficient(signal, coverage, rule.min_coverage, limit)
    before = line.intercept
    now = line.intercept + line.slope * rule.window_s
    delta = compute_delta(before, now, delta_kind_for(signal.tag))
    if delta is None:
        text = "padrão em zero: variação percentual não se aplica"
        return SignalOutcome(
            signal, "INSUFFICIENT", before, now, None, line.r2, coverage, text, limit
        )
    met = _direction_ok(signal.direction, delta, signal.min_change or 0.0) and (
        line.r2 >= signal.min_fit
    )
    shown = _fmt_change(signal.tag, delta)
    if _is_zero_shown(shown):
        head = f"ficou estável em {span_pt}"
    else:
        head = f"{'subiu' if delta > 0 else 'caiu'} {shown} em {span_pt}"
    text = (
        f"{head} (de {_value_pt(signal.tag, before)} para {_value_pt(signal.tag, now)}; "
        f"ajuste {fmt_number_pt(line.r2, 2)})"
    )
    verdict: SignalVerdict = "MET" if met else "NOT_MET"
    return SignalOutcome(signal, verdict, before, now, delta, line.r2, coverage, text, limit)


def _baseline_span(rule: EarlyWarningRule, grid: Grid) -> tuple[float, float, str]:
    """Trecho do padrão na grade e como ele é descrito."""
    window_from = grid.span_s - rule.window_s
    if rule.baseline == "before_window":
        base_s = float(rule.baseline_s or 0)
        return (
            window_from - base_s,
            window_from,
            (f"padrão das {fmt_duration_pt(base_s)} antes da janela"),
        )
    return window_from, window_from + rule.recent_s, "padrão do início da janela"


def evaluate_deviation(signal: Signal, grid: Grid, rule: EarlyWarningRule) -> SignalOutcome:
    base_from, base_to, base_pt = _baseline_span(rule, grid)
    recent_from = grid.span_s - rule.recent_s
    recent_pt = fmt_duration_pt(rule.recent_s)
    limit = _direction_limit_pt(signal, "relação ao " + base_pt)
    coverage = min(grid.coverage(base_from, base_to), grid.coverage(recent_from))
    if coverage < rule.min_coverage:
        return _insufficient(signal, coverage, rule.min_coverage, limit)
    before = grid.mean(base_from, base_to)
    now = grid.mean(recent_from, grid.span_s)
    delta = compute_delta(before, now, delta_kind_for(signal.tag))
    if before is None or now is None or delta is None:
        text = "padrão em zero ou sem leitura: desvio não se aplica"
        return SignalOutcome(signal, "INSUFFICIENT", before, now, None, None, coverage, text, limit)
    met = _direction_ok(signal.direction, delta, signal.min_change or 0.0)
    verb = "acima" if delta > 0 else "abaixo" if delta < 0 else "igual"
    text = (
        f"média dos últimos {recent_pt}: {_value_pt(signal.tag, now)}, "
        f"{_fmt_change(signal.tag, delta)} {verb} do {base_pt} ({_value_pt(signal.tag, before)})"
    )
    verdict: SignalVerdict = "MET" if met else "NOT_MET"
    return SignalOutcome(signal, verdict, before, now, delta, None, coverage, text, limit)


def evaluate_stable(signal: Signal, grid: Grid, rule: EarlyWarningRule) -> SignalOutcome:
    base_from, base_to, base_pt = _baseline_span(rule, grid)
    recent_from = grid.span_s - rule.recent_s
    amount = _fmt_change(signal.tag, signal.max_change or 0.0, limit=True)
    limit = f"variar no máximo {amount} em relação ao {base_pt}"
    coverage = min(grid.coverage(base_from, base_to), grid.coverage(recent_from))
    if coverage < rule.min_coverage:
        return _insufficient(signal, coverage, rule.min_coverage, limit)
    before = grid.mean(base_from, base_to)
    now = grid.mean(recent_from, grid.span_s)
    delta = compute_delta(before, now, delta_kind_for(signal.tag))
    if before is None or now is None or delta is None:
        text = "padrão em zero ou sem leitura: estabilidade não se aplica"
        return SignalOutcome(signal, "INSUFFICIENT", before, now, None, None, coverage, text, limit)
    met = abs(delta) <= (signal.max_change or 0.0) + EQ_TOL
    text = (
        f"{_value_pt(signal.tag, now)} agora, variação de {_fmt_change(signal.tag, delta)} "
        f"em relação ao {base_pt} ({_value_pt(signal.tag, before)})"
    )
    verdict: SignalVerdict = "MET" if met else "NOT_MET"
    return SignalOutcome(signal, verdict, before, now, delta, None, coverage, text, limit)


def evaluate_near_reference(
    signal: Signal, grid: Grid, ref: Grid, rule: EarlyWarningRule
) -> SignalOutcome:
    ref_tag = signal.ref_tag or ""
    ref_label = get_tag(ref_tag).label_pt if ref_tag else "referência"
    limit = (
        f"distância de até {_fmt_limit(signal.max_deviation_pct or 0.0)}% em relação a "
        f"{ref_label}, nos últimos {fmt_duration_pt(rule.recent_s)}"
    )
    recent_from = grid.span_s - rule.recent_s
    coverage = min(grid.coverage(recent_from), ref.coverage(recent_from))
    if coverage < rule.min_coverage:
        return _insufficient(signal, coverage, rule.min_coverage, limit)
    now = grid.mean(recent_from, grid.span_s)
    reference = ref.mean(recent_from, ref.span_s)
    if now is None or reference is None or abs(reference) < EQ_TOL:
        text = f"{ref_label} em zero ou sem leitura: a proximidade não se aplica"
        return SignalOutcome(
            signal, "INSUFFICIENT", reference, now, None, None, coverage, text, limit
        )
    distance = abs(now - reference) / abs(reference) * 100.0
    met = distance <= (signal.max_deviation_pct or 0.0)
    text = (
        f"{_value_pt(signal.tag, now)}; {ref_label}: {_value_pt(ref_tag, reference)}; "
        f"distância de {fmt_number_pt(distance, 1)}%"
    )
    verdict: SignalVerdict = "MET" if met else "NOT_MET"
    return SignalOutcome(signal, verdict, reference, now, distance, None, coverage, text, limit)


def evaluate_state(signal: Signal, grid: Grid, rule: EarlyWarningRule) -> SignalOutcome:
    from forja.events.what_changed import discrete_value_pt

    from_s = grid.span_s - rule.window_s
    expected = float(signal.value or 0.0)
    expected_pt = discrete_value_pt(signal.tag, expected)
    limit = (
        f"{expected_pt} em pelo menos {fmt_number_pt(signal.min_fraction * 100, 0)}% da janela "
        f"de {fmt_duration_pt(rule.window_s)}"
    )
    coverage = grid.coverage(from_s)
    if coverage < rule.min_coverage:
        return _insufficient(signal, coverage, rule.min_coverage, limit)
    fraction = grid.fraction_equal(expected, from_s)
    met = fraction + EQ_TOL >= signal.min_fraction
    text = f"{expected_pt} em {fmt_number_pt(fraction * 100, 0)}% do tempo com leitura"
    verdict: SignalVerdict = "MET" if met else "NOT_MET"
    return SignalOutcome(signal, verdict, None, None, fraction, None, coverage, text, limit)


def evaluate_signal(
    signal: Signal, grids: Mapping[str, Grid], rule: EarlyWarningRule
) -> SignalOutcome:
    grid = grids[signal.tag]
    if signal.kind == "trend":
        return evaluate_trend(signal, grid, rule)
    if signal.kind == "deviation":
        return evaluate_deviation(signal, grid, rule)
    if signal.kind == "stable":
        return evaluate_stable(signal, grid, rule)
    if signal.kind == "near_reference":
        return evaluate_near_reference(signal, grid, grids[signal.ref_tag or ""], rule)
    return evaluate_state(signal, grid, rule)


def combine(outcomes: Sequence[SignalOutcome]) -> RuleState:
    """AND: um sinal não atendido basta para não atender; faltando dado, insuficiente."""
    verdicts = {o.verdict for o in outcomes}
    if "NOT_MET" in verdicts:
        return "NOT_MET"
    if "INSUFFICIENT" in verdicts:
        return "INSUFFICIENT"
    return "MET"


def evaluate_rule(
    rule: EarlyWarningRule,
    equipment_id: str,
    series: Mapping[str, Series],
    now: datetime,
    *,
    cells: int = DEFAULT_CELLS,
    max_hold_s: float = DEFAULT_MAX_HOLD_S,
) -> RuleEvaluation:
    """Avalia uma regra com as séries já lidas do historiador (de now - lookback_s até now)."""
    start = now - timedelta(seconds=rule.lookback_s)
    allowed = frozenset(rule.allowed_qualities)
    grids = {
        tag: build_grid(s, start, now, allowed, cells=cells, max_hold_s=max_hold_s)
        for tag, s in series.items()
    }
    outcomes = tuple(evaluate_signal(signal, grids, rule) for signal in rule.signals)
    qualities = [g.quality for g in grids.values() if g.quality is not None]
    return RuleEvaluation(
        rule=rule,
        equipment_id=equipment_id,
        ts_utc=now,
        state=combine(outcomes),
        signals=outcomes,
        quality=worst(qualities) if qualities else None,
        cells={tag: g.cells for tag, g in grids.items()},
        cell_s=next(iter(grids.values())).cell_s if grids else 0.0,
    )


__all__ = [
    "DEFAULT_CELLS",
    "Grid",
    "LineFit",
    "RuleEvaluation",
    "RuleState",
    "SignalOutcome",
    "SignalVerdict",
    "build_grid",
    "combine",
    "evaluate_rule",
    "evaluate_signal",
    "fit_line",
]
