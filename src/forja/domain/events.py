"""Eventos deterministicos (spec §24, §27, §51; Documento Mestre §17, §22).

Evento guarda janela pre-evento para responder 'o que mudou primeiro?'.
Titulo em portugues para a UI; codigo interno so em 'Detalhes tecnicos'.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from forja.domain.evidence import EvidenceLevel
from forja.domain.quality import Quality
from forja.domain.samples import Sample


class Severity(StrEnum):
    INFO = "INFO"
    ATTENTION = "ATTENTION"
    CRITICAL = "CRITICAL"

    @property
    def label_pt(self) -> str:
        return {
            Severity.INFO: "Informação",
            Severity.ATTENTION: "Atenção",
            Severity.CRITICAL: "Crítico",
        }[self]


class EventStatus(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"
    EXPIRED = "EXPIRED"


class SourceRef(BaseModel):
    """Referencia rastreavel (fonte) usada por eventos e diagnosticos."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    kind: Literal[
        "rule",
        "case",
        "document",
        "field_observation",
        "manufacturer_doc",
        "machine_doc",
        "opinion",
    ]
    title: str
    reference: str = ""
    """Documento/revisao/secao/pagina, ou id do caso, ou id da regra."""
    evidence_level: EvidenceLevel


class WhatChangedItem(BaseModel):
    """ANTES / AGORA / VARIACAO de uma variavel (spec §27)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tag: str
    label_pt: str
    unit: str
    before: float | None
    now: float | None
    delta: float | None
    delta_kind: Literal["pct", "points", "abs", "none"]
    changed_first: bool = False
    ts_start_utc: datetime | None = None
    """Instante em que a variavel saiu do padrao (ordem conta a historia)."""
    text_pt: str = ""


class TimelinePoint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ts_utc: datetime
    text_pt: str
    kind: Literal["forja", "kcm", "human"] = "forja"
    tag: str | None = None


class EventContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    pre_window_s: int
    post_window_s: int
    pre_samples: tuple[Sample, ...] = ()
    during_samples: tuple[Sample, ...] = ()
    post_samples: tuple[Sample, ...] = ()
    what_changed: tuple[WhatChangedItem, ...] = ()
    timeline: tuple[TimelinePoint, ...] = ()
    gap_count: int = 0
    stale_count: int = 0
    comm_error_count: int = 0


class Resolution(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    resolved_at_utc: datetime
    resolved_by: str
    resolution_class: Literal[
        "NORMAL_STOP", "REQUESTED", "PROTECTION", "INTERLOCK", "FAULT", "FALSE_POSITIVE", "UNKNOWN"
    ] = "UNKNOWN"
    note_pt: str = ""


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    id: str = Field(default_factory=lambda: uuid4().hex)
    equipment_id: str
    type: str
    """Codigo interno (ex.: BELT_LOAD_LOW). Nunca titulo da UI."""
    title_pt: str
    start_utc: datetime
    end_utc: datetime | None = None
    severity: Severity
    summary_pt: str
    rule_id: str
    rule_version: int = 1
    context: EventContext
    sources: tuple[SourceRef, ...] = ()
    quality: Quality
    """Pior qualidade dos dados que dispararam."""
    status: EventStatus = EventStatus.OPEN
    acked_by: str | None = None
    acked_at_utc: datetime | None = None
    resolution: Resolution | None = None
    dedupe_key: str
    diagnosis_ref: str | None = None
    """Id da entrada da biblioteca de diagnostico que explica este tipo de evento."""

    @property
    def is_open(self) -> bool:
        return self.end_utc is None

    @property
    def duration_s(self) -> float | None:
        if self.end_utc is None:
            return None
        return (self.end_utc - self.start_utc).total_seconds()


class EventTransition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["OPEN", "UPDATE", "CLOSE"]
    event: Event
