"""Motor de regras deterministico: SampleBatch -> OPEN / UPDATE / CLOSE.

Eixo de tempo: ts_utc do lote (tempo do dado, que a aquisicao carimba pelo Clock).
O Clock injetado marca o instante em que a Forja processou o fechamento (Resolution).
Um evento aberto por dedupe_key = "<equipment_id>:<rule.id>". Nada aqui escreve no KCM.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import NAMESPACE_URL, uuid5

from forja.domain import (
    UNKNOWN,
    AlarmCatalog,
    AlarmKey,
    AlarmLookup,
    Clock,
    EquipmentProfile,
    Event,
    EventContext,
    EventStatus,
    EventTransition,
    Quality,
    Resolution,
    Sample,
    SampleBatch,
    StopByCatalog,
    TimelinePoint,
    WhatChangedItem,
    get_tag,
    worst,
)
from forja.events.conditions import EvalContext, evaluate
from forja.events.prewindow import SampleBuffer
from forja.events.rules import ANY_TAG, Rule
from forja.events.what_changed import compute_what_changed, delta_text_pt, fmt_number_pt

ALARM_CODE_TAG = "alarm_code"
ALARM_ACTIVE_TAG = "alarm_active"
STOP_BY_TAG = "stop_by"
MACHINE_STATE_TAG = "machine_state"
FORJA_ACTOR = "forja"


@dataclass
class _ConditionState:
    true_since: datetime | None = None


@dataclass
class _RuleState:
    conditions: list[_ConditionState]
    all_true_since: datetime | None = None
    open_event: Event | None = None
    clear_since: datetime | None = None
    cooldown_until: datetime | None = None


@dataclass
class _EquipmentState:
    buffer: SampleBuffer
    rules: dict[str, _RuleState] = field(default_factory=dict)


class _SafeFormat(dict[str, str]):
    """Placeholders ausentes no template viram UNKNOWN em vez de KeyError."""

    def __missing__(self, key: str) -> str:
        return UNKNOWN


def event_id_for(dedupe_key: str, start_utc: datetime) -> str:
    """Id deterministico: mesma anomalia, mesmo id (uuid5 em hex)."""
    return uuid5(NAMESPACE_URL, f"forja:event:{dedupe_key}:{start_utc.isoformat()}").hex


class RuleEngine:
    """Avalia regras por lote, com persistencia, dedupe, cooldown e fechamento por limpeza."""

    def __init__(
        self,
        rules: Sequence[Rule],
        alarms: AlarmCatalog,
        stop_by: StopByCatalog,
        clock: Clock,
        pre_window_s: int = 60,
        post_window_s: int = 30,
        buffer_s: int = 180,
        profiles: Mapping[str, EquipmentProfile] | None = None,
    ) -> None:
        if buffer_s < pre_window_s:
            raise ValueError("buffer_s precisa ser >= pre_window_s")
        self.rules: tuple[Rule, ...] = tuple(rules)
        self.alarms = alarms
        self.stop_by = stop_by
        self._clock = clock
        self.pre_window_s = pre_window_s
        self.post_window_s = post_window_s
        self.buffer_s = buffer_s
        self._profiles: dict[str, EquipmentProfile] = dict(profiles or {})
        self._state: dict[str, _EquipmentState] = {}

    # ------------------------------------------------------------------ publico

    def set_profile(self, profile: EquipmentProfile) -> None:
        """Registra o perfil para montar a chave composta de alarme deste equipamento."""
        self._profiles[profile.id] = profile

    def open_events(self, equipment_id: str) -> list[Event]:
        st = self._state.get(equipment_id)
        if st is None:
            return []
        return [rs.open_event for rs in st.rules.values() if rs.open_event is not None]

    def alarm_lookup(self, profile: EquipmentProfile | None, code: str) -> AlarmLookup:
        """Chave composta a partir do perfil. Sem perfil, tudo UNKNOWN exceto o codigo.

        Tenta o codigo como veio, com dois digitos ('06') e sem zeros a esquerda ('6').
        """
        key = self._alarm_key(profile, code)
        results = [
            self.alarms.lookup(key.model_copy(update={"code": variant}))
            for variant in _code_variants(code)
        ]
        for result in results:
            if result.definition is not None:
                return result
        for result in results:
            if result.candidates:
                return result
        return results[0]

    async def on_batch(self, batch: SampleBatch) -> list[EventTransition]:
        """Processa um lote. Deterministico: mesmo historico de lotes, mesmas transicoes."""
        st = self._equipment_state(batch.equipment_id)
        st.buffer.add(batch)
        now: dict[str, Sample] = {s.tag: s for s in batch.samples}
        transitions: list[EventTransition] = []
        for rule in self.rules:
            rs = st.rules[rule.id]
            transition = self._step_rule(rule, rs, st.buffer, batch, now)
            if transition is not None:
                transitions.append(transition)
        return transitions

    # ------------------------------------------------------------------ interno

    def _equipment_state(self, equipment_id: str) -> _EquipmentState:
        st = self._state.get(equipment_id)
        if st is None:
            st = _EquipmentState(buffer=SampleBuffer(self.buffer_s))
            for rule in self.rules:
                st.rules[rule.id] = _RuleState(
                    conditions=[_ConditionState() for _ in rule.conditions]
                )
            self._state[equipment_id] = st
        return st

    def _step_rule(
        self,
        rule: Rule,
        rs: _RuleState,
        buffer: SampleBuffer,
        batch: SampleBatch,
        now: Mapping[str, Sample],
    ) -> EventTransition | None:
        ts = batch.ts_utc
        ctx = EvalContext(
            ts=ts,
            now=now,
            batch_quality=batch.quality,
            history=buffer,
            allowed=frozenset(rule.allowed_qualities),
        )
        all_inst, satisfied = self._evaluate(rule, rs, ctx)
        if rs.open_event is None:
            if not satisfied or rs.all_true_since is None:
                return None
            if rs.cooldown_until is not None and ts < rs.cooldown_until:
                return None
            event = self._open(rule, rs.all_true_since, batch, now, buffer)
            rs.open_event = event
            rs.clear_since = None
            return EventTransition(kind="OPEN", event=event)
        if all_inst:
            rs.clear_since = None
            updated = self._update(rule, rs.open_event, batch, buffer)
            rs.open_event = updated
            return EventTransition(kind="UPDATE", event=updated)
        if rs.clear_since is None:
            rs.clear_since = ts
        if (ts - rs.clear_since).total_seconds() < rule.close_when_clear_for_s:
            return None
        closed = self._close(rule, rs.open_event, rs.clear_since, ts, buffer)
        rs.open_event = None
        rs.clear_since = None
        rs.all_true_since = None
        rs.cooldown_until = ts + timedelta(seconds=rule.cooldown_s)
        return EventTransition(kind="CLOSE", event=closed)

    def _evaluate(self, rule: Rule, rs: _RuleState, ctx: EvalContext) -> tuple[bool, bool]:
        """(todas instantaneamente verdadeiras, todas atendidas com persistencia)."""
        all_inst = True
        satisfied = True
        for cond, cs in zip(rule.conditions, rs.conditions, strict=True):
            inst = evaluate(cond, ctx)
            if not inst:
                cs.true_since = None
                all_inst = False
                satisfied = False
                continue
            if cs.true_since is None:
                cs.true_since = ctx.ts
            persist = 0 if cond.op == "persists_for" else (cond.persist_s or 0)
            if (ctx.ts - cs.true_since).total_seconds() < persist:
                satisfied = False
        if all_inst:
            if rs.all_true_since is None:
                rs.all_true_since = ctx.ts
        else:
            rs.all_true_since = None
        return all_inst, satisfied

    # ------------------------------------------------------------------ transicoes

    def _open(
        self,
        rule: Rule,
        start: datetime,
        batch: SampleBatch,
        now: Mapping[str, Sample],
        buffer: SampleBuffer,
    ) -> Event:
        detect_ts = batch.ts_utc
        tags = rule.tags
        pre_samples = buffer.pre_window(start, self.pre_window_s)
        during = buffer.between(start, detect_ts, include_end=True)
        history = (*pre_samples, *[s for s in during if s.ts_utc < detect_ts])
        # 'O que mudou' olha todo o buffer anterior a deteccao, nao so a pre-janela: a primeira
        # variavel pode ter saido do padrao antes de start - pre_window_s, e a linha de base
        # ('ANTES') precisa vir de quando tudo ainda estava estavel.
        analysis = buffer.between(
            detect_ts - timedelta(seconds=self.buffer_s), detect_ts, include_end=False
        )
        what_changed = compute_what_changed(analysis, now, tags)
        quality = self._event_quality(rule, batch, now)
        dedupe_key = f"{batch.equipment_id}:{rule.id}"
        profile = self._profiles.get(batch.equipment_id)
        timeline = self._timeline(
            rule, start, detect_ts, what_changed, (*pre_samples, *during), profile
        )
        context = EventContext(
            pre_window_s=self.pre_window_s,
            post_window_s=self.post_window_s,
            pre_samples=pre_samples,
            during_samples=during,
            what_changed=what_changed,
            timeline=timeline,
            gap_count=sum(1 for s in history if s.value is None),
            stale_count=sum(1 for s in history if s.quality == Quality.STALE),
            comm_error_count=sum(1 for s in history if s.quality == Quality.COMM_ERROR),
        )
        return Event(
            id=event_id_for(dedupe_key, start),
            equipment_id=batch.equipment_id,
            type=rule.internal_code,
            title_pt=rule.title_pt,
            start_utc=start,
            severity=rule.severity,
            summary_pt=self._summary(rule, what_changed, now),
            rule_id=rule.id,
            rule_version=rule.version,
            context=context,
            sources=tuple(rule.sources),
            quality=quality,
            status=EventStatus.OPEN,
            dedupe_key=dedupe_key,
            diagnosis_ref=rule.diagnosis_ref,
        )

    def _update(self, rule: Rule, event: Event, batch: SampleBatch, buffer: SampleBuffer) -> Event:
        during = buffer.between(event.start_utc, batch.ts_utc, include_end=True)
        quality = worst(
            [event.quality, self._event_quality(rule, batch, {s.tag: s for s in batch.samples})]
        )
        context = event.context.model_copy(update={"during_samples": during})
        return event.model_copy(update={"context": context, "quality": quality})

    def _close(
        self, rule: Rule, event: Event, cleared_at: datetime, ts: datetime, buffer: SampleBuffer
    ) -> Event:
        post_end = min(ts, cleared_at + timedelta(seconds=self.post_window_s))
        post = buffer.between(cleared_at, post_end, include_end=True)
        during = buffer.between(event.start_utc, cleared_at, include_end=False)
        timeline = (
            *event.context.timeline,
            TimelinePoint(
                ts_utc=cleared_at,
                text_pt=f"Condições da regra {rule.id} deixaram de ser atendidas",
                kind="forja",
            ),
            TimelinePoint(
                ts_utc=ts,
                text_pt=(
                    f"Forja encerrou o evento após {rule.close_when_clear_for_s} s sem a condição"
                ),
                kind="forja",
            ),
        )
        context = event.context.model_copy(
            update={"during_samples": during, "post_samples": post, "timeline": timeline}
        )
        resolution = Resolution(
            resolved_at_utc=self._clock.now_utc(),
            resolved_by=FORJA_ACTOR,
            resolution_class="UNKNOWN",
            note_pt="Encerrado automaticamente: a condição deixou de ser observada.",
        )
        return event.model_copy(
            update={
                "end_utc": cleared_at,
                "status": EventStatus.RESOLVED,
                "resolution": resolution,
                "context": context,
            }
        )

    # ------------------------------------------------------------------ apoio

    @staticmethod
    def _event_quality(rule: Rule, batch: SampleBatch, now: Mapping[str, Sample]) -> Quality:
        """Pior qualidade entre as amostras que a regra olhou neste lote."""
        qualities: list[Quality] = []
        for cond in rule.conditions:
            if cond.tag == ANY_TAG:
                qualities.append(batch.quality)
            elif cond.tag in now:
                qualities.append(now[cond.tag].quality)
            if cond.ref_tag is not None and cond.ref_tag in now:
                qualities.append(now[cond.ref_tag].quality)
        return worst(qualities) if qualities else batch.quality

    def _summary(
        self, rule: Rule, what_changed: Sequence[WhatChangedItem], now: Mapping[str, Sample]
    ) -> str:
        vars_: _SafeFormat = _SafeFormat()
        for item in what_changed:
            meta = get_tag(item.tag)
            vars_[f"{item.tag}_before"] = fmt_number_pt(item.before, meta.decimals)
            vars_[f"{item.tag}_now"] = fmt_number_pt(item.now, meta.decimals)
            vars_[f"{item.tag}_unit"] = meta.unit
            vars_[f"{item.tag}_delta_pt"] = delta_text_pt(
                item.delta, item.delta_kind, meta.unit, meta.decimals
            )
        stop = now.get(STOP_BY_TAG)
        raw = _raw_label(stop)
        entry = self.stop_by.classify(raw)
        vars_["stop_by_raw"] = raw or UNKNOWN
        vars_["stop_by_pt"] = entry.classification.label_pt
        first = next((i for i in what_changed if i.changed_first), None)
        vars_["changed_first_pt"] = first.label_pt if first is not None else UNKNOWN
        return rule.summary_template_pt.format_map(vars_)

    def _timeline(
        self,
        rule: Rule,
        start: datetime,
        detect_ts: datetime,
        what_changed: Sequence[WhatChangedItem],
        samples: Sequence[Sample],
        profile: EquipmentProfile | None,
    ) -> tuple[TimelinePoint, ...]:
        points: list[TimelinePoint] = []
        for item in what_changed:
            if item.ts_start_utc is None:
                continue
            prefix = "Primeiro a mudar: " if item.changed_first else ""
            meta = get_tag(item.tag)
            variation = delta_text_pt(item.delta, item.delta_kind, meta.unit, meta.decimals)
            text = f"{prefix}{item.label_pt} saiu do padrão ({variation} até a detecção)"
            points.append(
                TimelinePoint(ts_utc=item.ts_start_utc, text_pt=text, kind="forja", tag=item.tag)
            )
        points.extend(self._kcm_points(samples, profile, rule))
        points.append(
            TimelinePoint(
                ts_utc=start,
                text_pt=f"Condições da regra {rule.id} atendidas",
                kind="forja",
            )
        )
        points.append(
            TimelinePoint(
                ts_utc=detect_ts,
                text_pt=(
                    f"Forja abriu o evento '{rule.title_pt}' "
                    f"após {rule.persist_s} s de persistência"
                ),
                kind="forja",
            )
        )
        points.sort(key=lambda p: p.ts_utc)
        return tuple(points)

    def _kcm_points(
        self, samples: Sequence[Sample], profile: EquipmentProfile | None, rule: Rule
    ) -> list[TimelinePoint]:
        """O que o KCM informou (alarme ativo, STOP BY) dentro da janela analisada."""
        points: list[TimelinePoint] = []
        if not samples:
            return points
        alarm_ts = _first_active_alarm(samples)
        if alarm_ts is not None:
            code = _value_at(samples, ALARM_CODE_TAG, alarm_ts)
            if code is not None:
                lookup = self.alarm_lookup(profile, _fmt_code(code))
                points.append(
                    TimelinePoint(
                        ts_utc=alarm_ts,
                        text_pt=(
                            f"KCM informou alarme {lookup.code}: {lookup.title_pt} "
                            f"({lookup.qualifier_pt})"
                        ),
                        kind="kcm",
                        tag=ALARM_CODE_TAG,
                    )
                )
        if any(c.tag == MACHINE_STATE_TAG and c.op == "changed" for c in rule.conditions):
            stop_sample = _last_sample(samples, STOP_BY_TAG)
            raw = _raw_label(stop_sample)
            entry = self.stop_by.classify(raw)
            points.append(
                TimelinePoint(
                    ts_utc=stop_sample.ts_utc if stop_sample is not None else samples[-1].ts_utc,
                    text_pt=(
                        f"KCM informou STOP BY = {raw or UNKNOWN} "
                        f"({entry.classification.label_pt}; classificação {entry.evidence.value})"
                    ),
                    kind="kcm",
                    tag=STOP_BY_TAG,
                )
            )
        return points

    @staticmethod
    def _alarm_key(profile: EquipmentProfile | None, code: str) -> AlarmKey:
        if profile is None:
            return AlarmKey(code=code)
        return AlarmKey(
            manufacturer=profile.controller.manufacturer,
            controller=profile.controller.model,
            application=profile.application,
            software_version=profile.controller.software_version,
            code=code,
        )


def _code_variants(code: str) -> list[str]:
    text = code.strip()
    variants = [text]
    if text.isdigit():
        variants.extend([text.zfill(2), str(int(text))])
    return list(dict.fromkeys(variants))


def _fmt_code(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def _raw_label(sample: Sample | None) -> str | None:
    if sample is None or sample.value is None or not sample.quality.counts_for_rules:
        return None
    return _fmt_code(float(sample.value))


def _first_active_alarm(samples: Iterable[Sample]) -> datetime | None:
    for s in samples:
        if s.tag == ALARM_ACTIVE_TAG and s.value and s.quality.counts_for_rules:
            return s.ts_utc
    return None


def _value_at(samples: Iterable[Sample], tag: str, ts: datetime) -> float | None:
    """Primeiro valor utilizavel da tag com ts >= ts."""
    for s in samples:
        if s.tag == tag and s.ts_utc >= ts and s.value is not None and s.quality.counts_for_rules:
            return float(s.value)
    return None


def _last_sample(samples: Sequence[Sample], tag: str) -> Sample | None:
    for s in reversed(samples):
        if s.tag == tag:
            return s
    return None
