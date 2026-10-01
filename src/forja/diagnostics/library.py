"""Biblioteca de diagnostico (knowledge/diagnostics/*.yaml) e casos de campo (knowledge/cases).

Cada entrada traz hipoteses ('Comportamento compativel com...'), verificacoes em ordem e fontes,
cada uma com o proprio nivel de evidencia. Uma hipotese nunca contem a palavra 'causa' e nunca
recebe nivel mais forte do que a fonte mais forte que a sustenta.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from forja.config.loader import load_yaml_file
from forja.domain import (
    UNKNOWN,
    Caveat,
    ConfigError,
    EvidenceLevel,
    Hypothesis,
    KnowledgeState,
    NextCheck,
    SourceRef,
)
from forja.domain.evidence import strongest

HYPOTHESIS_PREFIX_PT = "Comportamento compatível com"
FORBIDDEN_HYPOTHESIS_WORD = "causa"
INTERNAL_CODE_PATTERN = r"^[A-Z][A-Z0-9_]{2,63}$"
REF_PATTERN = r"^[a-z][a-z0-9_]{1,63}$"


def _forbid_cause(text: str, where: str) -> None:
    if FORBIDDEN_HYPOTHESIS_WORD in text.lower():
        raise ValueError(f"{where}: hipótese não pode conter '{FORBIDDEN_HYPOTHESIS_WORD}'")


class DiagnosisEntry(BaseModel):
    """Uma entrada da biblioteca: o que a Forja sabe dizer sobre um tipo de evento."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = 1
    ref: str = Field(pattern=REF_PATTERN)
    internal_code: str = Field(pattern=INTERNAL_CODE_PATTERN)
    title_pt: str = Field(min_length=3)
    text_pt: str = Field(min_length=10)
    sources: list[SourceRef] = Field(min_length=1)
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    next_checks: list[NextCheck] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    related_rules: list[str] = Field(default_factory=list)
    related_cases: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> DiagnosisEntry:
        if self.title_pt.strip().upper() == self.internal_code:
            raise ValueError("title_pt não pode ser o código interno")
        by_id = {s.id: s for s in self.sources}
        if len(by_id) != len(self.sources):
            raise ValueError("ids de fonte duplicados")
        check_ids = {c.id for c in self.next_checks}
        if len(check_ids) != len(self.next_checks):
            raise ValueError("ids de verificação duplicados")
        orders = [c.order for c in self.next_checks]
        if orders != sorted(orders) or len(set(orders)) != len(orders):
            raise ValueError("next_checks devem ter 'order' crescente e único")
        for h in self.hypotheses:
            if not h.text_pt.startswith(HYPOTHESIS_PREFIX_PT):
                raise ValueError(f"hipótese {h.id} deve começar com {HYPOTHESIS_PREFIX_PT!r}")
            _forbid_cause(h.text_pt, f"hipótese {h.id}")
            _forbid_cause(h.rationale_pt, f"hipótese {h.id} (rationale)")
            missing = [v for v in h.verification_ids if v not in check_ids]
            if missing:
                raise ValueError(f"hipótese {h.id}: verificações inexistentes {missing}")
            _check_no_promotion("hipótese", h.id, h.evidence_level, h.source_ids, by_id)
        for c in self.next_checks:
            _check_no_promotion("verificação", c.id, c.evidence_level, c.source_ids, by_id)
        return self

    def caveat_models(self) -> tuple[Caveat, ...]:
        return tuple(Caveat(text_pt=c) for c in self.caveats)


def _check_no_promotion(
    kind: str,
    item_id: str,
    level: EvidenceLevel,
    source_ids: tuple[str, ...],
    by_id: dict[str, SourceRef],
) -> None:
    """Mesma regra estrutural do Diagnosis: nivel nunca acima da fonte mais forte."""
    if not source_ids:
        if level.is_stronger_than(EvidenceLevel.TECHNICAL_OPINION):
            raise ValueError(f"{kind} {item_id}: nível {level.value} sem fonte")
        return
    missing = [sid for sid in source_ids if sid not in by_id]
    if missing:
        raise ValueError(f"{kind} {item_id}: fontes inexistentes {missing}")
    cap = strongest([by_id[sid].evidence_level for sid in source_ids])
    if cap is not None and level.is_stronger_than(cap):
        raise ValueError(f"{kind} {item_id}: nível {level.value} acima da fonte ({cap.value})")


