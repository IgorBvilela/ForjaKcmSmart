"""Teste somente leitura (botão TESTAR SOMENTE LEITURA, spec §16).

Cria um driver descartável, percorre os estágios ReadTestStage e devolve o que leu.
Nunca escreve: o driver só tem connect/disconnect/read/health/capabilities.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from forja.acquisition.loop import AcquisitionPipeline, DriverRegistryPort
from forja.acquisition.state import NEEDS_FIELD_CONFIG_PT, reason_pt_for
from forja.domain import (
    Clock,
    DriverConnectError,
    DriverReadError,
    DriverTimeout,
    EquipmentProfile,
    Mapping,
    NotConfigured,
    ReadTestStage,
    Sample,
)

logger = logging.getLogger(__name__)


class ReadTestResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    stages: list[tuple[ReadTestStage, datetime, str]]
    final: ReadTestStage
    values: dict[str, Sample]
    latency_ms: float | None
    error_pt: str | None

    @property
    def ok(self) -> bool:
        return self.final.is_success


def _final_stage_for(exc: BaseException) -> ReadTestStage:
    if isinstance(exc, DriverTimeout):
        return ReadTestStage.TIMEOUT
    if isinstance(exc, DriverConnectError):
        return ReadTestStage.CONNECTION_REFUSED
    if isinstance(exc, DriverReadError | ValueError):
        return ReadTestStage.INVALID_RESPONSE
    return ReadTestStage.UNIDENTIFIED


async def run_read_test(
    profile: EquipmentProfile,
    mapping: Mapping,
    *,
    registry: DriverRegistryPort,
    pipeline: AcquisitionPipeline,
    clock: Clock,
) -> ReadTestResult:
    """Executa o teste. UnsupportedDriver e NotConfigured propagam: não são resultado de leitura."""
    if profile.communication.needs_configuration:
        raise NotConfigured(f"{NEEDS_FIELD_CONFIG_PT}: IP ou protocolo não definidos")
    driver = registry.create(profile, mapping, clock)

    stages: list[tuple[ReadTestStage, datetime, str]] = []

    def mark(stage: ReadTestStage, text_pt: str) -> None:
        stages.append((stage, clock.now_utc(), text_pt))

    values: dict[str, Sample] = {}
    latency_ms: float | None = None
    error_pt: str | None = None
    final: ReadTestStage
    mark(ReadTestStage.CONNECTING, "Conectando ao equipamento")
    try:
        await driver.connect()
        mark(ReadTestStage.HANDSHAKE, "Conexão aceita; verificando o estado do driver")
        health = await driver.health()
        if not health.connected:
            raise DriverConnectError(health.detail_pt or "driver não reportou conexão")
        mark(ReadTestStage.SESSION_CREATED, "Sessão criada")
        plan = pipeline.compiler.compile(profile, mapping)
        t0 = clock.monotonic_ns()
        frame = await driver.read(plan)
        measured_ms = (clock.monotonic_ns() - t0) / 1_000_000
        batch = pipeline.normalizer.normalize(frame, profile, mapping, clock)
        latency_ms = frame.latency_ms if frame.latency_ms is not None else measured_ms
        values = {s.tag: s for s in batch.samples}
        final = ReadTestStage.READ_OBTAINED
        mark(final, f"Leitura obtida: {len(values)} variáveis")
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        final = _final_stage_for(exc)
        error_pt = f"{final.label_pt}: {reason_pt_for(exc)}"
        mark(final, error_pt)
        logger.info("test_read %s: %s (%s)", profile.id, error_pt, type(exc).__name__)
    finally:
        try:
            await driver.disconnect()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("test_read %s: disconnect falhou (ignorado)", profile.id)
    return ReadTestResult(
        stages=stages, final=final, values=values, latency_ms=latency_ms, error_pt=error_pt
    )
