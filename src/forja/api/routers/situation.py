"""Tela Agora: a situação da planta numa resposta só, para o gerente e para a manutenção.

Junta, por dosador, o estado do cartão da Planta, as três vozes (alarme do KCM, evento da Forja,
aviso antecipado), desde quando, o que mudou primeiro e a primeira verificação do diagnóstico.

Regras: somente leitura; "sem dados" nunca conta como normal; o "desde quando" nunca é inventado
(sem base conhecida, fica indeterminado); o aviso antecipado usa a última avaliação guardada, sem
recalcular o historiador.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter

from forja.api.deps import ContainerDep, data_source_for, data_source_label_pt, jsonable
from forja.api.routers.events import STATUS_PT
from forja.api.routers.intelligence import kcm_alarm_view, rule_state
from forja.api.routers.plant import (
    BLOCKED_ANOMALY_PT,
    STATE_ATTENTION_PT,
    STATE_BLOCKED_PT,
    STATE_CRITICAL_PT,
    STATE_NO_COMM_PT,
    STATE_PAUSED_PT,
    STATE_STOPPED_PT,
    STATE_UNKNOWN_PT,
    build_plant_card,
)
from forja.domain import Diagnosis, EquipmentProfile, Event, Quality, Sample, Severity
from forja.events.pre_event import pre_event_summary
from forja.events.recurrence import ORIGIN_PT

router = APIRouter(prefix="/api/v1", tags=["agora"])

GROUP_PROBLEM = "problem"
GROUP_NO_DATA = "no_data"
GROUP_STOPPED = "stopped"
GROUP_NORMAL = "normal"
GROUP_ORDER = {GROUP_PROBLEM: 0, GROUP_NO_DATA: 1, GROUP_STOPPED: 2, GROUP_NORMAL: 3}
SEVERITY_RANK = {Severity.CRITICAL: 0, Severity.ATTENTION: 1, Severity.INFO: 2}

NO_DATA_STATES = frozenset({STATE_NO_COMM_PT, STATE_PAUSED_PT, STATE_BLOCKED_PT, STATE_UNKNOWN_PT})
PAUSED_REASON_PT = "Coleta pausada (KCM › Comunicação)."
ALL_NORMAL_PT = "Tudo dentro do normal"
NO_EQUIPMENT_PT = "Nenhum dosador configurado"

SINCE_EVENT = "EVENT"
SINCE_LAST_OK = "LAST_OK"
SINCE_HISTORIAN = "HISTORIAN"
SINCE_BEFORE_WINDOW = "BEFORE_WINDOW"
SINCE_UNDETERMINED = "UNDETERMINED"
SINCE_PT = {
    SINCE_BEFORE_WINDOW: "há mais de 24 h",
    SINCE_UNDETERMINED: "início não determinado",
}

KCM_ALARM_TAGS = ("alarm_active", "alarm_code")
ALARM_LOOKBACK_S = 24 * 3600
"""Até onde a tela Agora procura, no historiador, o início do alarme ativo do KCM."""
ALARM_CHUNK_S = 3600
"""A busca anda para trás em blocos deste tamanho e para no primeiro trecho conclusivo."""
GAP_FACTOR = 3
"""Sem amostra por mais que GAP_FACTOR vezes a amostra forçada, o trecho conta como buraco."""
USABLE = frozenset({Quality.GOOD, Quality.SIMULATED, Quality.UNCERTAIN})
_ACTIVE = "ACTIVE"
_INACTIVE = "INACTIVE"
_UNKNOWN = "UNKNOWN"
_CONTINUE = "CONTINUE"


# ------------------------------------------------------------------------------- funções puras


def classify_group(state_pt: str, kcm_alarm_active: bool) -> str:
    """Grupo da tela Agora. Sem dados vence o alarme: sem leitura, não há alarme confirmado."""
    if state_pt in (STATE_CRITICAL_PT, STATE_ATTENTION_PT):
        return GROUP_PROBLEM
    if state_pt in NO_DATA_STATES:
        return GROUP_NO_DATA
    if kcm_alarm_active:
        return GROUP_PROBLEM
    if state_pt == STATE_STOPPED_PT:
        return GROUP_STOPPED
    return GROUP_NORMAL


def focus_event(open_events: list[Event]) -> Event | None:
    """Evento em destaque: o mais grave; no empate, a regra e depois o mais antigo."""
    anomalies = [e for e in open_events if e.severity != Severity.INFO]
    if not anomalies:
        return None
    return min(
        anomalies,
        key=lambda e: (SEVERITY_RANK[e.severity], e.origin != "RULE", e.start_utc),
    )


def summarize(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Frase do topo e contagens. "Tudo dentro do normal" só com todos com dado e bem."""
    total = len(entries)
    groups = Counter(e["group"] for e in entries)
    problems = groups[GROUP_PROBLEM]
    no_data = groups[GROUP_NO_DATA]
    critical = sum(1 for e in entries if e["severity"] == Severity.CRITICAL.value)
    noun = "dosador" if total == 1 else "dosadores"
    if total == 0:
        headline, tone = NO_EQUIPMENT_PT, "info"
    elif problems:
        headline = f"{problems} de {total} {noun} em atenção"
        tone = "crit" if critical else "warn"
    elif no_data:
        headline, tone = f"{no_data} de {total} {noun} sem dados", "info"
    else:
        headline, tone = ALL_NORMAL_PT, "ok"
    return {
        "total": total,
        "attention": problems,
        "critical": critical,
        "no_data": no_data,
        "stopped": groups[GROUP_STOPPED],
        "normal": groups[GROUP_NORMAL],
        "headline_pt": headline,
        "tone": tone,
    }


