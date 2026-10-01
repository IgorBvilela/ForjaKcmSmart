"""Componente 'O QUE MUDOU' (spec §27; Documento Mestre §22).

Variaveis continuas (TagKind.CONTINUOUS):
ANTES = mediana do que a variavel fazia antes de sair do padrao.
AGORA = valor no instante da deteccao.
VARIACAO = percentual (kg/h, kg/m, kg), pontos (%) ou absoluta (rpm e outras).
ts_start_utc = primeiro instante em que a variavel saiu do padrao e nao voltou.

Variaveis discretas e status brutos (TagKind.DISCRETE / STATUS_RAW):
so entram quando mudaram de valor, sempre em palavras ('passou de Parado para Em operação'),
nunca numero com decimais, sem variacao numerica (delta_kind 'none').
ts_start_utc = primeiro instante com o valor atual depois da ultima mudanca.

A lista sai ordenada por ts_start_utc: a primeira a mudar recebe changed_first=True.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from statistics import median
from typing import Literal

from forja.domain import Quality, Sample, SemanticTag, TagKind, WhatChangedItem, get_tag

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

NO_READING_PT = "sem leitura"

# Codificacao do SIMULADOR para as tags discretas (config/mappings/simulator_wbf.yaml e
# forja/drivers/simulator/physics_wbf.py). O mapping real normaliza para esta mesma convencao
# da tag semantica; valor fora do mapa sai como numero inteiro, nunca inventado.
MACHINE_STATE_PT: dict[int, str] = {0: "Parado", 1: "Em operação", 2: "Em alarme"}
YES_NO_PT: dict[int, str] = {0: "não", 1: "sim"}
CONTROL_MODE_PT: dict[int, str] = {0: "volumétrico", 1: "gravimétrico"}

DetailFor = Callable[[str, float], str | None]
"""Complemento opcional vindo de fora para um valor discreto (ex.: titulo do alarme no catalogo).
Recebe (tag, valor) e devolve texto ou None."""


def delta_kind_for(tag: str) -> DeltaKind:
    meta = get_tag(tag)
    if meta.kind is not TagKind.CONTINUOUS:
        return "none"
    unit = meta.unit
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
    """'2,00 kg/m', '71,3%' (percentual colado, como no resumo), '62 rpm'."""
    if not unit:
        return text
    if unit == "%":
        return f"{text}%"
    return f"{text} {unit}"


def value_pt(value: float | None, meta: SemanticTag) -> str:
    """Valor continuo em portugues com unidade; None vira 'sem leitura'."""
    if value is None:
        return NO_READING_PT
    return with_unit(fmt_number_pt(value, meta.decimals), meta.unit)


def _as_int(value: float) -> int | None:
    return int(value) if float(value).is_integer() else None


def discrete_value_pt(tag: str, value: float | None, detail: str | None = None) -> str:
    """Valor discreto em palavras. Fora do mapa: numero inteiro. `detail` entra entre parenteses."""
    if value is None:
        return NO_READING_PT
    code = _as_int(value)
    base: str | None = None
    if code is not None:
        if tag == "machine_state":
            base = MACHINE_STATE_PT.get(code)
        elif tag == "alarm_active":
            base = YES_NO_PT.get(code)
        elif tag == "control_mode":
            base = CONTROL_MODE_PT.get(code)
        elif tag == "alarm_code":
            base = "nenhum alarme" if code == 0 else f"alarme {code}"
        elif tag == "stop_by":
            base = "nenhum" if code == 0 else f"código {code}"
    if base is None:
        base = fmt_number_pt(value, 0 if code is not None else get_tag(tag).decimals)
    return f"{base} ({detail})" if detail else base


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


def _usable(pre: Sequence[Sample], tag: str) -> list[Sample]:
    return [s for s in pre if s.tag == tag and s.quality in USABLE and s.value is not None]


def _now_value(now_sample: Sample | None) -> float | None:
    if now_sample is not None and now_sample.value is not None and now_sample.quality in USABLE:
        return float(now_sample.value)
    return None


def _continuous_item(
    tag: str, meta: SemanticTag, pre_tag: Sequence[Sample], now_sample: Sample | None
) -> WhatChangedItem | None:
    """Continua com ANTES/AGORA/VARIACAO. Sem nenhuma leitura utilizavel, nada a comparar."""
    kind: DeltaKind = delta_kind_for(tag)
    now_value = _now_value(now_sample)
    dep = _departure(pre_tag, now_value, kind)
    before = float(median(dep.before_values)) if dep.before_values else None
    if before is None and now_value is None:
        return None
    delta = compute_delta(before, now_value, kind)
    ts_start = dep.ts_start
    if dep.out_of_pattern and ts_start is None and now_sample is not None:
        ts_start = now_sample.ts_utc
    shown_kind: DeltaKind = kind if delta is not None else "none"
    text = (
        f"Antes: {value_pt(before, meta)} · Agora: {value_pt(now_value, meta)} · "
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


def _discrete_item(
    tag: str,
    meta: SemanticTag,
    pre_tag: Sequence[Sample],
    now_sample: Sample | None,
    detail_for: DetailFor | None,
) -> WhatChangedItem | None:
    """Discreta so conta quando mudou: ANTES = valor antes da ultima mudanca, AGORA = atual."""
    now_value = _now_value(now_sample)
    if now_value is None or now_sample is None:
        return None
    history = [(s.ts_utc, float(s.value)) for s in pre_tag if s.value is not None]
    idx = next((i for i in range(len(history) - 1, -1, -1) if history[i][1] != now_value), None)
    if idx is None:
        return None
    before = history[idx][1]
    ts_start = history[idx + 1][0] if idx + 1 < len(history) else now_sample.ts_utc

    def label(value: float) -> str:
        detail = detail_for(tag, value) if detail_for is not None else None
        return discrete_value_pt(tag, value, detail)

    return WhatChangedItem(
        tag=tag,
        label_pt=meta.label_pt,
        unit=meta.unit,
        before=before,
        now=now_value,
        delta=None,
        delta_kind="none",
        changed_first=False,
        ts_start_utc=ts_start,
        text_pt=f"passou de {label(before)} para {label(now_value)}",
    )


def _item(
    tag: str, pre: Sequence[Sample], now_sample: Sample | None, detail_for: DetailFor | None
) -> WhatChangedItem | None:
    meta = get_tag(tag)
    pre_tag = _usable(pre, tag)
    if meta.kind is TagKind.CONTINUOUS:
        return _continuous_item(tag, meta, pre_tag, now_sample)
    return _discrete_item(tag, meta, pre_tag, now_sample, detail_for)


def compute_what_changed(
    pre: Sequence[Sample],
    now: Mapping[str, Sample],
    tags: Sequence[str],
    detail_for: DetailFor | None = None,
) -> tuple[WhatChangedItem, ...]:
    """ANTES/AGORA/VARIACAO por tag, ordenado por quem saiu do padrao primeiro.

    `pre` sao as amostras anteriores a deteccao (pre-janela + durante), `now` o valor na deteccao.
    Ficam de fora: discreta que nao mudou de valor e continua sem nenhuma leitura utilizavel
    (nem antes, nem agora). Itens sem ts_start ficam ao final, na ordem de `tags`. Empate de
    ts_start: ordem de `tags`.
    """
    items = [
        item
        for item in (_item(tag, pre, now.get(tag), detail_for) for tag in dict.fromkeys(tags))
        if item is not None
    ]
    with_ts = [i for i in items if i.ts_start_utc is not None]
    without = [i for i in items if i.ts_start_utc is None]
    with_ts.sort(key=lambda i: i.ts_start_utc or datetime.max)
    ordered = [*with_ts, *without]
    if with_ts:
        ordered[0] = ordered[0].model_copy(update={"changed_first": True})
    return tuple(ordered)
