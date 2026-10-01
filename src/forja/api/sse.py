"""Hub de Server-Sent Events.

Assina o bus do container e distribui para os clientes conectados:
- `snapshot`: planta + live de todos (ou do equipamento filtrado) ao conectar;
- `sample`: lote de amostras, coalescido a <= 2 Hz por equipamento (fica sempre o mais novo);
- `event`: transição de evento ou diagnóstico publicado;
- `status`: mudança de conexão;
- `heartbeat`: a cada 5 s pelo relógio do container (testável com FakeClock).

Ids são sequenciais. Um buffer de 60 s permite retomar com `Last-Event-ID`; sem continuidade
possível, o cliente recebe um snapshot novo. Nada aqui inicia aquisição.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections import deque
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any

from sse_starlette import ServerSentEvent

from forja.api.deps import jsonable, uptime_s
from forja.api.routers.equipments import build_live_view, status_view
from forja.api.routers.events import event_view
from forja.api.routers.plant import build_plant_cards
from forja.domain import (
    TOPIC_CONNECTION,
    TOPIC_DIAGNOSES,
    TOPIC_EVENTS,
    TOPIC_SAMPLES,
    Diagnosis,
    Event,
    EventTransition,
    SampleBatch,
)

logger = logging.getLogger("forja.api.sse")

EVENT_SNAPSHOT = "snapshot"
EVENT_SAMPLE = "sample"
EVENT_EVENT = "event"
EVENT_STATUS = "status"
EVENT_HEARTBEAT = "heartbeat"


def _dumps(payload: Any) -> str:
    return json.dumps(jsonable(payload), ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True)
class StreamEvent:
    """Evento já serializado, pronto para qualquer cliente."""

    id: int
    name: str
    data: str
    equipment_id: str | None
    mono_ns: int

    def matches(self, equipment_id: str | None) -> bool:
        return (
            equipment_id is None or self.equipment_id is None or self.equipment_id == equipment_id
        )

    def to_sse(self) -> ServerSentEvent:
        return ServerSentEvent(data=self.data, event=self.name, id=str(self.id))


def _equipment_of(payload: Any) -> str | None:
    if isinstance(payload, Mapping):
        value = payload.get("equipment_id")
    else:
        value = getattr(payload, "equipment_id", None)
    return str(value) if value is not None else None


def sample_payload(batch: SampleBatch) -> dict[str, Any]:
    """Lote compacto: valor e qualidade por tag."""
    return {
        "equipment_id": batch.equipment_id,
        "ts_utc": batch.ts_utc,
        "quality": batch.quality,
        "quality_pt": batch.quality.label_pt,
        "latency_ms": batch.latency_ms,
        "tags": {
            s.tag: {
                "value": s.value,
                "quality": s.quality,
                "ts_utc": s.ts_utc,
                "reason_pt": s.reason_pt,
            }
            for s in batch.samples
        },
    }


def event_payload(payload: Any) -> dict[str, Any]:
    """Transição de evento, evento solto ou diagnóstico vindos do bus."""
    # INTEGRACAO: blocos 3/4 publicam EventTransition em TOPIC_EVENTS e Diagnosis em
    # TOPIC_DIAGNOSES.
    if isinstance(payload, EventTransition):
        return {"kind": payload.kind, "event": event_view(payload.event, include_samples=False)}
    if isinstance(payload, Event):
        return {"kind": "EVENT", "event": event_view(payload, include_samples=False)}
    if isinstance(payload, Diagnosis):
        return {
            "kind": "DIAGNOSIS",
            "event_id": payload.event_id,
            "equipment_id": payload.equipment_id,
            "diagnosis_id": payload.diagnosis_id,
            "summary": payload.summary,
        }
    return {"kind": "UNKNOWN", "payload": payload}


class StreamHub:
    """Fan-out do bus para clientes SSE, com coalescência, heartbeat e buffer de retomada."""

    def __init__(
        self,
        container: Any,
        *,
        heartbeat_s: float = 5.0,
        buffer_s: float = 60.0,
        max_rate_hz: float = 2.0,
        client_queue_size: int = 512,
    ) -> None:
        self._container = container
        self._clock = container.clock
        self._bus = container.bus
        self._heartbeat_s = heartbeat_s
        self._buffer_ns = int(buffer_s * 1e9)
        self._min_gap_ns = int(1e9 / max_rate_hz)
        self._queue_size = client_queue_size
        self._seq = 0
        self._buffer: deque[StreamEvent] = deque()
        self._clients: set[asyncio.Queue[StreamEvent]] = set()
        self._tasks: list[asyncio.Task[None]] = []
        self._pending: dict[str, SampleBatch] = {}
        self._last_emit_ns: dict[str, int] = {}
        self._flush_tasks: dict[str, asyncio.Task[None]] = {}
        self._started = False
        self.dropped = 0

    # ---- ciclo de vida -------------------------------------------------------------------

    @property
    def last_id(self) -> int:
        return self._seq

    @property
    def client_count(self) -> int:
        return len(self._clients)

    @property
    def buffered(self) -> int:
        return len(self._buffer)

    def ensure_started(self) -> None:
        """Cria as tasks de assinatura e heartbeat uma única vez, no loop corrente."""
        if self._started:
            return
        self._started = True
        self._tasks = [
            asyncio.create_task(self._pump_samples(), name="sse-samples"),
            asyncio.create_task(self._pump(TOPIC_EVENTS, EVENT_EVENT), name="sse-events"),
            asyncio.create_task(self._pump(TOPIC_DIAGNOSES, EVENT_EVENT), name="sse-diagnoses"),
            asyncio.create_task(self._pump(TOPIC_CONNECTION, EVENT_STATUS), name="sse-status"),
            asyncio.create_task(self._heartbeat(), name="sse-heartbeat"),
        ]

    async def stop(self) -> None:
        """Cancela tasks e esquece clientes. Idempotente."""
        tasks = [*self._tasks, *self._flush_tasks.values()]
        self._tasks = []
        self._flush_tasks = {}
        self._pending = {}
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._clients.clear()
        self._started = False

    # ---- publicação ----------------------------------------------------------------------

    def publish(self, name: str, payload: Any, equipment_id: str | None) -> StreamEvent:
        """Atribui id, guarda no buffer e entrega a todos os clientes."""
        self._seq += 1
        event = StreamEvent(
            id=self._seq,
            name=name,
            data=_dumps(payload),
            equipment_id=equipment_id,
            mono_ns=self._clock.monotonic_ns(),
        )
        self._buffer.append(event)
        self._prune(event.mono_ns)
        for queue in list(self._clients):
            if queue.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                    self.dropped += 1
            queue.put_nowait(event)
        return event

    def _prune(self, now_ns: int) -> None:
        while self._buffer and now_ns - self._buffer[0].mono_ns > self._buffer_ns:
            self._buffer.popleft()

    def offer_sample(self, batch: SampleBatch) -> None:
        """Coalescência: no máximo um `sample` por equipamento a cada 1/max_rate_hz."""
        equipment_id = batch.equipment_id
        now = self._clock.monotonic_ns()
        last = self._last_emit_ns.get(equipment_id)
        if last is None or now - last >= self._min_gap_ns:
            self._emit_sample(batch, now)
            return
        self._pending[equipment_id] = batch
        if equipment_id not in self._flush_tasks:
            delay_s = (last + self._min_gap_ns - now) / 1e9
            self._flush_tasks[equipment_id] = asyncio.create_task(
                self._flush_later(equipment_id, delay_s), name=f"sse-flush-{equipment_id}"
            )

    async def _flush_later(self, equipment_id: str, delay_s: float) -> None:
        try:
            await self._clock.sleep(delay_s)
        finally:
            self._flush_tasks.pop(equipment_id, None)
        batch = self._pending.pop(equipment_id, None)
        if batch is not None:
            self._emit_sample(batch, self._clock.monotonic_ns())

    def _emit_sample(self, batch: SampleBatch, now_ns: int) -> None:
        self._last_emit_ns[batch.equipment_id] = now_ns
        self.publish(EVENT_SAMPLE, sample_payload(batch), batch.equipment_id)

    # ---- tasks de fundo ------------------------------------------------------------------

    async def _pump_samples(self) -> None:
        async for payload in self._bus.subscribe(TOPIC_SAMPLES):
            if isinstance(payload, SampleBatch):
                self.offer_sample(payload)

    async def _pump(self, topic: str, name: str) -> None:
        async for payload in self._bus.subscribe(topic):
            try:
                self.publish(name, self._payload_for(name, payload), _equipment_of(payload))
            except Exception:
                logger.exception("falha ao serializar payload do tópico %s", topic)

    def _payload_for(self, name: str, payload: Any) -> Any:
        if name == EVENT_EVENT:
            return event_payload(payload)
        if name == EVENT_STATUS:
            equipment_id = _equipment_of(payload)
            status = None
            if equipment_id is not None:
                with contextlib.suppress(Exception):
                    status = status_view(self._container.manager.status(equipment_id))
            return {"equipment_id": equipment_id, "change": payload, "status": status}
        return payload

    async def _heartbeat(self) -> None:
        while True:
            await self._clock.sleep(self._heartbeat_s)
            self.publish(
                EVENT_HEARTBEAT,
                {
                    "ts_utc": self._clock.now_utc(),
                    "uptime_s": uptime_s(self._container),
                    "clients": len(self._clients),
                },
                None,
            )

    # ---- snapshot e retomada -------------------------------------------------------------

    async def snapshot(self, equipment_id: str | None) -> dict[str, Any]:
        """Planta + live. Com filtro, só o equipamento pedido."""
        profiles = self._container.store.profiles
        cards = await build_plant_cards(self._container)
        if equipment_id is not None:
            cards = [c for c in cards if c["id"] == equipment_id]
            selected = [profiles[equipment_id]] if equipment_id in profiles else []
        else:
            selected = list(profiles.values())
        return {
            "ts_utc": self._clock.now_utc(),
            "last_id": self._seq,
            "plant": cards,
            "live": {p.id: build_live_view(self._container, p) for p in selected},
        }

    def replay_plan(self, last_event_id: str | None) -> list[StreamEvent] | None:
        """Eventos a reenviar após `last_event_id`; None quando é preciso um snapshot."""
        if last_event_id is None:
            return None
        try:
            last = int(last_event_id)
        except ValueError:
            return None
        if last < 0 or last > self._seq:
            return None
        if last == self._seq:
            return []
        if not self._buffer or self._buffer[0].id > last + 1:
            return None
        return [ev for ev in self._buffer if ev.id > last]

    async def stream(
        self, equipment_id: str | None, last_event_id: str | None
    ) -> AsyncIterator[ServerSentEvent]:
        """Gerador por cliente: snapshot (ou retomada) e depois tudo que chegar."""
        self.ensure_started()
        queue: asyncio.Queue[StreamEvent] = asyncio.Queue(maxsize=self._queue_size)
        self._clients.add(queue)
        try:
            replay = self.replay_plan(last_event_id)
            if replay is None:
                snapshot_id = self._seq
                snapshot = await self.snapshot(equipment_id)
                yield ServerSentEvent(
                    data=_dumps(snapshot), event=EVENT_SNAPSHOT, id=str(snapshot_id)
                )
            else:
                for ev in replay:
                    if ev.matches(equipment_id):
                        yield ev.to_sse()
            while True:
                ev = await queue.get()
                if ev.matches(equipment_id):
                    yield ev.to_sse()
        finally:
            self._clients.discard(queue)
