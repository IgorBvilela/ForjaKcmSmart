"""Analise de uma janela do historico: o que mudou, quando comecou e quem mudou primeiro.

Usa o mesmo componente 'O QUE MUDOU' dos eventos (compute_what_changed): o padrao e o
comportamento do inicio da janela; cada variavel que saiu dele ganha o instante em que saiu.
A ordem desses instantes conta a historia ('o esforco subiu 18 s antes da vazao cair').
Nada e interpolado: leitura sem valor (COMM_ERROR, BAD) so entra nas contagens de qualidade.
O texto descreve ordem e simultaneidade; nunca afirma causa.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from forja.domain import Quality, Sample, WhatChangedItem, get_tag
from forja.events.plant_time import fmt_time_pt, resolve_zone
from forja.events.what_changed import USABLE, compute_what_changed

DEFAULT_TOGETHER_S = 30.0
"""Variaveis que sairam do padrao com ate esta diferenca de tempo 'mudaram juntas'."""

BASELINE_NOTE_PT = (
    "Análise da janela escolhida: o padrão é o comportamento do início da janela. "
    "Mostra o que mudou e em que ordem; não é causa."
)


class TagWindowStats(BaseModel):
    """Resumo de uma variavel na janela. min/max/avg so com leituras utilizaveis."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tag: str
    label_pt: str
    unit: str
    decimals: int
    points: int
    usable_points: int
    comm_error_points: int
    bad_points: int
    min: float | None
    max: float | None
    avg: float | None
    first: float | None
    last: float | None
    qualities: dict[str, int]


