"""Montagem do diagnóstico de um evento.

Entrada: um evento gravado pelo motor (com contexto anterior capturado).
Saída: um diagnóstico com RESUMO, EVIDÊNCIAS, HIPÓTESES, VERIFICAÇÕES e FONTES.

CONTRATO
--------
Esta saída é o contrato oficial entre o diagnóstico e qualquer consumidor —
UI, relatório ou integração. `diagnosis_schema_version` identifica o formato.
Quem consome deve ler o JSON, nunca reparsear a saída de texto da CLI: o
texto é apresentação e pode mudar sem aviso; o JSON é contrato e muda com
versão.

Regra de compatibilidade da versão:
    1.x  campos podem ser ACRESCENTADOS; nenhum campo existente some ou
         muda de tipo ou de significado
    2.0  qualquer remoção, renomeação ou mudança de significado

NÍVEL DE EVIDÊNCIA É POR ITEM
-----------------------------
Cada hipótese, cada verificação e cada fonte carrega o SEU nível. Não existe
um nível único para o diagnóstico inteiro, porque a mesma resposta costuma
juntar uma hipótese apoiada em campo com outra que é só opinião técnica.
`evidence_summary` resume a distribuição, mas não substitui o nível de cada
item — e informa o elo mais fraco, porque um conjunto não vale mais do que o
seu pior item.

O diagnóstico é read-only em dois sentidos: não escreve no KCM e não escreve
no evento. É derivado e reproduzível a partir do evento gravado.

O que ele nunca faz:
- afirmar causa confirmada (só a intervenção em campo confirma);
- apresentar dado simulado como leitura real;
- generalizar um caso da base como regra.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Optional

from forja.domain.evidence import (EVIDENCE_LABEL, EvidenceLevel, describe, weakest)
from forja.events.models import EventType

from .cases import CaseRecord, cases_for_event
from .library import DiagnosticEntry, entry_for

# Versão do contrato. Ver a regra de compatibilidade acima.
DIAGNOSIS_SCHEMA_VERSION = "1.0"


def _evidence_block(context: dict[str, Any]) -> list[dict[str, Any]]:
    """Evidências que o motor registrou no instante do reconhecimento.

    `quality` aqui é a qualidade do DADO (GOOD, SIMULATED, STALE...), coisa
    diferente do nível de evidência de uma hipótese. Um número pode ser de
    leitura boa e ainda assim sustentar uma hipótese fraca.
    """
    out = []
    for e in context.get("evidences", []):
        out.append({"label": e.get("label") or e.get("tag"), "tag": e.get("tag"),
                    "value": e.get("value"), "unit": e.get("unit", ""),
                    "ts": e.get("ts"), "quality": e.get("quality", ""),
                    "note": e.get("note", "")})
    return out


def _changed_block(context: dict[str, Any]) -> list[dict[str, Any]]:
    """O que mudou entre o antes e o instante do evento."""
    changed = context.get("changed") or {}
    out = []
    for tag, d in changed.items():
        line = {"tag": tag, "label": d.get("label", tag), "unit": d.get("unit", ""),
                "before": d.get("before"), "after": d.get("after")}
        if "delta" in d:
            line["delta"] = d["delta"]
        if "delta_pct" in d:
            line["delta_pct"] = d["delta_pct"]
        out.append(line)
    return out


def _simulated(context: dict[str, Any]) -> bool:
    qualities = {e.get("quality") for e in context.get("evidences", [])}
    return "SIMULATED" in qualities


def _hypotheses_block(entry: DiagnosticEntry, context: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for h in entry.hypotheses:
        item = asdict(h)
        item.pop("doc_ref", None)              # substituído pelo bloco padrão
        item.pop("evidence_level", None)
        item["rank"] = h.rank.value
        item.update(h.evidence_block())        # evidence_level, label, rank, doc_reference
        out.append(item)

    alarm = context.get("alarm")
    if alarm:
        level = alarm.get("evidence_level") or EvidenceLevel.UNKNOWN.value
        try:
            lv = EvidenceLevel(level)
        except ValueError:
            lv = EvidenceLevel.UNKNOWN
        top = {
            "id": "H-ALARM-CATALOG",
            "name": f"O que o catálogo registra para o código {alarm.get('code')}",
            "statement": f"{alarm.get('name')} — {alarm.get('meaning')}",
            "rationale": f"entrada de chave composta {alarm.get('key')}",
            "discriminator": "ler o texto do alarme na tela da própria máquina e comparar",
            "rank": "verificar_primeiro",
            "source": alarm.get("source", "UNKNOWN"),
            "ranking_basis": "entrada de catálogo, com escopo declarado; não é conclusão",
            "scope": alarm.get("scope", ""),
            "reverse_warning": alarm.get("reverse_warning", ""),
        }
        top.update(describe(lv))
        if alarm.get("doc_reference"):
            top["doc_reference"] = alarm["doc_reference"]
        out.insert(0, top)
    return out


def _checks_block(entry: DiagnosticEntry) -> list[dict[str, Any]]:
    out = []
    for c in sorted(entry.checks, key=lambda c: c.order):
        item = asdict(c)
        item.pop("doc_ref", None)
        item.pop("evidence_level", None)
        item.update(c.evidence_block())
        out.append(item)
    return out


def _sources_block(entry: DiagnosticEntry, context: dict[str, Any],
                   related: list[CaseRecord]) -> list[dict[str, Any]]:
    """Tudo que sustenta este diagnóstico, junto e rastreável.

    Cada linha diz DE ONDE veio e QUE NÍVEL de evidência é. Uma fonte de
    fabricante e uma opinião técnica não valem o mesmo, e quem lê precisa
    conseguir separar as duas sem adivinhar.
    """
    out: list[dict[str, Any]] = []
    seen: set[tuple] = set()

    def add(kind: str, reference: str, detail: str = "",
            level: EvidenceLevel = EvidenceLevel.UNKNOWN, doc_ref=None) -> None:
        key = (kind, reference)
        if not reference or key in seen:
            return
        seen.add(key)
        row = {"kind": kind, "reference": reference, "detail": detail}
        row.update(describe(level, doc_ref))
        out.append(row)

    # 1. a regra que reconheceu o evento
    rule = context.get("rule", {})
    if rule:
        add("regra", f"{rule.get('id', '?')} v{rule.get('version', '?')}",
            rule.get("description", ""), EvidenceLevel.FORJA_RULE)

    # 2. o catálogo de alarmes, quando o controlador declarou um código
    alarm = context.get("alarm")
    if alarm:
        try:
            lv = EvidenceLevel(alarm.get("evidence_level", "UNKNOWN"))
        except ValueError:
            lv = EvidenceLevel.UNKNOWN
        add("catálogo de alarme", alarm.get("source", "UNKNOWN"),
            f"{alarm.get('key', '')} — {alarm.get('name', '')}. Escopo: {alarm.get('scope', '')}",
            lv)

    # 3. o que sustenta cada hipótese
    for h in entry.hypotheses:
        add("hipótese", h.source, f"{h.id} — {h.name}", h.evidence_level, h.doc_ref)

    # 4. o que sustenta cada verificação
    for c in entry.checks:
        add("verificação", c.source, f"ordem {c.order} — {c.action}",
            c.evidence_level, c.doc_ref)

    # 5. casos de campo relacionados
    for case in related:
        add("caso de campo", case.case_id,
            f"{case.symptom} (causa confirmada: {case.confirmed_cause})",
            case.evidence_level())
        for s in case.sources:
            add("documento do caso", s, f"citado por {case.case_id}",
                EvidenceLevel.UNKNOWN)

    return out


def _evidence_summary(hypotheses: list[dict], checks: list[dict],
                      sources: list[dict]) -> dict[str, Any]:
    """Distribuição dos níveis. Não substitui o nível de cada item."""
    def levels(rows):
        out = []
        for r in rows:
            try:
                out.append(EvidenceLevel(r.get("evidence_level", "UNKNOWN")))
            except ValueError:
                out.append(EvidenceLevel.UNKNOWN)
        return out

    todos = levels(hypotheses) + levels(checks) + levels(sources)
    contagem: dict[str, int] = {}
    for lv in todos:
        contagem[lv.value] = contagem.get(lv.value, 0) + 1
    elo_fraco = weakest(levels(hypotheses)) if hypotheses else EvidenceLevel.UNKNOWN
    documentado = any(lv is EvidenceLevel.MANUFACTURER_DOC for lv in todos)
    return {
        "by_level": contagem,
        "weakest_hypothesis_level": elo_fraco.value,
        "weakest_hypothesis_label": EVIDENCE_LABEL[elo_fraco],
        "has_manufacturer_documentation": documentado,
        "note": "o nível vale por item; este resumo é orientação, não substitui "
                "ler o nível de cada hipótese e verificação",
    }


def _caveats(entry: DiagnosticEntry, context: dict[str, Any], event: dict[str, Any]) -> list[str]:
    out = list(entry.caveats)
    if _simulated(context):
        out.insert(0, "ORIGEM SIMULADA: as evidências deste evento vieram do simulador, "
                      "não de uma máquina real. Não usar como registro de campo.")
    alarm = context.get("alarm")
    if alarm:
        if alarm.get("evidence_level") == EvidenceLevel.UNKNOWN.value:
            out.append(f"o código {alarm.get('code')} não consta do catálogo para esta "
                       f"aplicação/controlador: o significado precisa ser confirmado na máquina")
        if alarm.get("scope"):
            out.append(f"escopo da entrada de alarme: {alarm['scope']}")
        if alarm.get("reverse_warning"):
            out.append(f"a recíproca não vale: {alarm['reverse_warning']}")
    if not context.get("before", {}).get("available", False):
        out.append("contexto anterior indisponível: o evento ocorreu antes de o histórico "
                   "acumular janela suficiente")
    stop_by = context.get("stop_by")
    if stop_by and not stop_by.get("is_fault"):
        out.append("esta parada NÃO está classificada como falha")
    return out


def diagnose(event: dict[str, Any], cases_dir: Optional[str] = None) -> dict[str, Any]:
    """Diagnóstico de um evento gravado.

    `event` é o dicionário que o historian devolve (com `context`).
    A saída segue `DIAGNOSIS_SCHEMA_VERSION`.
    """
    context = event.get("context") or {}
    type_str = event.get("type", "")
    entry = entry_for(type_str)
    summary = event.get("summary") or context.get("summary") or \
        context.get("rule", {}).get("description", "")

    if entry is None:
        return {
            "diagnosis_schema_version": DIAGNOSIS_SCHEMA_VERSION,
            "event_id": event.get("id"),
            "event_type": type_str,
            "available": False,
            "reason": f"não há entrada de diagnóstico para o tipo '{type_str}'",
            "summary": summary,
            "evidences": _evidence_block(context),
            "changed": _changed_block(context),
            "hypotheses": [], "checks": [], "sources": [], "related_cases": [],
            "evidence_summary": _evidence_summary([], [], []),
            "caveats": ["tipo de evento sem biblioteca: registrar e tratar manualmente"],
        }

    kwargs = {"directory": cases_dir} if cases_dir else {}
    related: list[CaseRecord] = cases_for_event(type_str, **kwargs)

    hypotheses = _hypotheses_block(entry, context)
    checks = _checks_block(entry)
    sources = _sources_block(entry, context, related)

    return {
        # contrato
        "diagnosis_schema_version": DIAGNOSIS_SCHEMA_VERSION,
        "event_id": event.get("id"),
        "event_type": type_str,
        "severity": event.get("severity"),
        "ts_start": event.get("ts_start").isoformat() if hasattr(event.get("ts_start"), "isoformat")
                    else event.get("ts_start"),
        "available": True,
        # ordem de leitura: resumo -> evidências -> hipóteses -> verificações -> fontes
        "summary": summary,
        "question": entry.question,
        "rule": context.get("rule", {}),
        "data_origin": "SIMULADO" if _simulated(context) else "leitura do equipamento",
        "evidences": _evidence_block(context),
        "changed": _changed_block(context),
        "before": context.get("before", {}),
        "hypotheses": hypotheses,
        "checks": checks,
        "sources": sources,
        "evidence_summary": _evidence_summary(hypotheses, checks, sources),
        "related_cases": [c.summary() for c in related],
        "caveats": _caveats(entry, context, event),
        "read_only_note": "todas as verificações são executadas por uma pessoa; este sistema "
                          "nunca escreve no controlador",
    }


def diagnose_event_id(historian, event_id: int, cases_dir: Optional[str] = None) -> Optional[dict]:
    event = historian.event(event_id)
    if event is None:
        return None
    return diagnose(event, cases_dir=cases_dir)


def supported_types() -> list[str]:
    return sorted(t.value for t in EventType if entry_for(t) is not None)
