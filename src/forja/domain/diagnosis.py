"""Contrato oficial do diagnostico: JSON v1.0 (spec §25, §28, §29, §81; Documento Mestre §5.2, §17.1).

Secoes oficiais, nesta ordem: RESUMO, EVIDENCIAS, O QUE MUDOU, HIPOTESES, PROXIMAS VERIFICACOES,
FONTES, RESSALVAS. A UI consome este JSON. Nunca reparsear texto da CLI.

Lei de Hyrum: cada chave e compromisso. Mudanca so aditiva; quebra = nova versao com adaptador.
Regra estrutural: um item nunca recebe nivel de evidencia mais forte do que a fonte mais forte que o sustenta.
Hipotese nao e causa. Nao existe campo 'causa'.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from forja.domain.events import Severity, SourceRef, WhatChangedItem
from forja.domain.evidence import EvidenceLevel, EvidencePromotionError, strongest, weakest
from forja.domain.quality import Quality
from forja.version import DIAGNOSIS_SCHEMA_VERSION, ENGINE_VERSION

MANDATORY_CAVEAT_PT = "Hipóteses não representam causa confirmada."


class DiagnosisSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    title_pt: str
    text_pt: str
    internal_code: str
    severity: Severity


class EvidenceItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    text_pt: str
    tag: str | None = None
    value: float | None = None
    unit: str | None = None
    quality: Quality | None = None
    evidence_level: EvidenceLevel
    ts_utc: datetime | None = None


class Hypothesis(BaseModel):
    """Comportamento compativel com..., nunca 'causa:'."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    text_pt: str
    evidence_level: EvidenceLevel
    rationale_pt: str
    verification_ids: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()


class NextCheck(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    order: int
    text_pt: str
    how_pt: str = ""
    safety_pt: str = "Conforme procedimento da planta."
    evidence_level: EvidenceLevel
    source_ids: tuple[str, ...] = ()


class Caveat(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    text_pt: str


class EvidenceSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    weakest_level: EvidenceLevel | None
    strongest_level: EvidenceLevel | None
    counts: dict[str, int]
    note_pt: str = (
        "Resumo do conjunto. Não substitui a leitura item a item: cada hipótese, verificação e fonte "
        "tem o próprio nível."
    )


class Diagnosis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    diagnosis_schema_version: str = DIAGNOSIS_SCHEMA_VERSION
    diagnosis_id: str = Field(default_factory=lambda: uuid4().hex)
    event_id: str
    equipment_id: str
    generated_at_utc: datetime
    engine_version: str = ENGINE_VERSION
    summary: DiagnosisSummary
    evidence: tuple[EvidenceItem, ...]
    what_changed: tuple[WhatChangedItem, ...]
    hypotheses: tuple[Hypothesis, ...]
    next_checks: tuple[NextCheck, ...]
    sources: tuple[SourceRef, ...]
    caveats: tuple[Caveat, ...]
    evidence_summary: EvidenceSummary

    @model_validator(mode="after")
    def _structural_rules(self) -> Diagnosis:
        if not any(c.text_pt == MANDATORY_CAVEAT_PT for c in self.caveats):
            raise ValueError(f"ressalva obrigatória ausente: {MANDATORY_CAVEAT_PT!r}")
        by_id = {s.id: s for s in self.sources}
        for h in self.hypotheses:
            _check_no_promotion("hipótese", h.id, h.evidence_level, h.source_ids, by_id)
            if "causa:" in h.text_pt.lower() or "causa confirmada" in h.text_pt.lower():
                raise ValueError(f"hipótese {h.id} afirma causa; use 'comportamento compatível com'")
        for c in self.next_checks:
            _check_no_promotion("verificação", c.id, c.evidence_level, c.source_ids, by_id)
        return self

    @staticmethod
    def build_evidence_summary(
        evidence: tuple[EvidenceItem, ...],
        hypotheses: tuple[Hypothesis, ...],
        next_checks: tuple[NextCheck, ...],
        sources: tuple[SourceRef, ...],
    ) -> EvidenceSummary:
        levels = (
            [e.evidence_level for e in evidence]
            + [h.evidence_level for h in hypotheses]
            + [c.evidence_level for c in next_checks]
            + [s.evidence_level for s in sources]
        )
        counts: dict[str, int] = {}
        for lv in levels:
            counts[lv.value] = counts.get(lv.value, 0) + 1
        return EvidenceSummary(
            weakest_level=weakest(levels), strongest_level=strongest(levels), counts=counts
        )


def _check_no_promotion(
    kind: str,
    item_id: str,
    level: EvidenceLevel,
    source_ids: tuple[str, ...],
    by_id: dict[str, SourceRef],
) -> None:
    """Item sem fonte: no maximo TECHNICAL_OPINION. Item com fontes: no maximo a fonte mais forte."""
    if not source_ids:
        if level.is_stronger_than(EvidenceLevel.TECHNICAL_OPINION):
            raise EvidencePromotionError(
                f"{kind} {item_id}: nível {level.value} sem fonte; máximo é TECHNICAL_OPINION"
            )
        return
    missing = [sid for sid in source_ids if sid not in by_id]
    if missing:
        raise ValueError(f"{kind} {item_id}: fontes inexistentes {missing}")
    cap = strongest([by_id[sid].evidence_level for sid in source_ids])
    if cap is not None and level.is_stronger_than(cap):
        raise EvidencePromotionError(
            f"{kind} {item_id}: nível {level.value} mais forte que a fonte mais forte ({cap.value})"
        )


OFFICIAL_SECTIONS_PT: tuple[tuple[str, str], ...] = (
    ("summary", "RESUMO"),
    ("evidence", "EVIDÊNCIAS"),
    ("what_changed", "O QUE MUDOU"),
    ("hypotheses", "HIPÓTESES"),
    ("next_checks", "PRÓXIMAS VERIFICAÇÕES"),
    ("sources", "FONTES"),
    ("caveats", "RESSALVAS"),
)