def order_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Grupo, gravidade, o que está assim há mais tempo e, por fim, a ordem da configuração."""
    severity_rank = {s.value: rank for s, rank in SEVERITY_RANK.items()}

    def key(item: tuple[int, dict[str, Any]]) -> tuple[int, int, str, int]:
        index, entry = item
        return (
            GROUP_ORDER[entry["group"]],
            severity_rank.get(entry["severity"], len(severity_rank)),
            entry["since_utc"] or "~",
            index,
        )

    return [entry for _, entry in sorted(enumerate(entries), key=key)]


def alarm_state(samples: Sequence[Sample]) -> str:
    """Estado do alarme num instante, com a mesma regra da leitura atual do KCM."""
    unknown = False
    for s in samples:
        if s.value is None or s.quality not in USABLE:
            unknown = True
            continue
        if (s.tag == "alarm_active" and s.value == 1) or (s.tag == "alarm_code" and s.value != 0):
            return _ACTIVE
    return _UNKNOWN if unknown else _INACTIVE


def alarm_run_start(samples: Sequence[Sample], max_gap_s: float) -> tuple[datetime | None, str]:
    """Início do episódio ativo mais recente nas amostras dadas.

    HISTORIAN: achou a passagem de inativo para ativo. UNDETERMINED: o último estado não é ativo,
    ou há leitura sem qualidade ou buraco no caminho. CONTINUE: tudo o que veio está ativo e é
    preciso olhar mais para trás.
    """
    by_ts: dict[datetime, list[Sample]] = {}
    for s in samples:
        by_ts.setdefault(s.ts_utc, []).append(s)
    states = [(ts, alarm_state(group)) for ts, group in sorted(by_ts.items())]
    if not states:
        return None, _CONTINUE
    if states[-1][1] != _ACTIVE:
        return None, SINCE_UNDETERMINED
    start = states[-1][0]
    for ts, state in reversed(states[:-1]):
        if (start - ts).total_seconds() > max_gap_s:
            return None, SINCE_UNDETERMINED
        if state == _ACTIVE:
            start = ts
            continue
        if state == _INACTIVE:
            return start, SINCE_HISTORIAN
        return None, SINCE_UNDETERMINED
    return start, _CONTINUE


async def kcm_alarm_since(
    historian: Any, equipment_id: str, now: datetime, max_gap_s: float
) -> tuple[datetime | None, str]:
    """Início do alarme ativo pelo historiador, nunca pela hora da última leitura."""
    limit = now - timedelta(seconds=ALARM_LOOKBACK_S)
    collected: list[Sample] = []
    end = now
    while end > limit:
        start = max(end - timedelta(seconds=ALARM_CHUNK_S), limit)
        chunk: list[Sample] = await historian.samples(equipment_id, KCM_ALARM_TAGS, start, end)
        if not collected:
            latest = max((s.ts_utc for s in chunk), default=None)
            if latest is None or (now - latest).total_seconds() > max_gap_s:
                return None, SINCE_UNDETERMINED
        collected = [*chunk, *collected]
        since, basis = alarm_run_start(collected, max_gap_s)
        if basis != _CONTINUE:
            return since, basis
        end = start
    earliest = min((s.ts_utc for s in collected), default=None)
    if earliest is None or (earliest - limit).total_seconds() > max_gap_s:
        return None, SINCE_UNDETERMINED
    return limit, SINCE_BEFORE_WINDOW


def voice_event(event: Event) -> dict[str, Any]:
    """Resumo de um evento aberto, com a origem rotulada."""
    return {
        "id": event.id,
        "title_pt": event.title_pt,
        "severity": event.severity.value,
        "severity_pt": event.severity.label_pt,
        "start_utc": jsonable(event.start_utc),
        "status": event.status.value,
        "status_pt": STATUS_PT[event.status],
        "acked_by": event.acked_by,
        "origin": event.origin,
        "origin_pt": ORIGIN_PT.get(event.origin, event.origin),
    }


def focus_view(event: Event, diagnosis: Diagnosis | None) -> dict[str, Any]:
    """O que mudou primeiro, a hipótese e a primeira verificação do evento em destaque."""
    pre = pre_event_summary(event)
    first = next((c for c in pre["changes"] if c.get("first")), None)
    changed_first = (
        None
        if first is None
        else {
            "tag": first["tag"],
            "label_pt": first["label_pt"],
            "lead_s": first["before_event_s"],
            "text_pt": first["text_pt"],
            "summary_pt": pre["narrative_pt"][0],
        }
    )
    next_check: dict[str, Any] | None = None
    hypothesis_pt: str | None = None
    if diagnosis is not None:
        checks = sorted(diagnosis.next_checks, key=lambda c: c.order)
        if checks:
            check = checks[0]
            next_check = {
                "text_pt": check.text_pt,
                "how_pt": check.how_pt,
                "evidence_level": check.evidence_level.value,
                "evidence_pt": check.evidence_level.label_pt,
            }
        if diagnosis.hypotheses:
            hypothesis_pt = diagnosis.hypotheses[0].text_pt
    return {
        "event_id": event.id,
        "title_pt": event.title_pt,
        "origin": event.origin,
        "origin_pt": ORIGIN_PT.get(event.origin, event.origin),
        "severity": event.severity.value,
        "start_utc": jsonable(event.start_utc),
        "status": event.status.value,
        "acked_by": event.acked_by,
        "changed_first": changed_first,
        "hypothesis_pt": hypothesis_pt,
        "next_check": next_check,
        "diagnosis_available": diagnosis is not None,
    }


# ------------------------------------------------------------------------------ montagem


async def kcm_voice(container: Any, profile: EquipmentProfile) -> dict[str, Any] | None:
    """Alarme ativo informado pelo KCM. O início vem do historiador, ou fica indeterminado."""
    view = kcm_alarm_view(container, profile)
    if view["state"] != "ACTIVE":
        return None
    max_gap_s = GAP_FACTOR * container.store.config.historian.forced_sample_every_s
    since, basis = await kcm_alarm_since(
        container.historian, profile.id, container.clock.now_utc(), max_gap_s
    )
    return {
        "state": view["state"],
        "state_pt": view["state_pt"],
        "code": view.get("code"),
        "title_pt": view.get("title_pt"),
        "catalogued": view.get("catalogued", False),
        "source_pt": view["source_pt"],
        "since_utc": jsonable(since),
        "since_basis": basis,
        "since_pt": SINCE_PT.get(basis),
    }


def early_warning_confirming(container: Any, equipment_id: str) -> int:
    """Regras confirmando, pela última avaliação guardada. Nunca chama a prévia do historiador."""
    engine = container.early_warning
    if engine is None:
        return 0
    count = 0
    for rule in engine.rules_for(equipment_id):
        rt = engine.runtime(equipment_id, rule.id)
        evaluation = rt.last if rt is not None else None
        if rule_state(rt, evaluation) == "CONFIRMING":
            count += 1
    return count


async def _diagnosis_for(container: Any, event: Event) -> Diagnosis | None:
    found = await container.diagnoses_repo.get_for_event(event.id)
    if found is None or isinstance(found, Diagnosis):
        return found
    return Diagnosis.model_validate(found)


async def situation_entry(container: Any, profile: EquipmentProfile) -> dict[str, Any]:
    """Um dosador na tela Agora."""
    card = await build_plant_card(container, profile)
    status = container.manager.status(profile.id)
    open_events: list[Event] = await container.events_repo.list(
        equipment_id=profile.id, open_only=True, limit=50
    )
    open_events.sort(key=lambda e: e.start_utc)
    kcm = await kcm_voice(container, profile)
    state_pt: str = card["state_pt"]
    group = classify_group(state_pt, kcm is not None)
    anomalies = [e for e in open_events if e.severity != Severity.INFO]
    highlighted = focus_event(open_events) if group == GROUP_PROBLEM else None

    since: Any = None
    since_basis: str | None = None
    if group == GROUP_PROBLEM and anomalies:
        since, since_basis = min(e.start_utc for e in anomalies), SINCE_EVENT
    elif group == GROUP_PROBLEM and kcm is not None:
        since, since_basis = kcm["since_utc"], kcm["since_basis"]
    elif group == GROUP_PROBLEM:
        since_basis = SINCE_UNDETERMINED
    elif state_pt == STATE_NO_COMM_PT:
        since = status.last_ok_utc
        since_basis = SINCE_LAST_OK if since is not None else SINCE_UNDETERMINED

    if state_pt == STATE_BLOCKED_PT:
        reason_pt: str | None = BLOCKED_ANOMALY_PT
    elif state_pt == STATE_PAUSED_PT:
        reason_pt = PAUSED_REASON_PT
    elif group == GROUP_NO_DATA:
        reason_pt = card["connection_pt"]
    else:
        reason_pt = None

    return {
        "id": profile.id,
        "name": profile.name,
        "state_pt": state_pt,
        "group": group,
        "severity": highlighted.severity.value if highlighted is not None else None,
        "since_utc": jsonable(since),
        "since_basis": since_basis,
        "reason_pt": reason_pt,
        "is_simulated": profile.is_simulated,
        "data_source": card["data_source"],
        "mass_flow": card["mass_flow"],
        "voices": {
            "kcm_alarm": kcm,
            "forja_events": [voice_event(e) for e in open_events if e.origin == "RULE"],
            "early_warnings": [voice_event(e) for e in open_events if e.origin == "EARLY_WARNING"],
            "early_warning_confirming": early_warning_confirming(container, profile.id),
        },
        "focus": (
            focus_view(highlighted, await _diagnosis_for(container, highlighted))
            if highlighted is not None
            else None
        ),
    }


@router.get("/situation")
async def get_situation(container: ContainerDep) -> dict[str, Any]:
    """Situação da planta para a tela Agora: um item por dosador, do mais grave ao normal."""
    profiles = list(container.store.profiles.values())
    entries = [await situation_entry(container, p) for p in profiles]
    data_source = data_source_for(profiles)
    return {
        "generated_at_utc": jsonable(container.clock.now_utc()),
        "data_source": data_source,
        "data_source_pt": data_source_label_pt(data_source),
        "summary": summarize(entries),
        "equipments": order_entries(entries),
    }
