"""Hierarquia de ativos e perfil de equipamento (spec §13, §14; Documento Mestre §14, §15.1).

Plant -> Area -> Line -> Equipment -> Controller -> Components.
Todo campo nao conhecido aceita o literal UNKNOWN. UNKNOWN e melhor que inventar.
Nada especifico da GTEX vive em codigo: tudo vem de config/equipment/*.yaml.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from forja.domain.evidence import UNKNOWN, KnowledgeState

DriverName = Literal["simulator", "modbus_tcp", "ethernet_ip"]


class ComponentType(StrEnum):
    KCM = "KCM"
    MDU = "MDU"
    SCALE = "Scale"
    SFT = "SFT"
    ENCODER = "Encoder"
    SIB = "SIB"
    MOTOR = "Motor"
    ANYBUS = "Anybus"
    OTHER = "Other"


class Component(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ComponentType
    model: str = UNKNOWN
    serial: str = UNKNOWN
    quantity: int | None = None
    evidence: KnowledgeState = KnowledgeState.UNKNOWN
    note_pt: str = ""


class ControllerInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manufacturer: str = UNKNOWN
    model: str = UNKNOWN
    software_version: str = UNKNOWN
    kgr: str = UNKNOWN
    host_file: str = UNKNOWN


class HostInterface(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str = UNKNOWN
    slot: str = UNKNOWN
    model: str = UNKNOWN
    part_number: str = UNKNOWN
    mac: str = UNKNOWN
    evidence: KnowledgeState = KnowledgeState.UNKNOWN


class CommunicationConfig(BaseModel):
    """Configuracao de comunicacao. Enderecos industriais nunca sao defaults do codigo."""

    model_config = ConfigDict(extra="forbid")

    driver: DriverName = "simulator"
    protocol: str = UNKNOWN
    ip: str = UNKNOWN
    subnet: str = UNKNOWN
    gateway: str = UNKNOWN
    port: int | str = UNKNOWN
    unit_id: int | str = UNKNOWN
    poll_interval_s: float = Field(default=1.0, ge=0.25, le=3600)
    timeout_s: float = Field(default=2.0, gt=0, le=60)
    connect_timeout_s: float = Field(default=3.0, gt=0, le=60)
    stale_after_s: float = Field(default=5.0, gt=0)
    max_block_size: int | str = UNKNOWN
    options: dict[str, Any] = Field(default_factory=dict)
    """Opcoes especificas do driver (ex.: simulador: scenario, seed, time_scale)."""

    @property
    def needs_configuration(self) -> bool:
        """Driver real sem IP ou protocolo e NEEDS_CONFIGURATION."""
        if self.driver == "simulator":
            return False
        return self.ip == UNKNOWN or self.protocol == UNKNOWN


class EquipmentProfile(BaseModel):
    """Perfil configuravel de um equipamento (spec §14)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9_]{1,63}$")
    name: str
    plant: str = UNKNOWN
    area: str = UNKNOWN
    line: str = UNKNOWN
    application: str = UNKNOWN
    """WBF, LWF ou UNKNOWN. Nunca misturar logica de LWF em WBF."""
    application_evidence: KnowledgeState = KnowledgeState.UNKNOWN
    controller: ControllerInfo = Field(default_factory=ControllerInfo)
    host_interface: HostInterface = Field(default_factory=HostInterface)
    communication: CommunicationConfig = Field(default_factory=CommunicationConfig)
    mapping_profile: str
    components: list[Component] = Field(default_factory=list)
    is_example: bool = False
    """True para perfis de exemplo/demo (Barrilha, KCM 03...). Nunca confundir com planta real."""
    reference_values: dict[str, float] = Field(default_factory=dict)
    """Referencias visuais do simulador/UX (ex.: rpm_ref, belt_load_ref). Nunca limites do KCM."""
    notes_pt: str = ""

    @field_validator("application")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    @property
    def is_simulated(self) -> bool:
        return self.communication.driver == "simulator"

    @property
    def display_path(self) -> str:
        parts = [p for p in (self.plant, self.area, self.line) if p != UNKNOWN]
        return " — ".join([*parts, self.name])


class Plant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    timezone: str = "America/Sao_Paulo"
    areas: list[Area] = Field(default_factory=list)


class Area(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    lines: list[Line] = Field(default_factory=list)


class Line(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    equipment_ids: list[str] = Field(default_factory=list)


Plant.model_rebuild()
Area.model_rebuild()