class DiagnosisLibrary:
    """Entradas indexadas por ref e por codigo interno."""

    def __init__(self, entries: list[DiagnosisEntry]) -> None:
        self._by_ref: dict[str, DiagnosisEntry] = {}
        self._by_code: dict[str, DiagnosisEntry] = {}
        for e in entries:
            if e.ref in self._by_ref:
                raise ConfigError(f"ref de diagnóstico duplicada: {e.ref}")
            if e.internal_code in self._by_code:
                raise ConfigError(f"internal_code de diagnóstico duplicado: {e.internal_code}")
            self._by_ref[e.ref] = e
            self._by_code[e.internal_code] = e

    def get(self, ref: str) -> DiagnosisEntry:
        try:
            return self._by_ref[ref]
        except KeyError as exc:
            raise KeyError(f"entrada de diagnóstico desconhecida: {ref!r}") from exc

    def find(self, ref: str | None, internal_code: str | None = None) -> DiagnosisEntry | None:
        if ref is not None and ref in self._by_ref:
            return self._by_ref[ref]
        if internal_code is not None:
            return self._by_code.get(internal_code)
        return None

    def refs(self) -> list[str]:
        return list(self._by_ref.keys())

    @property
    def entries(self) -> list[DiagnosisEntry]:
        return list(self._by_ref.values())

    def __len__(self) -> int:
        return len(self._by_ref)


class CaseMeasurement(BaseModel):
    """Medicao ou referencia observada no atendimento. Nunca vira threshold."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    what_pt: str
    value: str
    nature_pt: str
    evidence: KnowledgeState = KnowledgeState.FIELD_OBSERVED


class FieldCase(BaseModel):
    """Caso de campo estruturado (knowledge/cases). confirmed_cause fica UNKNOWN sem prova."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = 1
    id: str = Field(pattern=r"^CASE-[A-Z0-9][A-Z0-9_\-]{3,80}$")
    title_pt: str
    plant: str = UNKNOWN
    area: str = UNKNOWN
    equipment: str = UNKNOWN
    application: str = UNKNOWN
    period_pt: str = UNKNOWN
    evidence: KnowledgeState = KnowledgeState.FIELD_OBSERVED
    confirmed_cause: str = UNKNOWN
    observed_facts_pt: list[str] = Field(default_factory=list)
    interventions_pt: list[str] = Field(default_factory=list)
    measurements: list[CaseMeasurement] = Field(default_factory=list)
    calibration_reported_pt: list[str] = Field(default_factory=list)
    learned_rule_pt: str = ""
    related_rules: list[str] = Field(default_factory=list)
    related_diagnostics: list[str] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)
    notes_pt: str = ""

    @field_validator("confirmed_cause")
    @classmethod
    def _cause_unknown_or_sourced(cls, v: str) -> str:
        if v != UNKNOWN and len(v) < 20:
            raise ValueError("confirmed_cause só sai de UNKNOWN com descrição e fonte rastreável")
        return v


def _fmt(exc: ValidationError) -> str:
    return "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())


def load_entry(path: Path) -> DiagnosisEntry:
    data = load_yaml_file(path)
    try:
        return DiagnosisEntry.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"{path.name}: {_fmt(exc)}") from exc


def load_library(dir_: Path) -> DiagnosisLibrary:
    """Carrega knowledge/diagnostics/*.yaml. Pasta ausente = biblioteca vazia."""
    if not dir_.is_dir():
        return DiagnosisLibrary([])
    entries = [load_entry(p) for p in sorted(dir_.glob("*.yaml")) if not p.name.startswith("_")]
    return DiagnosisLibrary(entries)


def load_case(path: Path) -> FieldCase:
    data = load_yaml_file(path)
    try:
        return FieldCase.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"{path.name}: {_fmt(exc)}") from exc


def load_cases(dir_: Path) -> list[FieldCase]:
    """Carrega knowledge/cases/*.yaml. Pasta ausente = lista vazia."""
    if not dir_.is_dir():
        return []
    return [load_case(p) for p in sorted(dir_.glob("*.yaml")) if not p.name.startswith("_")]
