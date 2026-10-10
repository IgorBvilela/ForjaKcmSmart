"""Comissionamento / validação em campo: o registro do que foi conferido na visita.

Nada aqui afirma que a validação aconteceu: é o formulário que o técnico preenche na planta.
Cada conferência compara o valor lido pela Forja com o valor visto na tela do KCM, no mesmo
instante, e guarda endereço, bruto, qualidade e observação. Conferência gravada não muda:
correção é uma nova conferência.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from forja.domain.evidence import UNKNOWN
from forja.domain.quality import Quality
from forja.domain.tags import is_known_tag

_USER_PATTERN = r"^[\w .@\-]+$"


class CommissioningStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"

    @property
    def label_pt(self) -> str:
        return {
            CommissioningStatus.OPEN: "Em andamento",
            CommissioningStatus.CLOSED: "Encerrada",
        }[self]


class CheckResult(StrEnum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    NOT_EXPOSED = "NOT_EXPOSED"
    NOT_CHECKED = "NOT_CHECKED"

    @property
    def label_pt(self) -> str:
        return {
            CheckResult.MATCH: "Confere",
            CheckResult.MISMATCH: "Diverge",
            CheckResult.NOT_EXPOSED: "Não exposta pelo KCM",
            CheckResult.NOT_CHECKED: "Não conferida",
        }[self]


class CommissioningHeader(BaseModel):
    """O que se encontrou no equipamento. Desconhecido fica UNKNOWN, nunca suposto."""

    model_config = ConfigDict(extra="forbid")

    technician: str = Field(min_length=1, max_length=64, pattern=_USER_PATTERN)
    authorized_by: str = Field(default="", max_length=120)
    """Responsável da planta que autorizou conectar ao equipamento."""
    visit_date: date
    protocol_found: str = Field(default=UNKNOWN, max_length=120)
    kcm_software_version: str = Field(default=UNKNOWN, max_length=120)
    host_interface: str = Field(default=UNKNOWN, max_length=200)
    """Módulo Host/Anybus: modelo, part number e revisão, como na etiqueta."""
    ip: str = Field(default=UNKNOWN, max_length=64)
    subnet_mask: str = Field(default=UNKNOWN, max_length=64)
    gateway: str = Field(default=UNKNOWN, max_length=64)
    mapping_id: str = Field(default=UNKNOWN, max_length=64)
    mapping_version: int | None = None
    host_counters_before: str = Field(default="", max_length=500)
    """Contadores Host (leituras, escritas, erros) anotados antes de conectar a Forja."""
    host_counters_after: str = Field(default="", max_length=500)
    """Os mesmos contadores depois: escrita igual antes e depois prova que a Forja não escreveu."""
    notes_pt: str = Field(default="", max_length=4000)


class CommissioningSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: uuid4().hex, pattern=r"^[A-Za-z0-9_-]{8,64}$")
    equipment_id: str
    created_at_utc: datetime
    updated_at_utc: datetime
    status: CommissioningStatus = CommissioningStatus.OPEN
    header: CommissioningHeader
    conclusion_pt: str = Field(default="", max_length=4000)
    """Resultado geral escrito pelo técnico ao encerrar."""


class CommissioningCheck(BaseModel):
    """Uma conferência: valor Forja x valor na tela do KCM."""

    model_config = ConfigDict(extra="forbid")

    id: int | None = None
    session_id: str
    ts_utc: datetime
    tag: str
    label_pt: str = ""
    unit: str = ""
    address_text: str = Field(default="", max_length=300)
    forja_value: float | None = None
    forja_raw_hex: str | None = Field(default=None, max_length=512)
    forja_quality: Quality | None = None
    kcm_value: float | None = None
    kcm_text: str = Field(default="", max_length=200)
    """Como aparece na tela do KCM, quando não é número (ex.: texto de alarme)."""
    difference: float | None = None
    result: CheckResult
    note_pt: str = Field(default="", max_length=2000)
    technician: str = Field(min_length=1, max_length=64, pattern=_USER_PATTERN)

    @model_validator(mode="after")
    def _check(self) -> CommissioningCheck:
        if not is_known_tag(self.tag):
            raise ValueError(f"tag semântica desconhecida: {self.tag!r}")
        if self.forja_value is not None and self.kcm_value is not None:
            object.__setattr__(self, "difference", self.kcm_value - self.forja_value)
        return self


__all__ = [
    "CheckResult",
    "CommissioningCheck",
    "CommissioningHeader",
    "CommissioningSession",
    "CommissioningStatus",
]
