"""Mapping externo: tag semantica -> endereco de protocolo (spec §19, §20; Documento Mestre §13.1).

Regra estrutural: confirmed=true exige address, datatype, endianness e source != UNKNOWN
e uma validacao registrada (valor lido x valor na tela do KCM). Senao: UNCERTAIN.
Assembly 100/150, register 40001 ou qualquer endereco so existem como CONTEUDO deste arquivo.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from forja.domain.evidence import UNKNOWN, KnowledgeState
from forja.domain.quality import Quality
from forja.domain.tags import is_known_tag


class DataType(str, Enum):
    INT16 = "int16"
    UINT16 = "uint16"
    INT32 = "int32"
    UINT32 = "uint32"
    FLOAT32 = "float32"
    FLOAT64 = "float64"
    BOOL = "bool"
    BITFIELD16 = "bitfield16"
    BITFIELD32 = "bitfield32"
    STRING = "string"

    @property
    def word_count(self) -> int:
        return {
            DataType.INT16: 1,
            DataType.UINT16: 1,
            DataType.BOOL: 1,
            DataType.BITFIELD16: 1,
            DataType.INT32: 2,
            DataType.UINT32: 2,
            DataType.FLOAT32: 2,
            DataType.BITFIELD32: 2,
            DataType.FLOAT64: 4,
            DataType.STRING: 1,
        }[self]


class Endianness(str, Enum):
    """Ordem de bytes/palavras. Nomes classicos entre parenteses na documentacao."""

    BIG = "big"  # ABCD
    LITTLE = "little"  # DCBA
    BIG_WORD_SWAP = "big_word_swap"  # CDAB
    LITTLE_WORD_SWAP = "little_word_swap"  # BADC


class Scale(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    factor: float = 1.0
    offset: float = 0.0

    def apply(self, raw: float) -> float:
        return raw * self.factor + self.offset


class Validation(BaseModel):
    """Comparacao manual: valor lido pela Forja x valor exibido no KCM (wizard passo 6)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    validated_at_utc: datetime
    validated_by: str
    forja_value: float | str
    kcm_value: float | str
    matched: bool
    note_pt: str = ""


class MappingEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    semantic_tag: str
    protocol_address: str | dict[str, Any] = UNKNOWN
    """Modbus: {area: holding|input|coil|discrete, address: int, count: int}
    EtherNet/IP: {kind: assembly|attribute, class: int, instance: int, attribute: int, offset: int, length: int}
    Simulador: "sim:<tag>". UNKNOWN enquanto nao houver fonte."""
    datatype: DataType | str = UNKNOWN
    endianness: Endianness | str = UNKNOWN
    scale: Scale | str = UNKNOWN
    unit: str | None = None
    confirmed: bool = False
    source: str = UNKNOWN
    """De onde veio o endereco: documento (titulo, revisao, pagina), captura autorizada, teste."""
    evidence: KnowledgeState = KnowledgeState.UNKNOWN
    validation: Validation | None = None
    valid_min: float | None = None
    valid_max: float | None = None
    notes_pt: str = ""

    @model_validator(mode="after")
    def _check(self) -> MappingEntry:
        if not is_known_tag(self.semantic_tag):
            raise ValueError(f"tag semântica desconhecida: {self.semantic_tag!r}")
        if self.confirmed:
            missing = [
                name
                for name, val in (
                    ("protocol_address", self.protocol_address),
                    ("datatype", self.datatype),
                    ("endianness", self.endianness),
                    ("source", self.source),
                )
                if val == UNKNOWN
            ]
            if missing:
                raise ValueError(
                    f"{self.semantic_tag}: confirmed=true exige {', '.join(missing)} != UNKNOWN"
                )
            if self.validation is None or not self.validation.matched:
                raise ValueError(
                    f"{self.semantic_tag}: confirmed=true exige validação registrada com matched=true"
                )
        if self.valid_min is not None and self.valid_max is not None and self.valid_min > self.valid_max:
            raise ValueError(f"{self.semantic_tag}: valid_min > valid_max")
        return self

    @property
    def is_readable(self) -> bool:
        """Ha o minimo para tentar ler (endereco e tipo conhecidos)."""
        return self.protocol_address != UNKNOWN and self.datatype != UNKNOWN

    def quality_for(self, driver: str) -> Quality:
        """Qualidade que uma leitura bem-sucedida desta tag recebe."""
        if driver == "simulator":
            return Quality.SIMULATED
        return Quality.GOOD if self.confirmed else Quality.UNCERTAIN


class Mapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    mapping_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_\-]{1,63}$")
    version: int = Field(default=1, ge=1)
    equipment_id: str
    driver: str = UNKNOWN
    source: str = UNKNOWN
    confirmed_by: str | None = None
    entries: list[MappingEntry] = Field(default_factory=list)
    notes_pt: str = ""

    @model_validator(mode="after")
    def _unique_tags(self) -> Mapping:
        seen: set[str] = set()
        for e in self.entries:
            if e.semantic_tag in seen:
                raise ValueError(f"tag duplicada no mapping: {e.semantic_tag}")
            seen.add(e.semantic_tag)
        return self

    @property
    def readable_entries(self) -> list[MappingEntry]:
        return [e for e in self.entries if e.is_readable]

    @property
    def unknown_entries(self) -> list[MappingEntry]:
        return [e for e in self.entries if not e.is_readable]

    def entry(self, tag: str) -> MappingEntry | None:
        for e in self.entries:
            if e.semantic_tag == tag:
                return e
        return None

    @property
    def source_label(self) -> str:
        return f"driver:{self.driver}:{self.mapping_id}@{self.version}"
