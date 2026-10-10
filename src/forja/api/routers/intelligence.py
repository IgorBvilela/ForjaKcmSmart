"""Inteligência por equipamento: alertas, aviso antecipado e casos anteriores. Só leitura.

Três vozes separadas, sempre rotuladas:
- ALARME DO KCM: o que o controlador informa (alarm_active / alarm_code). Reconhecer ou resetar
  é feito no KCM; a Forja só mostra.
- EVENTO DETECTADO PELA FORJA: regra determinística (config/rules).
- AVISO ANTECIPADO DA FORJA: tendência e desvio do padrão (config/early_warning). Não é previsão.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter
from fastapi import Path as PathParam

from forja.api.deps import ContainerDep, jsonable, require_profile
from forja.api.errors import ApiError
from forja.api.routers.diagnostics import alarm_key_for
from forja.api.routers.equipments import build_live_view
from forja.api.routers.events import event_view
from forja.domain import (
    UNKNOWN,
    ConfigError,
    EquipmentProfile,
    Event,
    KnowledgeState,
    Quality,
    get_tag,
)
from forja.events.ew_engine import RuleRuntime
from forja.events.ew_rules import SIGNAL_KIND_PT, EarlyWarningRule
from forja.events.recurrence import recurrence
from forja.events.window_analysis import fmt_duration_pt

logger = logging.getLogger("forja.api")

router = APIRouter(prefix="/api/v1", tags=["inteligencia"])

EquipmentId = Annotated[str, PathParam(min_length=1, max_length=64)]

EW_DISCLAIMER_PT = (
    "Aviso antecipado é detecção de tendência e de desvio em relação ao padrão do próprio "
    "equipamento, com limites configurados e evidenciados. Não é previsão de falha e não é "
    "alarme do KCM."
)
KCM_ALARM_NOTE_PT = (
    "Alarme do KCM: reconhecer ou resetar é feito no próprio controlador. A Forja só mostra o que "
    "o KCM informa e nunca envia comando."
)
FORJA_EVENTS_NOTE_PT = (
    "Eventos detectados pela Forja por regras determinísticas. Reconhecer aqui registra quem viu "
    "e quando, com auditoria; não altera o KCM."
)
CASES_NOTE_PT = (
    "Casos de campo registram o que foi observado e o que foi feito. A causa só aparece como "
    "confirmada quando há evidência que feche a cadeia."
)
SPARK_POINTS = 60
STATE_PT: dict[str, str] = {
    "ACTIVE": "Merece atenção",
    "CONFIRMING": "Confirmando",
    "NORMAL": "Dentro do padrão configurado",
    "INSUFFICIENT": "Dados insuficientes",
    "PENDING": "Aguardando a primeira avaliação",
}
VERDICT_PT: dict[str, str] = {
    "MET": "condição presente",
    "NOT_MET": "condição ausente",
    "INSUFFICIENT": "sem dados suficientes",
}
KNOWLEDGE_PT: dict[str, str] = {
    KnowledgeState.FACT: "Fato",
    KnowledgeState.OFFICIAL_DOC: "Documento oficial",
    KnowledgeState.MACHINE_DOC: "Documento da máquina",
    KnowledgeState.FIELD_CONFIRMED: "Confirmado em campo",
    KnowledgeState.FIELD_OBSERVED: "Observado em campo",
    KnowledgeState.FORJA_RULE: "Regra Forja",
    KnowledgeState.TECHNICAL_OPINION: "Opinião técnica",
    KnowledgeState.HYPOTHESIS: "Hipótese",
    KnowledgeState.UNKNOWN: "Desconhecido",
}
USABLE = (Quality.GOOD, Quality.SIMULATED, Quality.UNCERTAIN)


# ---------------------------------------------------------------------------------- alertas


def kcm_alarm_view(container: Any, profile: EquipmentProfile) -> dict[str, Any]:
    """Estado de alarme informado pelo KCM, com a qualidade da leitura."""
    live = build_live_view(container, profile)
    tags = {t["tag"]: t for t in live["tags"]}
    active, code = tags.get("alarm_active"), tags.get("alarm_code")
    base: dict[str, Any] = {"source_pt": "informado pelo KCM", "note_pt": KCM_ALARM_NOTE_PT}
    if active is None and code is None:
        return {
            **base,
            "state": "NOT_MAPPED",
            "state_pt": "O mapping deste equipamento não traz o estado de alarme do KCM.",
        }
    readings = [t for t in (active, code) if t is not None]
    if any(t["quality"] not in {q.value for q in USABLE} for t in readings):
        worst_reading = next(t for t in readings if t["quality"] not in {q.value for q in USABLE})
        return {
            **base,
            "state": "UNKNOWN",
            "state_pt": "Estado do alarme do KCM desconhecido: sem leitura atual.",
            "quality": worst_reading["quality"],
            "quality_pt": worst_reading.get("quality_pt"),
        }
    code_value = code["value"] if code is not None else None
    is_active = (active is not None and active["value"] == 1) or (
        code_value is not None and code_value != 0
    )
    quality = readings[0]["quality"]
    if not is_active:
        return {
            **base,
            "state": "NONE",
            "state_pt": "Nenhum alarme ativo informado pelo KCM.",
            "quality": quality,
        }
    if code_value in (None, 0):
        return {
            **base,
            "state": "ACTIVE",
            "state_pt": "Alarme ativo informado pelo KCM (código não informado no mapping).",
            "code": None,
            "quality": quality,
        }
    code_text = str(int(code_value)) if float(code_value).is_integer() else str(code_value)
    lookup = container.store.alarms.lookup(alarm_key_for(profile, code_text))
    return {
        **base,
        "state": "ACTIVE",
        "state_pt": f"Alarme ativo no KCM: {lookup.title_pt}",
        "code": code_text,
        "title_pt": lookup.title_pt,
        "qualifier_pt": lookup.qualifier_pt,
        "catalogued": lookup.definition is not None,
        "since_utc": code["ts_utc"] if code is not None else None,
        "quality": quality,
    }


@router.get("/equipments/{equipment_id}/alerts")
async def alerts(equipment_id: EquipmentId, container: ContainerDep) -> dict[str, Any]:
    """Condições abertas, separadas por voz: alarme do KCM, eventos e avisos da Forja."""
    profile = require_profile(container, equipment_id)
    opened: list[Event] = await container.events_repo.list(
        equipment_id=profile.id, open_only=True, limit=500
    )
    opened.sort(key=lambda e: e.start_utc, reverse=True)
    forja = [event_view(e, include_samples=False) for e in opened if e.origin == "RULE"]
    warnings = [event_view(e, include_samples=False) for e in opened if e.origin == "EARLY_WARNING"]
    kcm = kcm_alarm_view(container, profile)
    return {
        "equipment_id": profile.id,
        "name": profile.name,
        "data_source": "SIMULATED" if profile.is_simulated else "EQUIPMENT",
        "kcm_alarm": kcm,
        "forja_events": forja,
        "early_warnings": warnings,
        "counts": {
            "kcm_alarm": 1 if kcm["state"] == "ACTIVE" else 0,
            "forja_events": len(forja),
            "forja_events_unacknowledged": sum(1 for e in forja if e["status"] == "OPEN"),
            "early_warnings": len(warnings),
        },
        "notes_pt": {
            "kcm": KCM_ALARM_NOTE_PT,
            "forja": FORJA_EVENTS_NOTE_PT,
            "early_warning": EW_DISCLAIMER_PT,
        },
        "generated_at_utc": jsonable(container.clock.now_utc()),
    }


# -------------------------------------------------------------------------- aviso antecipado


def _spark(cells: tuple[float | None, ...]) -> list[float | None]:
    """Até SPARK_POINTS pontos: média dos pedaços com leitura; pedaço vazio fica vazio."""
    if len(cells) <= SPARK_POINTS:
        return list(cells)
    size = len(cells) / SPARK_POINTS
    out: list[float | None] = []
    for i in range(SPARK_POINTS):
        chunk = [c for c in cells[int(i * size) : int((i + 1) * size)] if c is not None]
        out.append(sum(chunk) / len(chunk) if chunk else None)
    return out


def _rule_state(rt: RuleRuntime | None, evaluation: Any) -> str:
    if rt is not None and rt.open_event is not None:
        return "ACTIVE"
    if evaluation is None:
        return "PENDING"
    if evaluation.state == "MET":
        return "CONFIRMING"
    if evaluation.state == "INSUFFICIENT":
        return "INSUFFICIENT"
    return "NORMAL"


def rule_view(
    rule: EarlyWarningRule, rt: RuleRuntime | None, evaluation: Any, *, preview: bool
) -> dict[str, Any]:
    state = _rule_state(rt, evaluation)
    state_pt = STATE_PT[state]
    if state == "CONFIRMING":
        state_pt = (
            "Sinais atendidos nesta leitura; o aviso só abre depois de "
            f"{rule.persist_evaluations} avaliações seguidas"
            if preview or rt is None or rt.met_streak == 0
            else f"Confirmando: {rt.met_streak} de {rule.persist_evaluations} avaliações seguidas"
        )
    if state == "ACTIVE" and rule.severity.value == "INFO":
        state_pt = "Em observação"
    signals = []
    for i, signal in enumerate(rule.signals):
        outcome = evaluation.signals[i] if evaluation is not None else None
        meta = get_tag(signal.tag)
        cells = evaluation.cells.get(signal.tag, ()) if evaluation is not None else ()
        signals.append(
            {
                "tag": signal.tag,
                "label_pt": meta.label_pt,
                "unit": meta.unit,
                "decimals": meta.decimals,
                "kind": signal.kind,
                "kind_pt": SIGNAL_KIND_PT[signal.kind],
                "ref_tag": signal.ref_tag,
                "ref_label_pt": get_tag(signal.ref_tag).label_pt if signal.ref_tag else None,
                "verdict": outcome.verdict if outcome else None,
                "verdict_pt": VERDICT_PT[outcome.verdict] if outcome else "ainda não avaliado",
                "text_pt": outcome.text_pt if outcome else "",
                "limit_pt": outcome.limit_pt if outcome else "",
                "measured": outcome.measured if outcome else None,
                "fit": outcome.fit if outcome else None,
                "coverage": outcome.coverage if outcome else None,
                "before": outcome.before if outcome else None,
                "now": outcome.now if outcome else None,
                "spark": _spark(tuple(cells)),
            }
        )
    open_event = rt.open_event if rt is not None else None
    return {
        "id": rule.id,
        "version": rule.version,
        "title_pt": rule.title_pt,
        "description_pt": rule.description_pt,
        "severity": rule.severity.value,
        "severity_pt": rule.severity.label_pt,
        "state": state,
        "state_pt": state_pt,
        "preview": preview,
        "window_s": rule.window_s,
        "window_pt": fmt_duration_pt(rule.window_s),
        "recent_s": rule.recent_s,
        "recent_pt": fmt_duration_pt(rule.recent_s),
        "baseline": rule.baseline,
        "baseline_pt": (
            f"{fmt_duration_pt(rule.baseline_s or 0)} antes da janela"
            if rule.baseline == "before_window"
            else "início da janela"
        ),
        "evaluate_every_s": rule.evaluate_every_s,
        "evaluate_every_pt": fmt_duration_pt(rule.evaluate_every_s),
        "persist_evaluations": rule.persist_evaluations,
        "clear_evaluations": rule.clear_evaluations,
        "min_coverage": rule.min_coverage,
        "met_streak": rt.met_streak if rt is not None else 0,
        "last_evaluated_utc": jsonable(evaluation.ts_utc) if evaluation is not None else None,
        "quality": evaluation.quality.value if evaluation and evaluation.quality else None,
        "open_event_id": open_event.id if open_event is not None else None,
        "open_since_utc": jsonable(open_event.start_utc) if open_event is not None else None,
        "signals": signals,
        "threshold_basis": rule.threshold_basis,
        "threshold_note_pt": rule.threshold_note_pt,
        "sources": jsonable(rule.sources),
        "applications": rule.applications,
    }


@router.get("/equipments/{equipment_id}/early-warning")
async def early_warning(equipment_id: EquipmentId, container: ContainerDep) -> dict[str, Any]:
    """Regras de aviso antecipado do equipamento com a última avaliação de cada sinal."""
    profile = require_profile(container, equipment_id)
    engine = container.early_warning
    base = {
        "equipment_id": profile.id,
        "name": profile.name,
        "application": profile.application,
        "disclaimer_pt": EW_DISCLAIMER_PT,
        "generated_at_utc": jsonable(container.clock.now_utc()),
    }
    if engine is None:
        return {**base, "available": False, "rules": [], "active_count": 0, "recent": []}
    views = []
    for rule in engine.rules_for(profile.id):
        rt = engine.runtime(profile.id, rule.id)
        evaluation = rt.last
        preview = False
        if evaluation is None:
            try:
                evaluation = await engine.preview(container.historian, profile.id, rule)
                preview = True
            except Exception:  # historiador indisponível: a tela mostra "aguardando"
                logger.exception("prévia do aviso %s em %s falhou", rule.id, profile.id)
        views.append(rule_view(rule, rt, evaluation, preview=preview))
    events: list[Event] = await container.events_repo.list(equipment_id=profile.id, limit=500)
    recent = sorted(
        (e for e in events if e.origin == "EARLY_WARNING"),
        key=lambda e: e.start_utc,
        reverse=True,
    )[:20]
    return {
        **base,
        "available": True,
        "rules": views,
        "active_count": sum(1 for v in views if v["state"] == "ACTIVE"),
        "recent": [event_view(e, include_samples=False) for e in recent],
    }


# ---------------------------------------------------------------------------- casos anteriores


def case_view(case: Any) -> dict[str, Any]:
    data: dict[str, Any] = jsonable(case)
    data["evidence_pt"] = KNOWLEDGE_PT.get(case.evidence, str(case.evidence))
    confirmed = case.confirmed_cause != UNKNOWN
    data["cause_confirmed"] = confirmed
    data["cause_pt"] = case.confirmed_cause if confirmed else "Causa não confirmada"
    for m, raw in zip(data.get("measurements", []), case.measurements, strict=True):
        m["evidence_pt"] = KNOWLEDGE_PT.get(raw.evidence, str(raw.evidence))
    return data


@router.get("/equipments/{equipment_id}/cases")
async def cases(equipment_id: EquipmentId, container: ContainerDep) -> dict[str, Any]:
    """Casos de campo do equipamento, da mesma aplicação e ocorrências registradas pela Forja."""
    from forja.diagnostics import cases_for, load_cases

    profile = require_profile(container, equipment_id)
    try:
        all_cases = load_cases(container.paths.knowledge_dir / "cases")
    except ConfigError as exc:
        raise ApiError(
            500, "CASES_INVALID", "A base de casos de campo tem um arquivo inválido.", str(exc)
        ) from exc
    own, same_application = cases_for(all_cases, profile)
    events: list[Event] = await container.events_repo.list(equipment_id=profile.id, limit=2000)
    return {
        "equipment_id": profile.id,
        "name": profile.name,
        "application": profile.application,
        "field_cases": [case_view(c) for c in own],
        "same_application_cases": [case_view(c) for c in same_application],
        "recurrence": recurrence(events),
        "note_pt": CASES_NOTE_PT,
        "generated_at_utc": jsonable(container.clock.now_utc()),
    }


@router.get("/knowledge/cases")
async def knowledge_cases(container: ContainerDep) -> dict[str, Any]:
    """Biblioteca de casos de campo de todos os equipamentos (knowledge/cases)."""
    from forja.diagnostics import load_cases

    try:
        all_cases = load_cases(container.paths.knowledge_dir / "cases")
    except ConfigError as exc:
        raise ApiError(
            500, "CASES_INVALID", "A base de casos de campo tem um arquivo inválido.", str(exc)
        ) from exc
    return {
        "count": len(all_cases),
        "cases": [case_view(c) for c in all_cases],
        "note_pt": CASES_NOTE_PT,
    }


__all__ = ["EW_DISCLAIMER_PT", "KCM_ALARM_NOTE_PT", "kcm_alarm_view", "router", "rule_view"]
