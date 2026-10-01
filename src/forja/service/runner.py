"""Runner do serviço: monta o Container, liga os motores ao bus, roda jobs periódicos.

build_container importa os módulos dos outros blocos tarde (dentro da função) para os testes
unitários deste bloco não dependerem deles. start/stop são graciosos: parar loops, flush,
fechar bancos, tudo dentro de um timeout.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from forja.acquisition.manager import EquipmentManager
from forja.config import ConfigStore, ForjaPaths, resolve_paths
from forja.domain import (
    TOPIC_DIAGNOSES,
    TOPIC_EVENTS,
    TOPIC_SAMPLES,
    Clock,
    DiagnosisRepository,
    Event,
    EventBus,
    EventRepository,
    EventTransition,
    SampleBatch,
)
from forja.infra import AsyncBus, SystemClock
from forja.service.container import Container, DiagnosisEnginePort, RuleEnginePort

logger = logging.getLogger(__name__)

ROLLUP_EVERY_S = 60.0
RETENTION_EVERY_S = 3600.0


class EngineBridge:
    """Liga TOPIC_SAMPLES ao RuleEngine e o OPEN ao DiagnosisEngine.

    Para cada SampleBatch: on_batch -> salva cada transição -> publica em TOPIC_EVENTS;
    para OPEN: diagnose -> salva -> publica em TOPIC_DIAGNOSES. Erro nunca derruba a task.
    """

    def __init__(
        self,
        bus: EventBus,
        rule_engine: RuleEnginePort,
        diagnosis_engine: DiagnosisEnginePort,
        events_repo: EventRepository,
        diagnoses_repo: DiagnosisRepository,
    ) -> None:
        self._bus = bus
        self._rules = rule_engine
        self._diagnosis = diagnosis_engine
        self._events = events_repo
        self._diagnoses = diagnoses_repo
        self._stream: AsyncIterator[Any] | None = None
        self.batches = 0
        self.transitions = 0
        self.diagnoses = 0
        self.errors = 0

    def attach(self) -> None:
        """Assina TOPIC_SAMPLES agora, antes dos loops começarem, para não perder lote."""
        if self._stream is None:
            self._stream = self._bus.subscribe(TOPIC_SAMPLES)

    async def run(self) -> None:
        self.attach()
        assert self._stream is not None
        async for payload in self._stream:
            if isinstance(payload, SampleBatch):
                await self.handle(payload)

    async def handle(self, batch: SampleBatch) -> list[EventTransition]:
        self.batches += 1
        try:
            transitions = await self._rules.on_batch(batch)
        except asyncio.CancelledError:
            raise
        except Exception:
            self.errors += 1
            logger.exception("motor de regras falhou no lote de %s", batch.equipment_id)
            return []
        done: list[EventTransition] = []
        for t in transitions:
            try:
                await self._events.save(t.event)
                await self._bus.publish(TOPIC_EVENTS, t)
                if t.kind == "OPEN":
                    await self._diagnose(t.event)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.errors += 1
                logger.exception("falha ao processar transição %s de %s", t.kind, t.event.id)
                continue
            self.transitions += 1
            done.append(t)
        return done

    async def _diagnose(self, event: Event) -> None:
        diagnosis = self._diagnosis.diagnose(event)
        await self._diagnoses.save(diagnosis)
        await self._bus.publish(TOPIC_DIAGNOSES, diagnosis)
        self.diagnoses += 1


class PeriodicJobs:
    """Rollups a cada 60 s e retenção a cada 3600 s, dormindo pelo Clock."""

    def __init__(
        self,
        historian: Any,
        clock: Clock,
        *,
        rollup_every_s: float = ROLLUP_EVERY_S,
        retention_every_s: float = RETENTION_EVERY_S,
    ) -> None:
        self._historian = historian
        self._clock = clock
        self.rollup_every_s = rollup_every_s
        self.retention_every_s = retention_every_s
        self.runs: dict[str, int] = {"run_rollups": 0, "run_retention": 0}
        self.errors: dict[str, int] = {"run_rollups": 0, "run_retention": 0}
        self.last_result: dict[str, Any] = {}

    async def run_rollups_forever(self) -> None:
        await self._forever("run_rollups", self.rollup_every_s)

    async def run_retention_forever(self) -> None:
        await self._forever("run_retention", self.retention_every_s)

    async def run_once(self, name: str) -> Any:
        fn = getattr(self._historian, name, None)
        if fn is None:
            return None
        try:
            result = await fn()
        except asyncio.CancelledError:
            raise
        except Exception:
            self.errors[name] += 1
            logger.exception("job %s falhou", name)
            return None
        self.runs[name] += 1
        self.last_result[name] = result
        return result

    async def _forever(self, name: str, every_s: float) -> None:
        if getattr(self._historian, name, None) is None:
            logger.info("historian sem %s; job desligado", name)
            return
        while True:
            await self._clock.sleep(every_s)
            await self.run_once(name)

    def start_tasks(self) -> list[asyncio.Task[None]]:
        return [
            asyncio.create_task(self.run_rollups_forever(), name="forja-job-rollups"),
            asyncio.create_task(self.run_retention_forever(), name="forja-job-retention"),
        ]


async def build_container(paths: ForjaPaths | None = None, clock: Clock | None = None) -> Container:
    """Monta tudo. Importa Blocos 1, 2 e 4 aqui dentro (import tardio, de propósito)."""
    from forja.diagnostics.engine import DiagnosisEngine
    from forja.diagnostics.library import load_library
    from forja.drivers.registry import build_default_registry
    from forja.events.engine import RuleEngine
    from forja.events.rules import load_rules
    from forja.historian.core_store import SqliteCoreStore
    from forja.historian.sqlite import SqliteHistorian

    paths = (paths or resolve_paths()).ensure()
    clock = clock or SystemClock()
    store = ConfigStore(paths).load_all()
    bus = AsyncBus()

    historian = SqliteHistorian(paths.historian_db, store.config.historian, clock)
    await historian.open()
    core = SqliteCoreStore(paths.core_db, clock)
    await core.open()
    # EventRepository e DiagnosisRepository têm `list` com assinaturas diferentes; uma classe só
    # não cabe nas duas portas. O core store expõe uma view por porta: usamos as views.
    events_repo = core.events
    diagnoses_repo = core.diagnoses

    registry = build_default_registry()
    ev = store.config.events
    rule_engine = RuleEngine(
        load_rules(paths.rules_dir),
        store.alarms,
        store.stop_by,
        clock,
        ev.pre_window_s,
        ev.post_window_s,
        ev.buffer_s,
        profiles=store.profiles,
        timezone=store.config.edge.timezone,
    )
    diagnosis_engine = DiagnosisEngine(
        load_library(paths.knowledge_dir / "diagnostics"),
        clock,
        timezone=store.config.edge.timezone,
    )
    manager = EquipmentManager(store, registry, historian, bus, clock)

    container = Container(
        paths=paths,
        store=store,
        clock=clock,
        bus=bus,
        registry=registry,
        historian=historian,
        events_repo=events_repo,
        diagnoses_repo=diagnoses_repo,
        manager=manager,
        rule_engine=rule_engine,
        diagnosis_engine=diagnosis_engine,
        started_at_utc=clock.now_utc(),
    )
    container.runtime.closeables = [historian, core]
    container.runtime.bridge = EngineBridge(
        bus, rule_engine, diagnosis_engine, events_repo, diagnoses_repo
    )
    container.runtime.jobs = PeriodicJobs(historian, clock)
    return container


async def start(container: Container) -> None:
    """Assina o bus, sobe jobs e inicia a aquisição de todos os equipamentos."""
    rt = container.runtime
    if rt.started:
        return
    if rt.bridge is None:
        rt.bridge = EngineBridge(
            container.bus,
            container.rule_engine,
            container.diagnosis_engine,
            container.events_repo,
            container.diagnoses_repo,
        )
    rt.bridge.attach()
    rt.tasks.append(asyncio.create_task(rt.bridge.run(), name="forja-engine-bridge"))
    if rt.jobs is None:
        rt.jobs = PeriodicJobs(container.historian, container.clock)
    rt.tasks.extend(rt.jobs.start_tasks())
    await container.manager.start_all()
    rt.started = True
    logger.info("serviço iniciado com %d equipamento(s)", len(container.store.profiles))


async def stop(container: Container, timeout_s: float = 10) -> None:
    """Parada graciosa: loops, tasks auxiliares, flush e fechamento dos bancos."""
    rt = container.runtime
    await container.manager.stop_all(timeout_s=timeout_s)
    tasks = [t for t in rt.tasks if not t.done()]
    for t in tasks:
        t.cancel()
    if tasks:
        _, pending = await asyncio.wait(set(tasks), timeout=timeout_s)
        for t in pending:
            logger.warning("serviço: task %s não parou em %.1f s", t.get_name(), timeout_s)
    rt.tasks.clear()
    await _close_all(_closeables(container))
    rt.started = False
    logger.info("serviço parado")


def _closeables(container: Container) -> list[Any]:
    seen: set[int] = set()
    out: list[Any] = []
    for obj in (
        *container.runtime.closeables,
        container.historian,
        container.events_repo,
        container.diagnoses_repo,
    ):
        if id(obj) in seen:
            continue
        seen.add(id(obj))
        out.append(obj)
    return out


async def _close_all(objs: list[Any]) -> None:
    for obj in objs:
        for method in ("flush", "close"):
            fn = getattr(obj, method, None)
            if fn is None:
                continue
            try:
                await fn()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("serviço: %s.%s falhou", type(obj).__name__, method)
