"""Motor de eventos determinístico.

FLUXO
-----
    ciclo de aquisição -> EventEngine.on_cycle() -> avalia todas as regras
    -> abre / mantém / fecha eventos -> grava no historian

ABERTURA E FECHAMENTO
---------------------
Uma condição precisa estar ativa por `rule.for_cycles` ciclos consecutivos
para ABRIR o evento, e ausente por `rule.clear_cycles` ciclos para FECHAR.
Isso evita que ruído de um ciclo vire evento, sem depender de médias móveis
ou de qualquer coisa não reproduzível.

CAPTURA DO CONTEXTO ANTERIOR
----------------------------
O motor guarda os últimos snapshots num anel de tamanho fixo. Quando um
evento abre, ele leva junto:

    context["before"]  -> como a máquina estava ANTES do distúrbio
    context["at_open"] -> o instante do reconhecimento
    context["trend"]   -> série curta das tags relevantes no entorno

Sem isso, o diagnóstico chega depois do fato e só vê a máquina já degradada.
O "antes" é o que permite dizer o que mudou.

O motor NÃO conclui causa. Ele reconhece sintoma, guarda evidência e entrega
para a biblioteca de diagnóstico.
"""
from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from forja.acquisition.scheduler import CycleResult
from forja.domain.equipment import EquipmentCard
from forja.domain.models import Sample, TAG_CATALOG, utcnow
from forja.historian.repository import HistorianRepository

from .models import Event, EventStatus, EventType, Evidence, Severity
from .rules import Rule, RuleContext, RuleHit, default_rules

log = logging.getLogger("forja.events")

# tags que entram na fotografia de contexto de qualquer evento
CONTEXT_TAGS = ["machine_state", "setpoint", "mass_flow", "drive_command", "rpm", "belt_load",
                "net_weight", "alarm_code", "stop_by", "sft_list", "sft_status", "mdu_status",
                "int_channel_pct", "motor_load_pct", "control_mode", "vol_belt_load"]


@dataclass
class Snapshot:
    """Fotografia de um ciclo: o que cada tag valia, e se a leitura falhou."""
    ts: datetime
    values: dict[str, Sample]
    read_error_count: int = 0

    def plain(self, tags: Optional[list[str]] = None) -> dict[str, Any]:
        keys = tags or list(self.values)
        out: dict[str, Any] = {}
        for t in keys:
            s = self.values.get(t)
            if s is None:
                continue
            out[t] = {"value": s.value, "quality": s.quality.value,
                      "ts": s.ts.isoformat(),
                      "age_s": round(s.age_s, 2) if s.age_s else 0.0}
        return out


@dataclass
class _RuleState:
    """Estado de debounce de uma regra. Determinístico: só contadores."""
    active_cycles: int = 0
    clear_cycles: int = 0
    open_event: Optional[Event] = None
    open_event_id: Optional[int] = None
    last_hit: Optional[RuleHit] = None


@dataclass
class EngineStats:
    cycles: int = 0
    events_opened: int = 0
    events_closed: int = 0
    last_event_ts: Optional[datetime] = None


