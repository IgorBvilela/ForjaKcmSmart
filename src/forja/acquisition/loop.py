"""Loop de aquisição: uma task asyncio por equipamento.

connect -> a cada poll_interval_s: read(plan) -> Normalizer -> publish(TOPIC_SAMPLES) + historian.
Exceção de driver vira comm_error_batch + ConnectionState.ERROR + backoff. Nunca escapa.
O tempo vem só da porta Clock. O sono é fatiado em pedaços de poll_interval_s para o
watchdog enxergar tick mesmo durante um backoff longo.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from forja.acquisition.backoff import Backoff
from forja.acquisition.live import LiveState
from forja.acquisition.state import ConnectionChanged, EquipmentState, reason_pt_for
from forja.domain import (
    TOPIC_CONNECTION,
    TOPIC_SAMPLES,
    Clock,
    CommLogEntry,
    ConnectionState,
    EquipmentProfile,
    EventBus,
    HistorianRepository,
    Mapping,
    Quality,
    RawFrame,
    ReadOnlyDriverBase,
    ReadPlan,
    Sample,
    SampleBatch,
)

logger = logging.getLogger(__name__)

_NS = 1_000_000_000
_SLEEP_EPSILON_S = 1e-6
"""Resto de sono abaixo disto é descartado: evita um sleep infinitesimal que nunca acorda."""


class PlanCompiler(Protocol):
    def compile(self, profile: EquipmentProfile, mapping: Mapping) -> ReadPlan: ...


class FrameNormalizer(Protocol):
    def normalize(
        self, frame: RawFrame, profile: EquipmentProfile, mapping: Mapping, clock: Clock
    ) -> SampleBatch: ...


CommErrorFactory = Callable[[EquipmentProfile, Mapping, Clock, str], SampleBatch]


class DriverRegistryPort(Protocol):
    """O que a aquisição precisa do DriverRegistry do Bloco 1."""

    def create(
        self, profile: EquipmentProfile, mapping: Mapping, clock: Clock
    ) -> ReadOnlyDriverBase: ...

    def support(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class AcquisitionPipeline:
    """Compilador de plano, normalizador e fábrica de lote COMM_ERROR (Bloco 1)."""

    compiler: PlanCompiler
    normalizer: FrameNormalizer
    comm_error: CommErrorFactory


def default_pipeline() -> AcquisitionPipeline:
    """Pipeline real, importado tarde para o Bloco 3 testar sem o Bloco 1 pronto."""
    from forja.normalization.normalizer import Normalizer, comm_error_batch
    from forja.normalization.plan import ReadPlanCompiler

    return AcquisitionPipeline(
        compiler=ReadPlanCompiler(), normalizer=Normalizer(), comm_error=comm_error_batch
    )


def fallback_comm_error_batch(
    profile: EquipmentProfile, mapping: Mapping, clock: Clock, reason_pt: str
) -> SampleBatch:
    """Lote COMM_ERROR mínimo, usado se a fábrica do pipeline falhar."""
    now = clock.now_utc()
    mono = clock.monotonic_ns()
    samples = tuple(
        Sample(
            ts_utc=now,
            equipment_id=profile.id,
            tag=e.semantic_tag,
            value=None,
            quality=Quality.COMM_ERROR,
            source=mapping.source_label,
            ts_mono_ns=mono,
            reason_pt=reason_pt,
        )
        for e in mapping.readable_entries
    )
    return SampleBatch(
        equipment_id=profile.id, ts_utc=now, samples=samples, quality=Quality.COMM_ERROR
    )


class EquipmentLoop:
    """Corpo da task de um equipamento. Escreve em EquipmentState e LiveState; nunca lança."""

    def __init__(
        self,
        *,
        profile: EquipmentProfile,
        mapping: Mapping,
        driver: ReadOnlyDriverBase,
        pipeline: AcquisitionPipeline,
        historian: HistorianRepository,
        bus: EventBus,
        clock: Clock,
        state: EquipmentState,
        live: LiveState,
        backoff: Backoff | None = None,
    ) -> None:
        self._profile = profile
        self._mapping = mapping
        self._driver = driver
        self._pipeline = pipeline
        self._historian = historian
        self._bus = bus
        self._clock = clock
        self._state = state
        self._live = live
        self._backoff = backoff or Backoff()
        self._plan: ReadPlan | None = None
        self._connected = False
        self._connected_once = False
        self._stop_requested = False
        self._last_reason_pt = ""
        self.polls = 0
        self.failures = 0

    @property
    def equipment_id(self) -> str:
        return self._profile.id

    @property
    def poll_interval_s(self) -> float:
        return self._profile.communication.poll_interval_s

    @property
    def driver(self) -> ReadOnlyDriverBase:
        return self._driver

    def request_stop(self) -> None:
        self._stop_requested = True

    async def run(self) -> None:
        """Roda até request_stop() ou cancelamento. Exceção de driver nunca sai daqui."""
        try:
            while not self._stop_requested:
                self._tick()
                if self._plan is None and not await self._compile_plan():
                    await self._sleep_backoff()
                    continue
                if not self._connected and not await self._connect():
                    await self._sleep_backoff()
                    continue
                if await self._poll_once():
                    await self._sleep_ticking(self.poll_interval_s)
                else:
                    await self._sleep_backoff()
        finally:
            await self._shutdown()

    def _tick(self) -> None:
        self._state.tick(self._clock.monotonic_ns())

    async def _compile_plan(self) -> bool:
        try:
            self._plan = self._pipeline.compiler.compile(self._profile, self._mapping)
        except Exception as exc:
            await self._fail(exc)
            return False
        return True

    async def _connect(self) -> bool:
        target = (
            ConnectionState.RECONNECTING if self._connected_once else ConnectionState.CONNECTING
        )
        await self._set_connection(target, "")
        try:
            await self._driver.connect()
        except Exception as exc:
            await self._fail(exc)
            return False
        if self._connected_once:
            self._state.reconnect_count += 1
        self._connected = True
        self._connected_once = True
        await self._set_connection(ConnectionState.CONNECTED, "")
        return True

    async def _poll_once(self) -> bool:
        assert self._plan is not None
        t0 = self._clock.monotonic_ns()
        try:
            frame = await self._driver.read(self._plan)
            batch = self._pipeline.normalizer.normalize(
                frame, self._profile, self._mapping, self._clock
            )
        except Exception as exc:
            await self._fail(exc)
            return False
        self.polls += 1
        latency = batch.latency_ms
        if latency is None:
            latency = (self._clock.monotonic_ns() - t0) / 1_000_000
        self._state.latency_ms = latency
        self._state.consecutive_errors = 0
        self._state.last_ok_utc = batch.ts_utc
        self._state.record_ok(self._clock.monotonic_ns())
        self._backoff.reset()
        await self._deliver(batch)
        if self._state.connection is not ConnectionState.CONNECTED:
            await self._set_connection(ConnectionState.CONNECTED, "")
        return True

    async def _fail(self, exc: BaseException) -> None:
        """Caminho único de falha: lote COMM_ERROR, estado ERROR, desconecta, conta."""
        reason = reason_pt_for(exc)
        self._last_reason_pt = reason
        self.failures += 1
        self._state.consecutive_errors += 1
        n = self._state.consecutive_errors
        log = logger.warning if n == 1 or n % 60 == 0 else logger.debug
        log(
            "aquisição %s: %s (%s: %s) [falhas seguidas: %d]",
            self.equipment_id,
            reason,
            type(exc).__name__,
            exc,
            n,
        )
        await self._deliver(self._comm_error_batch(reason))
        await self._set_connection(ConnectionState.ERROR, reason, exc=exc)
        await self._disconnect_quietly()
        self._connected = False

    def _comm_error_batch(self, reason_pt: str) -> SampleBatch:
        try:
            return self._pipeline.comm_error(self._profile, self._mapping, self._clock, reason_pt)
        except Exception:
            logger.exception("aquisição %s: comm_error_batch do pipeline falhou", self.equipment_id)
            return fallback_comm_error_batch(self._profile, self._mapping, self._clock, reason_pt)

    async def _deliver(self, batch: SampleBatch) -> None:
        """Atualiza o estado ao vivo, publica no bus e grava no historian (STALE nunca entra)."""
        self._live.update(batch)
        self._state.last_read_utc = batch.ts_utc
        self._tick()
        try:
            await self._bus.publish(TOPIC_SAMPLES, batch)
        except Exception:
            logger.exception("aquisição %s: falha ao publicar lote", self.equipment_id)
        to_write = [s for s in batch.samples if s.quality is not Quality.STALE]
        if not to_write:
            return
        try:
            await self._historian.write(to_write)
        except Exception:
            self._state.historian_errors += 1
            logger.exception("aquisição %s: falha ao gravar no historian", self.equipment_id)

    async def _set_connection(
        self, new: ConnectionState, detail_pt: str, *, exc: BaseException | None = None
    ) -> None:
        previous = self._state.connection
        self._state.detail_pt = detail_pt
        if previous is new:
            return
        self._state.connection = new
        now = self._clock.now_utc()
        changed = ConnectionChanged(
            equipment_id=self.equipment_id,
            previous=previous,
            current=new,
            ts_utc=now,
            detail_pt=detail_pt,
            consecutive_errors=self._state.consecutive_errors,
            reconnect_count=self._state.reconnect_count,
        )
        try:
            await self._bus.publish(TOPIC_CONNECTION, changed)
        except Exception:
            logger.exception("aquisição %s: falha ao publicar conexão", self.equipment_id)
        await self._log_comm(previous, new, detail_pt, exc)

    async def _log_comm(
        self,
        previous: ConnectionState,
        new: ConnectionState,
        detail_pt: str,
        exc: BaseException | None,
    ) -> None:
        level = "WARNING" if new is ConnectionState.ERROR else "INFO"
        detail: dict[str, Any] = {"previous": previous.value, "current": new.value}
        if exc is not None:
            detail["exception"] = type(exc).__name__
            detail["message"] = str(exc)[:200]
        entry = CommLogEntry(
            ts_utc=self._clock.now_utc(),
            equipment_id=self.equipment_id,
            level=level,
            kind="connection",
            message_pt=f"{previous.label_pt} -> {new.label_pt}"
            + (f": {detail_pt}" if detail_pt else ""),
            detail=detail,
        )
        try:
            await self._historian.log_comm(entry)
        except Exception:
            logger.debug("aquisição %s: comm_log indisponível", self.equipment_id)

    async def _disconnect_quietly(self) -> None:
        try:
            await self._driver.disconnect()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("aquisição %s: disconnect falhou (ignorado)", self.equipment_id)

    async def _sleep_backoff(self) -> None:
        delay = self._backoff.next_delay()
        base = self._last_reason_pt or self._state.detail_pt
        self._state.detail_pt = f"{base}. Nova tentativa em {delay:.0f} s".lstrip(". ")
        await self._sleep_ticking(delay)

    async def _sleep_ticking(self, total_s: float) -> None:
        """Dorme total_s em fatias de poll_interval_s, marcando tick entre elas."""
        remaining = total_s
        while remaining > _SLEEP_EPSILON_S and not self._stop_requested:
            chunk = min(remaining, self.poll_interval_s)
            self._tick()
            await self._clock.sleep(chunk)
            remaining -= chunk

    async def _shutdown(self) -> None:
        self._connected = False
        await self._disconnect_quietly()
        await self._set_connection(ConnectionState.DISCONNECTED, "Aquisição parada")
