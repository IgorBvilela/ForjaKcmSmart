"""Alarmes com chave composta e classificacao de STOP BY (spec §34-36; Documento Mestre §9).

Nunca: alarm_code -> significado universal. A chave e
(manufacturer, controller, application, software_version, code).
Sem correspondencia exata -> 'nao catalogado' (candidatos sao so sugestao).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from forja.domain.evidence import UNKNOWN, EvidenceLevel, KnowledgeState


class AlarmKey(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    manufacturer: str = UNKNOWN
    controller: str = UNKNOWN
    application: str = UNKNOWN
    software_version: str = UNKNOWN
    code: str

    def matches_exact(self, other: AlarmKey) -> bool:
        return self == other


class AlarmDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    key: AlarmKey
    text: str
    """Texto como aparece no KCM (ex.: 'BELTLOAD LOW')."""
    title_pt: str
    meaning_pt: str = ""
    evidence: EvidenceLevel
    source: str = UNKNOWN
    """Documento (titulo, revisao, pagina) ou 'foto da tela em <data>'."""
    note_pt: str = ""

    @property
    def observed_only(self) -> bool:
        return self.evidence in (EvidenceLevel.FIELD_OBSERVED, EvidenceLevel.HYPOTHESIS)


class AlarmLookup(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    definition: AlarmDefinition | None
    candidates: tuple[AlarmDefinition, ...] = ()

    @property
    def title_pt(self) -> str:
        if self.definition is not None:
            return self.definition.title_pt
        return f"Alarme {self.code} (não catalogado para esta aplicação/versão)"

    @property
    def qualifier_pt(self) -> str:
        if self.definition is None:
            return "Não catalogado"
        if self.definition.evidence == EvidenceLevel.FIELD_OBSERVED:
            return "Observado nesta aplicação"
        return self.definition.evidence.label_pt


class AlarmCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    definitions: list[AlarmDefinition] = Field(default_factory=list)

    def lookup(self, key: AlarmKey) -> AlarmLookup:
        exact = [d for d in self.definitions if d.key == key]
        if exact:
            return AlarmLookup(code=key.code, definition=exact[0])
        candidates = tuple(
            d
            for d in self.definitions
            if d.key.code == key.code
            and d.key.manufacturer in (key.manufacturer, UNKNOWN)
            and d.key.controller in (key.controller, UNKNOWN)
            and d.key.application in (key.application, UNKNOWN)
        )
        return AlarmLookup(code=key.code, definition=None, candidates=candidates)


class StopByClass(str, Enum):
    NORMAL = "NORMAL"
    REQUESTED = "REQUESTED"
    PROTECTION = "PROTECTION"
    INTERLOCK = "INTERLOCK"
    FAULT = "FAULT"
    UNKNOWN = "UNKNOWN"

    @property
    def label_pt(self) -> str:
        return {
            StopByClass.NORMAL: "Parada normal",
            StopByClass.REQUESTED: "Parada solicitada",
            StopByClass.PROTECTION: "Proteção",
            StopByClass.INTERLOCK: "Intertravamento",
            StopByClass.FAULT: "Falha",
            StopByClass.UNKNOWN: "Motivo desconhecido",
        }[self]


class StopByEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    raw_label: str
    classification: StopByClass = StopByClass.UNKNOWN
    evidence: KnowledgeState = KnowledgeState.UNKNOWN
    source: str = UNKNOWN
    note_pt: str = ""


class StopByCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: list[StopByEntry] = Field(default_factory=list)

    def classify(self, raw_label: str | None) -> StopByEntry:
        if raw_label is None or raw_label == "":
            return StopByEntry(raw_label="", classification=StopByClass.UNKNOWN)
        for e in self.entries:
            if e.raw_label.lower() == raw_label.lower():
                return e
        return StopByEntry(raw_label=raw_label, classification=StopByClass.UNKNOWN)