class WindowChange(BaseModel):
    """Uma variavel que saiu do padrao, com a distancia em segundos ate a primeira."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item: WhatChangedItem
    offset_s: float | None
    started_pt: str


class WindowAnalysis(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    changes: list[WindowChange]
    unchanged_tags: list[str]
    first_changed_tag: str | None
    together: list[list[str]]
    stats: dict[str, TagWindowStats]
    narrative_pt: list[str]
    caveats_pt: list[str]
    resolution_s: int


def fmt_duration_pt(seconds: float) -> str:
    """'18 s', '2 min 5 s', '1 h 03 min'."""
    s = max(0, round(seconds))
    if s < 60:
        return f"{s} s"
    m, rs = divmod(s, 60)
    if m < 60:
        return f"{m} min {rs} s" if rs else f"{m} min"
    h, rm = divmod(m, 60)
    return f"{h} h {rm:02d} min"


def _stats(
    tag: str, samples: Sequence[Sample], extremes: tuple[float | None, float | None] | None
) -> TagWindowStats:
    meta = get_tag(tag)
    usable = [float(s.value) for s in samples if s.quality in USABLE and s.value is not None]
    qualities: dict[str, int] = {}
    for s in samples:
        qualities[s.quality.value] = qualities.get(s.quality.value, 0) + 1
    low = min(usable) if usable else None
    high = max(usable) if usable else None
    if extremes is not None:
        low = extremes[0] if extremes[0] is not None else low
        high = extremes[1] if extremes[1] is not None else high
    return TagWindowStats(
        tag=tag,
        label_pt=meta.label_pt,
        unit=meta.unit,
        decimals=meta.decimals,
        points=len(samples),
        usable_points=len(usable),
        comm_error_points=sum(1 for s in samples if s.quality is Quality.COMM_ERROR),
        bad_points=sum(1 for s in samples if s.quality is Quality.BAD),
        min=low,
        max=high,
        avg=(sum(usable) / len(usable)) if usable else None,
        first=usable[0] if usable else None,
        last=usable[-1] if usable else None,
        qualities=qualities,
    )


def _groups(changes: Sequence[WindowChange], together_s: float) -> list[list[str]]:
    """Agrupa por proximidade do instante de saida; so devolve grupos com 2 ou mais."""
    groups: list[list[str]] = []
    current: list[str] = []
    start: datetime | None = None
    for change in changes:
        ts = change.item.ts_start_utc
        if ts is None:
            continue
        if start is not None and (ts - start).total_seconds() <= together_s:
            current.append(change.item.tag)
            continue
        if len(current) > 1:
            groups.append(current)
        current, start = [change.item.tag], ts
    if len(current) > 1:
        groups.append(current)
    return groups


def _caveats(all_samples: Sequence[Sample], resolution_s: int) -> list[str]:
    out = [BASELINE_NOTE_PT]
    if resolution_s > 1:
        out.append(
            f"Horários com precisão de {fmt_duration_pt(resolution_s)}: a janela foi "
            "resumida em intervalos para caber no gráfico."
        )
    present = {s.quality for s in all_samples}
    comm = sum(1 for s in all_samples if s.quality is Quality.COMM_ERROR)
    if comm:
        out.append(
            f"Houve {comm} trecho(s) sem leitura gravada nesta janela (sem comunicação com o "
            "equipamento ou Forja Edge sem coletar). Eles aparecem como buraco no gráfico e "
            "nada foi interpolado."
        )
    if Quality.BAD in present:
        out.append("Leituras fora da faixa válida foram descartadas (qualidade Inválido).")
    if Quality.UNCERTAIN in present:
        out.append(
            "Parte dos valores vem de mapping ainda não validado contra a tela do KCM "
            "(qualidade Não validado)."
        )
    if Quality.SIMULATED in present:
        out.append("Dados simulados: nenhum valor representa um KCM real.")
    return out


def _narrative(
    changes: Sequence[WindowChange], together: Sequence[Sequence[str]], together_s: float
) -> list[str]:
    if not changes:
        return [
            "Nenhuma variável saiu do padrão nesta janela. O padrão é o comportamento do "
            "início da janela."
        ]
    lines: list[str] = []
    for i, change in enumerate(changes):
        item = change.item
        if i == 0:
            lines.append(
                f"{item.label_pt} foi a primeira a sair do padrão, às {change.started_pt} "
                f"({item.text_pt})."
            )
        elif change.offset_s is not None and change.offset_s >= 1:
            lines.append(
                f"{item.label_pt} começou a mudar às {change.started_pt}, "
                f"{fmt_duration_pt(change.offset_s)} depois ({item.text_pt})."
            )
        else:
            lines.append(
                f"{item.label_pt} começou a mudar no mesmo instante, às {change.started_pt} "
                f"({item.text_pt})."
            )
    labels = {c.item.tag: c.item.label_pt for c in changes}
    for group in together:
        names = ", ".join(labels[t] for t in group)
        lines.append(f"Mudaram juntas (diferença de até {fmt_duration_pt(together_s)}): {names}.")
    return lines


def analyze_window(
    samples_by_tag: Mapping[str, Sequence[Sample]],
    tags: Sequence[str],
    *,
    timezone: str,
    resolution_s: int,
    together_s: float = DEFAULT_TOGETHER_S,
    extremes: Mapping[str, tuple[float | None, float | None]] | None = None,
) -> WindowAnalysis:
    """Analisa as amostras da janela (ja em ordem de tempo por tag).

    `extremes` permite informar min/max reais de cada tag quando as amostras sao medias de
    intervalos (serie resumida): o pico dentro do intervalo nao some do resumo.
    """
    zone = resolve_zone(timezone)
    wanted = [t for t in dict.fromkeys(tags) if t in samples_by_tag]
    ordered = {t: sorted(samples_by_tag[t], key=lambda s: s.ts_utc) for t in wanted}
    all_samples = [s for t in wanted for s in ordered[t]]
    now: dict[str, Sample] = {}
    for tag in wanted:
        usable = [s for s in ordered[tag] if s.quality in USABLE and s.value is not None]
        if usable:
            now[tag] = usable[-1]
    items = compute_what_changed(all_samples, now, wanted, before_mode="baseline")
    reference = max((s.ts_utc for s in all_samples), default=None)
    changed = [i for i in items if i.ts_start_utc is not None]
    first_ts = changed[0].ts_start_utc if changed else None
    changes = [
        WindowChange(
            item=i,
            offset_s=(i.ts_start_utc - first_ts).total_seconds()
            if i.ts_start_utc is not None and first_ts is not None
            else None,
            started_pt=fmt_time_pt(i.ts_start_utc, zone, reference)
            if i.ts_start_utc is not None
            else "",
        )
        for i in changed
    ]
    changed_tags = {c.item.tag for c in changes}
    together = _groups(changes, together_s)
    return WindowAnalysis(
        changes=changes,
        unchanged_tags=[t for t in wanted if t not in changed_tags],
        first_changed_tag=changes[0].item.tag if changes else None,
        together=together,
        stats={t: _stats(t, ordered[t], (extremes or {}).get(t)) for t in wanted},
        narrative_pt=_narrative(changes, together, together_s),
        caveats_pt=_caveats(all_samples, resolution_s),
        resolution_s=resolution_s,
    )


__all__ = [
    "DEFAULT_TOGETHER_S",
    "TagWindowStats",
    "WindowAnalysis",
    "WindowChange",
    "analyze_window",
    "fmt_duration_pt",
]
