"""Fakes locais do Bloco 3 (aquisição e serviço).

Tudo aqui é determinístico e sem rede: drivers fake que devolvem RawFrame com payload dict,
drivers que levantam ou travam, registry fake, historian em memória, pipeline fake e helpers de
tempo que só avançam o FakeClock (nunca sleep real).
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from forja.config import ConfigStore, ForjaPaths
from forja.domain import (
    Clock,
    CommLogEntry,
    CommunicationConfig,
    DataType,
    DriverCapabilities,
    DriverConnectError,
    DriverHealth,
    DriverSupportState,
    DriverTimeout,
    Endianness,
    EquipmentProfile,
    KnowledgeState,
    Mapping,
    MappingEntry,
    Quality,
    RawBlock,
    RawFrame,
    ReadBlock,
    ReadOnlyDriverBase,
    ReadPlan,
    Sample,
    SampleBatch,
    Scale,
    Series,
    UnsupportedDriver,
    worst,
)
from forja.infra import AsyncBus, FakeClock

TAGS: tuple[str, ...] = ("mass_flow", "belt_load", "rpm")
SIM_BLOCK = "sim"


# --- configuração em memória -----------------------------------------------------------------


def make_paths(tmp: Path) -> ForjaPaths:
    paths = ForjaPaths(
        home=tmp,
        config_dir=tmp / "config",
        knowledge_dir=tmp / "knowledge",
        data_dir=tmp / "var",
        logs_dir=tmp / "var" / "logs",
        backups_dir=tmp / "var" / "backups",
    )
    paths.equipment_dir.mkdir(parents=True, exist_ok=True)
    paths.mappings_dir.mkdir(parents=True, exist_ok=True)
    return paths


def make_mapping(mapping_id: str = "fake_wbf", tags: Sequence[str] = TAGS) -> Mapping:
    return Mapping(
        mapping_id=mapping_id,
        version=1,
        equipment_id="*",
        driver="simulator",
        source="fake de teste",
        entries=[
            MappingEntry(
                semantic_tag=tag,
                protocol_address=f"sim:{tag}",
                datatype=DataType.FLOAT32,
                endianness=Endianness.BIG,
                scale=Scale(),
                source="fake de teste",
                evidence=KnowledgeState.FORJA_RULE,
            )
            for tag in tags
        ],
    )


def make_profile(
    equipment_id: str,
    *,
    mapping_id: str = "fake_wbf",
    poll_interval_s: float = 1.0,
    stale_after_s: float = 5.0,
    driver: str = "simulator",
    options: dict[str, Any] | None = None,
) -> EquipmentProfile:
    return EquipmentProfile(
        id=equipment_id,
        name=f"Equipamento {equipment_id}",
        mapping_profile=mapping_id,
        is_example=True,
        communication=CommunicationConfig(
            driver=driver,  # type: ignore[arg-type]
            poll_interval_s=poll_interval_s,
            stale_after_s=stale_after_s,
            options=options or {},
        ),
    )


def make_store(
    paths: ForjaPaths,
    profiles: Sequence[EquipmentProfile],
    mappings: Sequence[Mapping] | None = None,
) -> ConfigStore:
    store = ConfigStore(paths)
    store.profiles = {p.id: p for p in profiles}
    store.mappings = {m.mapping_id: m for m in (mappings or [make_mapping()])}
    return store


# --- drivers fake -----------------------------------------------------------------------------


@dataclass
class DriverLog:
    """Contadores fora do driver: a superfície pública do driver fica só com o contrato."""

    connects: int = 0
    disconnects: int = 0
    reads: int = 0
    failures: int = 0


class _FakeDriver(ReadOnlyDriverBase):
    name = "simulator"

    def __init__(self, equipment_id: str, clock: Clock, log: DriverLog | None = None) -> None:
        self._equipment_id = equipment_id
        self._clock = clock
        self._log = log or DriverLog()
        self._connected = False

    async def connect(self) -> None:
        self._log.connects += 1
        self._connected = True

    async def disconnect(self) -> None:
        self._log.disconnects += 1
        self._connected = False

    async def read(self, plan: ReadPlan) -> RawFrame:
        raise NotImplementedError

    async def health(self) -> DriverHealth:
        return DriverHealth(connected=self._connected, consecutive_errors=self._log.failures)

    def capabilities(self) -> DriverCapabilities:
        return DriverCapabilities(
            protocol="simulator",
            support_state=DriverSupportState.AVAILABLE,
            read_areas=(SIM_BLOCK,),
            note_pt="Driver fake de teste",
        )

    def _frame(self, plan: ReadPlan, value_of: Callable[[int, int], float]) -> RawFrame:
        ts = self._clock.now_utc()
        mono = self._clock.monotonic_ns()
        n = self._log.reads
        blocks = {
            b.block_id: RawBlock(
                block_id=b.block_id,
                payload={tag: value_of(i, n) for i, tag in enumerate(b.tags)},
                ts_utc=ts,
                ts_mono_ns=mono,
                latency_ms=1.5,
            )
            for b in plan.blocks
        }
        return RawFrame(equipment_id=self._equipment_id, ts_utc=ts, blocks=blocks, latency_ms=1.5)


class OkDriver(_FakeDriver):
    """Lê sempre com sucesso; valor = base da tag + número da leitura."""

    async def read(self, plan: ReadPlan) -> RawFrame:
        if not self._connected:
            raise DriverConnectError("leitura sem conexão")
        self._log.reads += 1
        return self._frame(plan, lambda i, n: 100.0 * (i + 1) + n)


class ExplodingDriver(_FakeDriver):
    """Levanta a exceção configurada a cada read (após `ok_reads` leituras boas)."""

    def __init__(
        self,
        equipment_id: str,
        clock: Clock,
        log: DriverLog | None = None,
        *,
        exc_factory: Callable[[], BaseException] | None = None,
        ok_reads: int = 0,
    ) -> None:
        super().__init__(equipment_id, clock, log)
        self._exc_factory = exc_factory or (lambda: DriverTimeout("sem resposta (fake)"))
        self._ok_reads = ok_reads

    async def read(self, plan: ReadPlan) -> RawFrame:
        if self._log.reads < self._ok_reads:
            self._log.reads += 1
            return self._frame(plan, lambda i, n: 10.0 * (i + 1) + n)
        self._log.reads += 1
        self._log.failures += 1
        raise self._exc_factory()


class HangingDriver(_FakeDriver):
    """read() nunca responde: simula task travada para o watchdog."""

    async def read(self, plan: ReadPlan) -> RawFrame:
        self._log.reads += 1
        await asyncio.get_running_loop().create_future()
        raise AssertionError("inalcançável")


class ConnectRefusingDriver(_FakeDriver):
    async def connect(self) -> None:
        self._log.connects += 1
        raise DriverConnectError("conexão recusada (fake)")

    async def read(self, plan: ReadPlan) -> RawFrame:
        raise AssertionError("não deveria ler sem conectar")


DriverFactory = Callable[[EquipmentProfile, Mapping, Clock], ReadOnlyDriverBase]


class FakeRegistry:
    """Registry fake: factory por equipamento; lista de factories = uma por criação."""

    def __init__(self) -> None:
        self._factories: dict[str, list[DriverFactory]] = {}
        self._default: DriverFactory | None = None
        self.created: dict[str, list[ReadOnlyDriverBase]] = {}
        self.create_calls: dict[str, int] = {}

    def set_default(self, factory: DriverFactory) -> None:
        self._default = factory

    def add(self, equipment_id: str, *factories: DriverFactory) -> None:
        self._factories.setdefault(equipment_id, []).extend(factories)

    def create(
        self, profile: EquipmentProfile, mapping: Mapping, clock: Clock
    ) -> ReadOnlyDriverBase:
        eid = profile.id
        self.create_calls[eid] = self.create_calls.get(eid, 0) + 1
        if profile.communication.driver != "simulator":
            raise UnsupportedDriver("Disponível na fase J/K; requer configuração de campo")
        factories = self._factories.get(eid)
        if factories:
            factory = factories.pop(0) if len(factories) > 1 else factories[0]
        elif self._default is not None:
            factory = self._default
        else:
            raise UnsupportedDriver(f"sem factory fake para {eid}")
        driver = factory(profile, mapping, clock)
        self.created.setdefault(eid, []).append(driver)
        return driver

    def support(self) -> dict[str, Any]:
        return {"simulator": {"state": DriverSupportState.AVAILABLE.value}}

    def names(self) -> list[str]:
        return ["simulator"]


def ok_factory(log: DriverLog | None = None) -> DriverFactory:
    return lambda profile, _mapping, clock: OkDriver(profile.id, clock, log)


def exploding_factory(
    log: DriverLog | None = None,
    *,
    exc_factory: Callable[[], BaseException] | None = None,
    ok_reads: int = 0,
) -> DriverFactory:
    return lambda profile, _mapping, clock: ExplodingDriver(
        profile.id, clock, log, exc_factory=exc_factory, ok_reads=ok_reads
    )


def hanging_factory(log: DriverLog | None = None) -> DriverFactory:
    return lambda profile, _mapping, clock: HangingDriver(profile.id, clock, log)


def refusing_factory(log: DriverLog | None = None) -> DriverFactory:
    return lambda profile, _mapping, clock: ConnectRefusingDriver(profile.id, clock, log)


# --- pipeline fake ----------------------------------------------------------------------------


class FakeCompiler:
    def compile(self, profile: EquipmentProfile, mapping: Mapping) -> ReadPlan:
        tags = tuple(e.semantic_tag for e in mapping.readable_entries)
        return ReadPlan(
            equipment_id=profile.id,
            mapping_id=mapping.mapping_id,
            mapping_version=mapping.version,
            blocks=(
                ReadBlock(
                    block_id=SIM_BLOCK, area=SIM_BLOCK, address=0, count=len(tags), tags=tags
                ),
            ),
        )


class FakeNormalizer:
    def __init__(self) -> None:
        self._compiler = FakeCompiler()

    def normalize(
        self, frame: RawFrame, profile: EquipmentProfile, mapping: Mapping, clock: Clock
    ) -> SampleBatch:
        plan = self._compiler.compile(profile, mapping)
        driver = profile.communication.driver
        samples: list[Sample] = []
        for block in plan.blocks:
            raw = frame.blocks.get(block.block_id)
            for tag in block.tags:
                entry = mapping.entry(tag)
                assert entry is not None
                value = None
                if raw is not None and isinstance(raw.payload, dict):
                    value = raw.payload.get(tag)
                if value is None:
                    samples.append(
                        Sample(
                            ts_utc=frame.ts_utc,
                            equipment_id=profile.id,
                            tag=tag,
                            value=None,
                            quality=Quality.COMM_ERROR,
                            source=mapping.source_label,
                            ts_mono_ns=clock.monotonic_ns(),
                            reason_pt="sem leitura",
                        )
                    )
                    continue
                samples.append(
                    Sample(
                        ts_utc=raw.ts_utc if raw else frame.ts_utc,
                        equipment_id=profile.id,
                        tag=tag,
                        value=float(value),
                        quality=entry.quality_for(driver),
                        source=mapping.source_label,
                        ts_mono_ns=raw.ts_mono_ns if raw else None,
                    )
                )
        return SampleBatch(
            equipment_id=profile.id,
            ts_utc=frame.ts_utc,
            samples=tuple(samples),
            quality=worst([s.quality for s in samples]),
            latency_ms=frame.latency_ms,
        )


def fake_comm_error_batch(
    profile: EquipmentProfile, mapping: Mapping, clock: Clock, reason_pt: str
) -> SampleBatch:
    ts = clock.now_utc()
    mono = clock.monotonic_ns()
    samples = tuple(
        Sample(
            ts_utc=ts,
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
        equipment_id=profile.id, ts_utc=ts, samples=samples, quality=Quality.COMM_ERROR
    )


def fake_pipeline() -> Any:
    from forja.acquisition.loop import AcquisitionPipeline

    return AcquisitionPipeline(
        compiler=FakeCompiler(), normalizer=FakeNormalizer(), comm_error=fake_comm_error_batch
    )


# --- historian em memória ---------------------------------------------------------------------


class InMemoryHistorian:
    """HistorianRepository em memória + jobs e fechamento observáveis."""

    def __init__(self) -> None:
        self.rows: list[Sample] = []
        self.comm: list[CommLogEntry] = []
        self.rollup_runs = 0
        self.retention_runs = 0
        self.flushed = False
        self.closed = False
        self.fail_writes = False

    async def write(self, samples: Sequence[Sample]) -> None:
        if self.fail_writes:
            raise RuntimeError("historian indisponível (fake)")
        self.rows.extend(samples)

    async def latest(
        self, equipment_id: str, tags: Sequence[str] | None = None
    ) -> dict[str, Sample]:
        out: dict[str, Sample] = {}
        for s in self.rows:
            if s.equipment_id == equipment_id and (tags is None or s.tag in tags):
                out[s.tag] = s
        return out

    async def range(
        self, equipment_id: str, tag: str, start: datetime, end: datetime, max_points: int = 2000
    ) -> Series:
        return Series(equipment_id=equipment_id, tag=tag, resolution="raw", bucket_s=0, points=())

    async def count(self, equipment_id: str | None = None) -> int:
        return len([s for s in self.rows if equipment_id is None or s.equipment_id == equipment_id])

    async def log_comm(self, entry: CommLogEntry) -> None:
        self.comm.append(entry)

    async def comm_log(
        self, equipment_id: str | None, since: datetime | None, limit: int = 200
    ) -> list[CommLogEntry]:
        out = [e for e in self.comm if equipment_id is None or e.equipment_id == equipment_id]
        return out[-limit:]

    async def run_rollups(self) -> dict[str, int]:
        self.rollup_runs += 1
        return {"agg_1m": 0}

    async def run_retention(self) -> dict[str, int]:
        self.retention_runs += 1
        return {"deleted": 0}

    async def flush(self) -> None:
        self.flushed = True

    async def close(self) -> None:
        self.closed = True

    def rows_for(self, equipment_id: str, quality: Quality | None = None) -> list[Sample]:
        return [
            s
            for s in self.rows
            if s.equipment_id == equipment_id and (quality is None or s.quality is quality)
        ]


# --- tempo e bus ------------------------------------------------------------------------------


async def settle(rounds: int = 12) -> None:
    """Cede o loop várias vezes para as tasks progredirem. Sem tempo real."""
    for _ in range(rounds):
        await asyncio.sleep(0)


async def run_for(clock: FakeClock, seconds: float, *, step: float = 1.0, rounds: int = 12) -> None:
    """Avança o relógio fake em passos, cedendo o loop entre eles."""
    await settle(rounds)
    elapsed = 0.0
    while elapsed + 1e-9 < seconds:
        chunk = min(step, seconds - elapsed)
        clock.advance(chunk)
        elapsed += chunk
        await settle(rounds)


async def wait_until(
    predicate: Callable[[], Any], *, timeout_s: float = 20.0, poll_s: float = 0.005
) -> None:
    """Espera uma condição de I/O REAL (ex.: writer thread do SQLite) com teto curto.

    O predicado pode ser síncrono ou assíncrono. Único helper com tempo real.
    Nunca usar para STALE, backoff ou watchdog: isso é FakeClock.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while True:
        result = predicate()
        if inspect.isawaitable(result):
            result = await result
        if result:
            return
        if loop.time() > deadline:
            raise TimeoutError(f"condição não ocorreu em {timeout_s} s")
        await asyncio.sleep(poll_s)


@dataclass
class Collector:
    """Assina um tópico do bus e guarda tudo que chega."""

    bus: AsyncBus
    topic: str
    items: list[Any] = field(default_factory=list)
    _task: asyncio.Task[None] | None = None

    def start(self) -> Collector:
        gen = self.bus.subscribe(self.topic)

        async def _run() -> None:
            async for item in gen:
                self.items.append(item)

        self._task = asyncio.create_task(_run(), name=f"collector-{self.topic}")
        return self

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    def of(self, equipment_id: str) -> list[Any]:
        return [i for i in self.items if getattr(i, "equipment_id", None) == equipment_id]
