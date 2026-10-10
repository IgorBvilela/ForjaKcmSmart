"""Motor de aviso antecipado: avalia as regras EW-* por equipamento e abre/encerra avisos.

- Cada regra é avaliada a cada `evaluate_every_s`, lendo as séries do historiador.
- O aviso abre depois de `persist_evaluations` avaliações seguidas com todos os sinais atendidos
  e encerra depois de `clear_evaluations` avaliações seguidas sem a combinação.
- Dados insuficientes nunca abrem aviso e não encerram um aviso aberto (não há como confirmar
  que a condição passou).
- O aviso é um Event de origem EARLY_WARNING, com o mesmo dedupe e persistência dos eventos.
  Nunca é alarme do KCM e nunca é previsão. Nada aqui fala com o equipamento.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol

from forja.domain import (
    Clock,
    EquipmentProfile,
    Event,
    EventContext,
    EventStatus,
    EventTransition,
    Quality,
    Resolution,
    Series,
    TimelinePoint,
    WhatChangedItem,
    get_tag,
)
from forja.events.early_warning import (
    DEFAULT_CELLS,
    DEFAULT_MAX_HOLD_S,
    RuleEvaluation,
    SignalOutcome,
    evaluate_rule,
)
from forja.events.engine import FORJA_ACTOR, event_id_for
from forja.events.ew_rules import EarlyWarningRule
from forja.events.what_changed import compute_delta, delta_kind_for

logger = logging.getLogger(__name__)

UPDATE_EVERY_S = 300.0
"""Aviso aberto é regravado (resumo atualizado) no máximo a cada 5 min."""
POINTS_PER_CELL = 2


class SeriesSource(Protocol):
    async def range(
        self, equipment_id: str, tag: str, start: datetime, end: datetime, max_points: int = 2000
    ) -> Series: ...


@dataclass
class RuleRuntime:
    """Estado de uma regra num equipamento."""

    met_streak: int = 0
    clear_streak: int = 0
    first_met_utc: datetime | None = None
    open_event: Event | None = None
    last: RuleEvaluation | None = None
    next_due_utc: datetime | None = None
    last_written_utc: datetime | None = None


class EarlyWarningEngine:
    """Avalia regras de aviso antecipado. Estado em memória; avisos persistem como eventos."""

    def __init__(
        self,
        rules: Iterable[EarlyWarningRule],
        profiles: Mapping[str, EquipmentProfile],
        clock: Clock,
        *,
        cells: int = DEFAULT_CELLS,
        max_hold_s: float = DEFAULT_MAX_HOLD_S,
    ) -> None:
        self.rules: list[EarlyWarningRule] = list(rules)
        self._profiles = profiles
        self._clock = clock
        self._cells = cells
        self._max_hold_s = max_hold_s
        self._state: dict[tuple[str, str], RuleRuntime] = {}

    # ------------------------------------------------------------------ consulta

    def set_profiles(self, profiles: Mapping[str, EquipmentProfile]) -> None:
        self._profiles = profiles

    def rules_for(self, equipment_id: str) -> list[EarlyWarningRule]:
        profile = self._profiles.get(equipment_id)
        if profile is None:
            return []
        return [r for r in self.rules if r.applies_to(str(profile.application))]

    def runtime(self, equipment_id: str, rule_id: str) -> RuleRuntime:
        return self._state.setdefault((equipment_id, rule_id), RuleRuntime())

    def open_warnings(self, equipment_id: str) -> list[Event]:
        return [
            st.open_event
            for (eq, _), st in self._state.items()
            if eq == equipment_id and st.open_event is not None
        ]

    # ------------------------------------------------------------------ avaliação

    async def evaluate(
        self, source: SeriesSource, equipment_id: str, *, force: bool = False
    ) -> list[EventTransition]:
        """Avalia as regras vencidas (ou todas, com force) e devolve as transições."""
        now = self._clock.now_utc()
        transitions: list[EventTransition] = []
        for rule in self.rules_for(equipment_id):
            st = self.runtime(equipment_id, rule.id)
            if not force and st.next_due_utc is not None and now < st.next_due_utc:
                continue
            st.next_due_utc = now + timedelta(seconds=rule.evaluate_every_s)
            series = await self._read(source, equipment_id, rule, now)
            evaluation = evaluate_rule(
                rule, equipment_id, series, now, cells=self._cells, max_hold_s=self._max_hold_s
            )
            st.last = evaluation
            transition = self._step(rule, st, evaluation)
            if transition is not None:
                transitions.append(transition)
        return transitions

    async def preview(
        self, source: SeriesSource, equipment_id: str, rule: EarlyWarningRule
    ) -> RuleEvaluation:
        """Avaliação avulsa, sem mexer no estado (persistência, aviso aberto)."""
        now = self._clock.now_utc()
        series = await self._read(source, equipment_id, rule, now)
        return evaluate_rule(
            rule, equipment_id, series, now, cells=self._cells, max_hold_s=self._max_hold_s
        )

    async def _read(
        self, source: SeriesSource, equipment_id: str, rule: EarlyWarningRule, now: datetime
    ) -> dict[str, Series]:
        start = now - timedelta(seconds=rule.lookback_s)
        budget = self._cells * POINTS_PER_CELL
        return {
            tag: await source.range(equipment_id, tag, start, now, max_points=budget)
            for tag in rule.tags
        }

    def _step(
        self, rule: EarlyWarningRule, st: RuleRuntime, ev: RuleEvaluation
    ) -> EventTransition | None:
        if ev.state == "MET":
            st.met_streak += 1
            st.clear_streak = 0
            if st.first_met_utc is None:
                st.first_met_utc = ev.ts_utc
            if st.open_event is None:
                if st.met_streak < rule.persist_evaluations:
                    return None
                st.open_event = self._open(rule, ev, st.first_met_utc)
                st.last_written_utc = ev.ts_utc
                return EventTransition(kind="OPEN", event=st.open_event)
            if st.last_written_utc is not None and (
                (ev.ts_utc - st.last_written_utc).total_seconds() < UPDATE_EVERY_S
            ):
                return None
            st.open_event = self._refresh(st.open_event, ev)
            st.last_written_utc = ev.ts_utc
            return EventTransition(kind="UPDATE", event=st.open_event)
        st.met_streak = 0
        st.first_met_utc = None
        if st.open_event is None or ev.state == "INSUFFICIENT":
            return None
        st.clear_streak += 1
        if st.clear_streak < rule.clear_evaluations:
            return None
        closed = self._close(rule, st.open_event, ev)
        st.open_event = None
        st.clear_streak = 0
        st.last_written_utc = None
        return EventTransition(kind="CLOSE", event=closed)

    # ------------------------------------------------------------------ evento

    def _open(self, rule: EarlyWarningRule, ev: RuleEvaluation, first_met: datetime) -> Event:
        dedupe = f"{ev.equipment_id}:{rule.id}"
        timeline = (
            TimelinePoint(
                ts_utc=first_met,
                text_pt=(
                    f"Aviso antecipado '{rule.title_pt}': todos os sinais configurados atendidos"
                ),
                kind="forja",
            ),
            TimelinePoint(
                ts_utc=ev.ts_utc,
                text_pt=(
                    f"Forja abriu o aviso após {rule.persist_evaluations} avaliação(ões) seguidas"
                ),
                kind="forja",
            ),
        )
        return Event(
            id=event_id_for(dedupe, first_met),
            equipment_id=ev.equipment_id,
            type=rule.internal_code,
            title_pt=rule.title_pt,
            start_utc=first_met,
            severity=rule.severity,
            summary_pt=summary_pt(ev.signals),
            rule_id=rule.id,
            rule_version=rule.version,
            context=EventContext(
                pre_window_s=rule.window_s,
                post_window_s=0,
                what_changed=what_changed_items(ev.signals),
                timeline=timeline,
            ),
            sources=tuple(rule.sources),
            quality=ev.quality or Quality.UNCERTAIN,
            dedupe_key=dedupe,
            diagnosis_ref=rule.diagnosis_ref,
            origin="EARLY_WARNING",
        )

    @staticmethod
    def _refresh(event: Event, ev: RuleEvaluation) -> Event:
        context = event.context.model_copy(update={"what_changed": what_changed_items(ev.signals)})
        return event.model_copy(
            update={
                "summary_pt": summary_pt(ev.signals),
                "context": context,
                "quality": ev.quality or event.quality,
            }
        )

    def _close(self, rule: EarlyWarningRule, event: Event, ev: RuleEvaluation) -> Event:
        timeline = (
            *event.context.timeline,
            TimelinePoint(
                ts_utc=ev.ts_utc,
                text_pt=(
                    f"Forja encerrou o aviso após {rule.clear_evaluations} avaliação(ões) "
                    "seguidas fora da combinação configurada"
                ),
                kind="forja",
            ),
        )
        resolution = Resolution(
            resolved_at_utc=self._clock.now_utc(),
            resolved_by=FORJA_ACTOR,
            resolution_class="UNKNOWN",
            note_pt="Encerrado automaticamente: os sinais saíram da combinação configurada.",
        )
        return event.model_copy(
            update={
                "end_utc": ev.ts_utc,
                "status": EventStatus.RESOLVED,
                "resolution": resolution,
                "context": event.context.model_copy(update={"timeline": timeline}),
            }
        )


def summary_pt(outcomes: Sequence[SignalOutcome]) -> str:
    """Uma frase por sinal, na ordem da regra."""
    parts = [f"{get_tag(o.signal.tag).label_pt}: {o.text_pt}" for o in outcomes]
    return "; ".join(parts) + "." if parts else ""


def what_changed_items(outcomes: Sequence[SignalOutcome]) -> tuple[WhatChangedItem, ...]:
    """ANTES/AGORA dos sinais de variação (tendência, desvio, estabilidade)."""
    items: list[WhatChangedItem] = []
    for o in outcomes:
        if o.signal.kind not in ("trend", "deviation", "stable"):
            continue
        meta = get_tag(o.signal.tag)
        kind = delta_kind_for(o.signal.tag)
        items.append(
            WhatChangedItem(
                tag=o.signal.tag,
                label_pt=meta.label_pt,
                unit=meta.unit,
                before=o.before,
                now=o.now,
                delta=compute_delta(o.before, o.now, kind),
                delta_kind=kind,
                text_pt=o.text_pt,
            )
        )
    return tuple(items)


def evaluation_view(ev: RuleEvaluation | None) -> dict[str, Any] | None:
    """Avaliação serializável (API)."""
    if ev is None:
        return None
    return {
        "ts_utc": ev.ts_utc.isoformat(),
        "state": ev.state,
        "met_count": ev.met_count,
        "quality": ev.quality.value if ev.quality is not None else None,
        "signals": [
            {
                "tag": o.signal.tag,
                "kind": o.signal.kind,
                "verdict": o.verdict,
                "before": o.before,
                "now": o.now,
                "measured": o.measured,
                "fit": o.fit,
                "coverage": o.coverage,
                "text_pt": o.text_pt,
                "limit_pt": o.limit_pt,
            }
            for o in ev.signals
        ],
    }


__all__ = [
    "EarlyWarningEngine",
    "RuleRuntime",
    "SeriesSource",
    "evaluation_view",
    "summary_pt",
    "what_changed_items",
]