class EventEngine:
    def __init__(self, equipment: EquipmentCard, historian: HistorianRepository,
                 rules: Optional[list[Rule]] = None, history_size: int = 600,
                 context_before_s: float = 30.0,
                 on_event: Optional[Callable[[Event], None]] = None):
        self.equipment = equipment
        self.historian = historian
        self.rules = rules if rules is not None else default_rules()
        self.history: deque[Snapshot] = deque(maxlen=history_size)
        self.context_before_s = context_before_s
        self.on_event = on_event
        self.stats = EngineStats()
        self._state: dict[str, _RuleState] = {r.rule_id: _RuleState() for r in self.rules}
        self._latest: dict[str, Sample] = {}
        self._lock = threading.Lock()

    # -- entrada: um ciclo de aquisição terminou
    def on_cycle(self, cycle: CycleResult) -> list[Event]:
        with self._lock:
            for s in cycle.samples:
                self._latest[s.tag] = s
            snapshot = Snapshot(ts=cycle.ts, values=dict(self._latest),
                                read_error_count=len(cycle.read_errors))
            ctx = RuleContext(equipment=self.equipment, now=cycle.ts,
                              samples=snapshot.values, cycle=cycle, history=list(self.history))
            opened: list[Event] = []
            for rule in self.rules:
                ev = self._apply(rule, ctx, snapshot)
                if ev is not None:
                    opened.append(ev)
            self.history.append(snapshot)
            self.stats.cycles += 1
        for ev in opened:
            if self.on_event:
                try:
                    self.on_event(ev)
                except Exception:                      # um consumidor não derruba o motor
                    log.exception("on_event falhou para %s", ev.type.value)
        return opened

    # -- máquina de estados de uma regra
    def _apply(self, rule: Rule, ctx: RuleContext, snapshot: Snapshot) -> Optional[Event]:
        st = self._state[rule.rule_id]
        try:
            hit = rule.evaluate(ctx)
        except Exception:
            log.exception("regra %s falhou; ignorada neste ciclo", rule.rule_id)
            return None

        if hit.active:
            st.active_cycles += 1
            st.clear_cycles = 0
            st.last_hit = hit
            if st.open_event is None and st.active_cycles >= rule.for_cycles:
                return self._open(rule, ctx, hit, snapshot)
            return None

        st.active_cycles = 0
        if st.open_event is not None:
            st.clear_cycles += 1
            if st.clear_cycles >= rule.clear_cycles:
                self._close(rule, ctx.now)
        return None

    def _open(self, rule: Rule, ctx: RuleContext, hit: RuleHit, snapshot: Snapshot) -> Event:
        before = self._snapshot_before(ctx.now)
        context: dict[str, Any] = {
            "rule": {"id": rule.rule_id, "version": rule.version,
                     "description": rule.description, "params": rule.params,
                     "for_cycles": rule.for_cycles},
            "evidences": [e.model_dump(mode="json") for e in hit.evidences],
            "at_open": snapshot.plain(CONTEXT_TAGS),
            "before": {
                "ts": before.ts.isoformat() if before else None,
                "seconds_before": round((ctx.now - before.ts).total_seconds(), 2) if before else None,
                "values": before.plain(CONTEXT_TAGS) if before else {},
                "available": before is not None,
            },
            "changed": self._diff(before, snapshot),
            "trend": self._trend(hit, snapshot),
            "equipment": {"id": self.equipment.equipment_id,
                          "application": ctx.application.value,
                          "controller_model": ctx.controller_model,
                          "tag": self.equipment.tag},
            "data_origin": {
                "note": "origem do dado registrada em cada evidência (campo quality); "
                        "SIMULATED nunca é apresentado como leitura real",
            },
        }
        context.update(hit.extra)

        event = Event(equipment_id=self.equipment.equipment_id, type=rule.event_type,
                      severity=hit.severity or rule.severity, ts_start=ctx.now,
                      rule_id=rule.rule_id, rule_version=rule.version,
                      status=EventStatus.OPEN, summary=hit.summary, context=context)
        row = event.to_row()
        event.id = self.historian.write_event(**row)

        st = self._state[rule.rule_id]
        st.open_event = event
        st.open_event_id = event.id
        st.clear_cycles = 0
        self.stats.events_opened += 1
        self.stats.last_event_ts = ctx.now
        log.info("evento aberto: %s (%s) — %s", event.type.value, rule.rule_id, event.summary)
        return event

    def _close(self, rule: Rule, ts: datetime) -> None:
        st = self._state[rule.rule_id]
        event = st.open_event
        if event is None:
            return
        event.ts_end = ts
        event.status = EventStatus.CLOSED
        if event.id is not None:
            self.historian.close_event(event.id, ts)
        self.stats.events_closed += 1
        log.info("evento fechado: %s após %.1f s", event.type.value, event.duration_s or 0.0)
        st.open_event = None
        st.open_event_id = None
        st.clear_cycles = 0

    # -- contexto
    def _snapshot_before(self, now: datetime) -> Optional[Snapshot]:
        """O snapshot mais recente anterior a `context_before_s`.

        É o "antes do distúrbio": a máquina como estava, não como ficou.
        """
        cutoff = now - timedelta(seconds=self.context_before_s)
        chosen: Optional[Snapshot] = None
        for snap in self.history:
            if snap.ts <= cutoff:
                chosen = snap
            else:
                break
        if chosen is None and self.history:
            chosen = self.history[0]      # histórico curto: o mais antigo que existe
        return chosen

    @staticmethod
    def _diff(before: Optional[Snapshot], now: Snapshot) -> dict[str, Any]:
        """O que mudou entre o antes e o agora. Só o que mudou."""
        if before is None:
            return {}
        out: dict[str, Any] = {}
        for tag in CONTEXT_TAGS:
            b, a = before.values.get(tag), now.values.get(tag)
            if b is None or a is None or b.value == a.value:
                continue
            cat = TAG_CATALOG.get(tag)
            entry: dict[str, Any] = {"label": cat.display_name if cat else tag,
                                     "unit": cat.unit if cat else "",
                                     "before": b.value, "after": a.value}
            if b.is_numeric and a.is_numeric:
                delta = float(a.value) - float(b.value)
                entry["delta"] = round(delta, 4)
                if float(b.value) != 0:
                    entry["delta_pct"] = round(delta / abs(float(b.value)) * 100, 1)
            out[tag] = entry
        return out

    def _trend(self, hit: RuleHit, now: Snapshot, points: int = 12) -> dict[str, list]:
        """Série curta das tags citadas nas evidências, para ver a transição."""
        tags = [e.tag for e in hit.evidences if e.tag in TAG_CATALOG]
        if not tags:
            tags = ["mass_flow", "drive_command", "rpm"]
        snaps = list(self.history)[-points:] + [now]
        out: dict[str, list] = {}
        for tag in dict.fromkeys(tags):
            series = []
            for snap in snaps:
                s = snap.values.get(tag)
                if s is None:
                    continue
                series.append({"ts": s.ts.isoformat(), "value": s.value, "quality": s.quality.value})
            if series:
                out[tag] = series
        return out

    # -- consulta
    def open_events(self) -> list[Event]:
        with self._lock:
            return [st.open_event for st in self._state.values() if st.open_event is not None]

    def rule_table(self) -> list[dict]:
        return [{"rule_id": r.rule_id, "version": r.version, "event_type": r.event_type.value,
                 "severity": r.severity.value, "description": r.description,
                 "for_cycles": r.for_cycles, "clear_cycles": r.clear_cycles, "params": r.params}
                for r in self.rules]
