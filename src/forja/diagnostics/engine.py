"""Motor de diagnostico: Event -> Diagnosis v1.0 (sete secoes, na ordem oficial).

Evidencia vem das amostras do evento; 'O QUE MUDOU' vem do contexto do evento; hipoteses,
verificacoes e fontes vem da biblioteca. Toda saida passa pela validacao estrutural do Diagnosis
(ressalva obrigatoria, nenhuma hipotese afirma causa, nenhum item acima da sua fonte).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import tzinfo
from uuid import NAMESPACE_URL, uuid5

from forja.diagnostics.library import DiagnosisEntry, DiagnosisLibrary
from forja.diagnostics.translator import Translator
from forja.domain import (
    MANDATORY_CAVEAT_PT,
    Caveat,
    Clock,
    Diagnosis,
    DiagnosisSummary,
    Event,
    EvidenceItem,
    EvidenceLevel,
    Hypothesis,
    NextCheck,
    Quality,
    Sample,
    SourceRef,
    get_tag,
)
from forja.events.plant_time import DEFAULT_TIMEZONE, fmt_time_pt, resolve_zone
from forja.version import ENGINE_VERSION

FALLBACK_REF = "sem_entrada_biblioteca"
FALLBACK_TEXT_PT = (
    "A biblioteca de diagnóstico ainda não tem entrada para este tipo de evento. "
    "Registre o comportamento observado e as leituras do KCM no momento; a manutenção decide."
)
SIMULATED_CAVEAT_PT = (
    "Os dados deste evento são SIMULADOS pela Forja. Não representam o KCM da GTEX nem "
    "qualquer equipamento real."
)
UNCERTAIN_CAVEAT_PT = (
    "Parte das leituras tem qualidade 'Não validado': o mapping ainda não foi confirmado contra "
    "a tela do KCM."
)
THRESHOLD_CAVEAT_PT = (
    "Os limiares que abriram este evento são regras Forja, relativos ao próprio comportamento "
    "do equipamento ou ao cenário simulado. Não são limites do KCM."
)
CAUSE_UNKNOWN_CAVEAT_PT = (
    "A causa confirmada permanece desconhecida até haver evidência de campo que feche a "
    "cadeia causal."
)


def evidence_level_for_quality(quality: Quality | None) -> EvidenceLevel:
    """Leitura validada = observado em campo; simulada = regra Forja; o resto = hipotese."""
    if quality == Quality.GOOD:
        return EvidenceLevel.FIELD_OBSERVED
    if quality == Quality.SIMULATED:
        return EvidenceLevel.FORJA_RULE
    return EvidenceLevel.HYPOTHESIS


def diagnosis_id_for(event_id: str) -> str:
    """Id deterministico: mesmo evento e mesmo motor, mesmo diagnostico."""
    return uuid5(NAMESPACE_URL, f"forja:diagnosis:{ENGINE_VERSION}:{event_id}").hex


class DiagnosisEngine:
    """Produz o Diagnosis v1.0 de um Event, sem rede, sem IA, sem escrita no KCM."""

    def __init__(
        self,
        library: DiagnosisLibrary,
        clock: Clock,
        translator: Translator | None = None,
        timezone: str | tzinfo = DEFAULT_TIMEZONE,
    ) -> None:
        self.library = library
        self._clock = clock
        self.translator = translator or Translator()
        self.zone: tzinfo = resolve_zone(timezone)
        """Fuso da planta (config edge.timezone): todo horario em texto *_pt sai neste fuso."""

    def diagnose(self, event: Event) -> Diagnosis:
        entry = self.library.find(event.diagnosis_ref, event.type) or self._fallback_entry(event)
        sources = _merge_sources(entry.sources, event.sources)
        evidence = self._evidence(event)
        hypotheses = tuple(entry.hypotheses)
        next_checks = tuple(sorted(entry.next_checks, key=lambda c: c.order))
        summary = DiagnosisSummary(
            title_pt=self.translator.code_title(event.type, default=entry.title_pt),
            text_pt=f"{event.summary_pt} {entry.text_pt}".strip(),
            internal_code=event.type,
            severity=event.severity,
        )
        caveats = self._caveats(entry, event)
        return Diagnosis(
            diagnosis_id=diagnosis_id_for(event.id),
            event_id=event.id,
            equipment_id=event.equipment_id,
            generated_at_utc=self._clock.now_utc(),
            summary=summary,
            evidence=evidence,
            what_changed=event.context.what_changed,
            hypotheses=hypotheses,
            next_checks=next_checks,
            sources=sources,
            caveats=caveats,
            evidence_summary=Diagnosis.build_evidence_summary(
                evidence, hypotheses, next_checks, sources
            ),
        )

    # ------------------------------------------------------------------ secoes

    def _evidence(self, event: Event) -> tuple[EvidenceItem, ...]:
        ctx = event.context
        # Id e versao da regra ficam em event.rule_id / rule_version ('Detalhes tecnicos').
        since_pt = fmt_time_pt(event.start_utc, self.zone, reference=self._clock.now_utc())
        items: list[EvidenceItem] = [
            EvidenceItem(
                id="EV-RULE",
                text_pt=f"Regra Forja '{event.title_pt}' atendida a partir de {since_pt}.",
                evidence_level=EvidenceLevel.FORJA_RULE,
                ts_utc=event.start_utc,
            )
        ]
        for item in ctx.what_changed:
            if item.now is None and item.before is None:
                continue
            sample = _latest_for_tag(ctx.during_samples, item.tag) or _latest_for_tag(
                ctx.pre_samples, item.tag
            )
            quality = sample.quality if sample is not None else event.quality
            items.append(
                EvidenceItem(
                    id=f"EV-{item.tag.upper()}",
                    text_pt=f"{item.label_pt}: {item.text_pt}",
                    tag=item.tag,
                    value=item.now,
                    unit=item.unit or None,
                    quality=quality,
                    evidence_level=evidence_level_for_quality(quality),
                    ts_utc=item.ts_start_utc or event.start_utc,
                )
            )
        for n, point in enumerate((p for p in ctx.timeline if p.kind == "kcm"), start=1):
            items.append(
                EvidenceItem(
                    id=f"EV-KCM-{n}",
                    text_pt=point.text_pt,
                    tag=point.tag,
                    quality=event.quality,
                    evidence_level=evidence_level_for_quality(event.quality),
                    ts_utc=point.ts_utc,
                )
            )
        items.extend(self._quality_evidence(event))
        return tuple(items)

    @staticmethod
    def _quality_evidence(event: Event) -> list[EvidenceItem]:
        ctx = event.context
        out: list[EvidenceItem] = []
        if ctx.comm_error_count:
            out.append(
                EvidenceItem(
                    id="EV-COMM",
                    text_pt=(
                        f"{ctx.comm_error_count} leitura(s) sem comunicação na janela analisada: "
                        "a tentativa de leitura falhou; não é valor antigo."
                    ),
                    quality=Quality.COMM_ERROR,
                    evidence_level=EvidenceLevel.FORJA_RULE,
                    ts_utc=event.start_utc,
                )
            )
        if ctx.stale_count:
            out.append(
                EvidenceItem(
                    id="EV-STALE",
                    text_pt=(
                        f"{ctx.stale_count} valor(es) antigo(s) na janela analisada: a leitura "
                        "não foi renovada e nada foi gravado como novo."
                    ),
                    quality=Quality.STALE,
                    evidence_level=EvidenceLevel.FORJA_RULE,
                    ts_utc=event.start_utc,
                )
            )
        gaps = ctx.gap_count - ctx.comm_error_count
        if gaps > 0:
            out.append(
                EvidenceItem(
                    id="EV-GAP",
                    text_pt=(
                        f"{gaps} leitura(s) ausente(s) na janela analisada; nada foi interpolado."
                    ),
                    evidence_level=EvidenceLevel.FORJA_RULE,
                    ts_utc=event.start_utc,
                )
            )
        return out

    @staticmethod
    def _caveats(entry: DiagnosisEntry, event: Event) -> tuple[Caveat, ...]:
        texts: list[str] = [MANDATORY_CAVEAT_PT, *entry.caveats, THRESHOLD_CAVEAT_PT]
        qualities = {s.quality for s in (*event.context.pre_samples, *event.context.during_samples)}
        if Quality.SIMULATED in qualities or event.quality == Quality.SIMULATED:
            texts.append(SIMULATED_CAVEAT_PT)
        if Quality.UNCERTAIN in qualities or event.quality == Quality.UNCERTAIN:
            texts.append(UNCERTAIN_CAVEAT_PT)
        texts.append(CAUSE_UNKNOWN_CAVEAT_PT)
        return tuple(Caveat(text_pt=t) for t in dict.fromkeys(texts))

    @staticmethod
    def _fallback_entry(event: Event) -> DiagnosisEntry:
        sources = list(event.sources) or [
            SourceRef(
                id=f"SRC-RULE-{event.rule_id}",
                kind="rule",
                title=f"Regra Forja '{event.title_pt}'",
                reference=f"config/rules/{event.rule_id}.yaml",
                evidence_level=EvidenceLevel.FORJA_RULE,
            )
        ]
        return DiagnosisEntry(
            ref=FALLBACK_REF,
            internal_code=event.type,
            title_pt=event.title_pt,
            text_pt=FALLBACK_TEXT_PT,
            sources=sources,
            hypotheses=[],
            next_checks=[
                NextCheck(
                    id="V1",
                    order=1,
                    text_pt="Registrar o comportamento e as leituras do KCM no momento do evento.",
                    how_pt=(
                        "Anotar valores da tela do KCM, alarmes ativos e horário; não alterar nada."
                    ),
                    evidence_level=EvidenceLevel.TECHNICAL_OPINION,
                )
            ],
            caveats=[
                "Sem entrada na biblioteca de diagnóstico para o evento "
                f"'{event.title_pt}'; o código interno fica em 'Detalhes técnicos'."
            ],
        )


def _merge_sources(
    primary: Sequence[SourceRef], extra: Sequence[SourceRef]
) -> tuple[SourceRef, ...]:
    seen: dict[str, SourceRef] = {}
    for s in (*primary, *extra):
        seen.setdefault(s.id, s)
    return tuple(seen.values())


def _latest_for_tag(samples: Sequence[Sample], tag: str) -> Sample | None:
    for s in reversed(samples):
        if s.tag == tag:
            return s
    return None


def hypothesis_titles(entry: DiagnosisEntry) -> list[str]:
    """Atalho para UI/testes: textos das hipoteses de uma entrada."""
    return [h.text_pt for h in entry.hypotheses]


def tag_label(tag: str) -> str:
    return get_tag(tag).label_pt


__all__ = [
    "DiagnosisEngine",
    "Hypothesis",
    "diagnosis_id_for",
    "evidence_level_for_quality",
    "hypothesis_titles",
    "tag_label",
]
