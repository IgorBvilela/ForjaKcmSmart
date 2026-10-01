"""Container do serviço: tudo que o runner monta e a API consome."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol

from forja.acquisition.loop import DriverRegistryPort
from forja.acquisition.manager import EquipmentManager
from forja.config import ConfigStore, ForjaPaths
from forja.domain import (
    Clock,
    Diagnosis,
    DiagnosisRepository,
    Event,
    EventRepository,
    EventTransition,
    HistorianRepository,
    SampleBatch,
)
from forja.infra import AsyncBus

if TYPE_CHECKING:
    from forja.service.runner import EngineBridge, PeriodicJobs


class RuleEnginePort(Protocol):
    """O que o serviço precisa do RuleEngine do Bloco 4."""

    async def on_batch(self, batch: SampleBatch) -> list[EventTransition]: ...


class DiagnosisEnginePort(Protocol):
    """O que o serviço precisa do DiagnosisEngine do Bloco 4."""

    def diagnose(self, event: Event) -> Diagnosis: ...


@dataclass
class ServiceRuntime:
    """Tasks e objetos vivos criados por start(); fechados por stop()."""

    bridge: EngineBridge | None = None
    jobs: PeriodicJobs | None = None
    tasks: list[asyncio.Task[None]] = field(default_factory=list)
    closeables: list[Any] = field(default_factory=list)
    started: bool = False


@dataclass
class Container:
    paths: ForjaPaths
    store: ConfigStore
    clock: Clock
    bus: AsyncBus
    registry: DriverRegistryPort
    historian: HistorianRepository
    events_repo: EventRepository
    diagnoses_repo: DiagnosisRepository
    manager: EquipmentManager
    rule_engine: RuleEnginePort
    diagnosis_engine: DiagnosisEnginePort
    started_at_utc: datetime
    runtime: ServiceRuntime = field(default_factory=ServiceRuntime)

    @property
    def uptime_s(self) -> float:
        return max(0.0, (self.clock.now_utc() - self.started_at_utc).total_seconds())
