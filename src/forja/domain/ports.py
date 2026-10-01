"""Portas (interfaces) do dominio. Tudo que fala com o mundo externo implementa uma destas.

REGRA INEGOCIAVEL: a porta de driver NAO tem write(). Nenhum metodo que altere o KCM existe aqui,
e ReadOnlyDriverBase recusa, na definicao da classe, qualquer subclasse que tente adicionar um.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from forja.domain.errors import ReadOnlyContractViolation
from forja.domain.events import Event
from forja.domain.quality import Quality
from forja.domain.samples import RawFrame, ReadPlan, Sample

FORBIDDEN_DRIVER_METHOD = re.compile(
    r"^(write|set_|reset|start|stop|command|force|preset|tare|span|calib|apply|save|restore"
    r"|create|delete|run|enable|disable|output|produce|send_command)",
    re.IGNORECASE,
)
ALLOWED_DRIVER_PUBLIC = frozenset({"name", "connect", "disconnect", "read", "health", "capabilities"})


class DriverSupportState(str, Enum):
    AVAILABLE = "AVAILABLE"
    EXPERIMENTAL = "EXPERIMENTAL"
    NEEDS_CONFIGURATION = "NEEDS_CONFIGURATION"
    UNSUPPORTED = "UNSUPPORTED"

    @property
    def label_pt(self) -> str:
        return {
            DriverSupportState.AVAILABLE: "Disponível",
            DriverSupportState.EXPERIMENTAL: "Experimental",
            DriverSupportState.NEEDS_CONFIGURATION: "Requer configuração",
            DriverSupportState.UNSUPPORTED: "Não suportado",
        }[self]


class DriverHealth(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    connected: bool
    last_ok_utc: datetime | None = None
    latency_ms: float | None = None
    consecutive_errors: int = 0
    detail_pt: str = ""


class DriverCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    protocol: str
    support_state: DriverSupportState
    library: str = ""
    library_version: str = ""
    read_areas: tuple[str, ...] = ()
    max_block_size: int | None = None
    supports_device_identification: bool = False
    note_pt: str = ""


@runtime_checkable
class ReadOnlyDriver(Protocol):
    """Contrato conceitual: connect, disconnect, read, health, capabilities. SEM WRITE."""

    name: str

    async def connect(self) -> None: ...

    async def disconnect(self) -> None: ...

    async def read(self, plan: ReadPlan) -> RawFrame: ...

    async def health(self) -> DriverHealth: ...

    def capabilities(self) -> DriverCapabilities: ...


class ReadOnlyDriverBase(ABC):
    """Base concreta para drivers. Recusa subclasses com metodos de escrita na definicao."""

    name: str = "abstract"

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        for attr in list(vars(cls)):
            if attr.startswith("_"):
                continue
            if attr not in ALLOWED_DRIVER_PUBLIC or FORBIDDEN_DRIVER_METHOD.match(attr):
                raise ReadOnlyContractViolation(
                    f"{cls.__name__}.{attr}: driver só pode expor "
                    f"{sorted(ALLOWED_DRIVER_PUBLIC)}; read-only é requisito estrutural"
                )

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def read(self, plan: ReadPlan) -> RawFrame: ...

    @abstractmethod
    async def health(self) -> DriverHealth: ...

    @abstractmethod
    def capabilities(self) -> DriverCapabilities: ...


class SeriesPoint(BaseModel):
    """Ponto de serie para graficos. value None = GAP (nunca interpolar)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ts_utc: datetime
    value: float | None
    quality: Quality
    min: float | None = None
    max: float | None = None
    n: int = 1


class Series(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    equipment_id: str
    tag: str
    resolution: str
    """raw | 1m | 1h | <N>s (re-bucket)."""
    bucket_s: int
    points: tuple[SeriesPoint, ...]
    gap_count: int = 0
    stale_count: int = 0
    downsampled: bool = False


class CommLogEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ts_utc: datetime
    equipment_id: str
    level: str
    kind: str
    message_pt: str
    detail: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class HistorianRepository(Protocol):
    async def write(self, samples: Sequence[Sample]) -> None: ...

    async def latest(self, equipment_id: str, tags: Sequence[str] | None = None) -> dict[str, Sample]: ...

    async def range(
        self,
        equipment_id: str,
        tag: str,
        start: datetime,
        end: datetime,
        max_points: int = 2000,
    ) -> Series: ...

    async def count(self, equipment_id: str | None = None) -> int: ...

    async def log_comm(self, entry: CommLogEntry) -> None: ...

    async def comm_log(
        self, equipment_id: str | None, since: datetime | None, limit: int = 200
    ) -> list[CommLogEntry]: ...


@runtime_checkable
class EventRepository(Protocol):
    async def save(self, event: Event) -> None: ...

    async def get(self, event_id: str) -> Event | None: ...

    async def list(
        self,
        equipment_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        open_only: bool = False,
        limit: int = 200,
    ) -> list[Event]: ...

    async def find_open(self, equipment_id: str, dedupe_key: str) -> Event | None: ...


@runtime_checkable
class DiagnosisRepository(Protocol):
    async def save(self, diagnosis: Any) -> None: ...

    async def get_for_event(self, event_id: str) -> Any | None: ...

    async def list(self, equipment_id: str | None = None, limit: int = 100) -> list[Any]: ...


@runtime_checkable
class Clock(Protocol):
    def now_utc(self) -> datetime: ...

    def monotonic_ns(self) -> int: ...

    async def sleep(self, seconds: float) -> None: ...


@runtime_checkable
class EventBus(Protocol):
    async def publish(self, topic: str, payload: Any) -> None: ...

    def subscribe(self, topic: str) -> AsyncIterator[Any]: ...


TOPIC_SAMPLES = "samples"
TOPIC_CONNECTION = "connection"
TOPIC_EVENTS = "events"
TOPIC_DIAGNOSES = "diagnoses"
