"""Kit de teste da API: Container com fakes locais, app FastAPI e cliente httpx (ASGITransport).

Nada aqui abre socket, banco em disco ou driver real. Os blocos vizinhos entram só por import
tardio e com fallback local, para estes testes não dependerem do estado dos outros blocos.
Ids de equipamento vêm da configuração carregada (config/equipment), nunca de literal no teste.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, ConfigDict

from forja.api.app import create_app
from forja.config import ConfigStore, resolve_paths
from forja.domain import (
    MANDATORY_CAVEAT_PT,
    Caveat,
    CommLogEntry,
    CommunicationConfig,
    ConnectionState,
    Diagnosis,
    DiagnosisSummary,
    DriverSupportState,
    EquipmentProfile,
    EquipmentRuntimeStatus,
    Event,
    EventContext,
    EventStatus,
    EvidenceItem,
    EvidenceLevel,
    Hypothesis,
    Mapping,
    NextCheck,
    Quality,
    ReadTestStage,
    Sample,
    Series,
    SeriesPoint,
    Severity,
    SourceRef,
    UnsupportedDriver,
    WhatChangedItem,
)
from forja.infra import AsyncBus, FakeClock
from forja.service.container import Container

REPO_ROOT = Path(__file__).resolve().parents[2]

UNSUPPORTED_REASON_PT = "Disponível na fase J/K; requer configuração de campo"
MODBUS_TEST_ID = "TESTE_MODBUS_01"
NEEDS_CONFIG_TEST_ID = "TESTE_SEM_CONFIG_01"
TEST_MAPPING_ID = "teste_modbus_vazio"
DEV_EDGE_NAME = "Forja Edge (desenvolvimento)"
PROD_EDGE_NAME = "Forja Edge (teste)"
TEST_SOURCE_ID = "SRC-TESTE-REGRA"


# ----------------------------------------------------------------------------------------------
# Fakes dos blocos 1 e 3
# ----------------------------------------------------------------------------------------------


class FakeSupportInfo(BaseModel):
    """Espelho local de DriverSupportInfo (bloco 1)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    state: DriverSupportState
    library: str = ""
    version: str = ""
    reason_pt: str = ""


class FakeRegistry:
    """simulator AVAILABLE; modbus_tcp e ethernet_ip UNSUPPORTED. Nunca AVAILABLE falso."""

    def __init__(self) -> None:
        self._support = {
            "simulator": FakeSupportInfo(
                name="simulator",
                state=DriverSupportState.AVAILABLE,
                library="forja",
                reason_pt="Dados simulados; nenhum valor representa um KCM real.",
            ),
            "modbus_tcp": FakeSupportInfo(
                name="modbus_tcp",
                state=DriverSupportState.UNSUPPORTED,
                library="pymodbus",
                reason_pt=UNSUPPORTED_REASON_PT,
            ),
            "ethernet_ip": FakeSupportInfo(
                name="ethernet_ip",
                state=DriverSupportState.UNSUPPORTED,
                reason_pt=UNSUPPORTED_REASON_PT,
            ),
        }

    def support(self) -> dict[str, FakeSupportInfo]:
        return dict(self._support)

    def names(self) -> list[str]:
        return list(self._support)

    def create(self, profile: EquipmentProfile, mapping: Mapping, clock: Any) -> Any:
        if profile.communication.driver != "simulator":
            raise UnsupportedDriver(UNSUPPORTED_REASON_PT)
        return object()


class FakeLiveSnapshot(BaseModel):
    """Espelho local de LiveSnapshot (bloco 3)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    equipment_id: str
    ts_utc: datetime
    connection: ConnectionState
    samples: dict[str, Sample]
    ages_s: dict[str, float | None]
    is_stale: bool
    stale_for_s: float | None
    last_ok_utc: datetime | None


class FakeReadTestResult(BaseModel):
    """Espelho local de ReadTestResult (bloco 3)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stages: list[tuple[ReadTestStage, datetime, str]]
    final: ReadTestStage
    values: dict[str, Sample]
    latency_ms: float | None
    error_pt: str | None


class FakeManager:
    """statuses()/status()/live()/test_read() controlados pelo teste."""

    def __init__(self, store: ConfigStore, clock: FakeClock) -> None:
        self._store = store
        self._clock = clock
        self._status: dict[str, dict[str, Any]] = {}
        self._samples: dict[str, dict[str, Sample]] = {}
        self._ages: dict[str, dict[str, float | None]] = {}
        self._stale: dict[str, tuple[bool, float | None]] = {}
        self.test_read_calls: list[tuple[EquipmentProfile, Mapping]] = []
        self.test_read_result: FakeReadTestResult | None = None
        self.test_read_error: Exception | None = None

    def set_status(self, equipment_id: str, **changes: Any) -> None:
        self._status.setdefault(equipment_id, {}).update(changes)

    def set_samples(
        self,
        equipment_id: str,
        samples: dict[str, Sample],
        *,
        ages_s: dict[str, float | None] | None = None,
        is_stale: bool = False,
        stale_for_s: float | None = None,
    ) -> None:
        self._samples[equipment_id] = dict(samples)
        self._ages[equipment_id] = dict(ages_s or {})
        self._stale[equipment_id] = (is_stale, stale_for_s)

    def status(self, equipment_id: str) -> EquipmentRuntimeStatus:
        profile = self._store.profiles[equipment_id]
        comm = profile.communication
        if comm.driver == "simulator":
            support, connection = DriverSupportState.AVAILABLE, ConnectionState.DISCONNECTED
        elif comm.needs_configuration:
            support, connection = (
                DriverSupportState.NEEDS_CONFIGURATION,
                ConnectionState.NOT_CONFIGURED,
            )
        else:
            support, connection = DriverSupportState.UNSUPPORTED, ConnectionState.NOT_CONFIGURED
        is_stale, stale_for_s = self._stale.get(equipment_id, (False, None))
        base: dict[str, Any] = {
            "equipment_id": equipment_id,
            "driver": comm.driver,
            "support_state": support,
            "connection": connection,
            "is_stale": is_stale,
            "stale_for_s": stale_for_s,
        }
        base.update(self._status.get(equipment_id, {}))
        return EquipmentRuntimeStatus(**base)

    def statuses(self) -> dict[str, EquipmentRuntimeStatus]:
        return {eid: self.status(eid) for eid in self._store.profiles}

    def live(self, equipment_id: str) -> FakeLiveSnapshot:
        status = self.status(equipment_id)
        samples = self._samples.get(equipment_id, {})
        is_stale, stale_for_s = self._stale.get(equipment_id, (False, None))
        return FakeLiveSnapshot(
            equipment_id=equipment_id,
            ts_utc=self._clock.now_utc(),
            connection=status.connection,
            samples=samples,
            ages_s=self._ages.get(equipment_id, {}),
            is_stale=is_stale,
            stale_for_s=stale_for_s,
            last_ok_utc=status.last_ok_utc,
        )

    async def test_read(self, profile: EquipmentProfile, mapping: Mapping) -> FakeReadTestResult:
        self.test_read_calls.append((profile, mapping))
        if self.test_read_error is not None:
            raise self.test_read_error
        if self.test_read_result is not None:
            return self.test_read_result
        now = self._clock.now_utc()
        return FakeReadTestResult(
            stages=[
                (ReadTestStage.CONNECTING, now, "Conectando ao equipamento"),
                (ReadTestStage.READ_OBTAINED, now, "Leitura obtida: 0 variáveis"),
            ],
            final=ReadTestStage.READ_OBTAINED,
            values={},
            latency_ms=1.0,
            error_pt=None,
        )


# ----------------------------------------------------------------------------------------------
# Historian em memória e repositórios
# ----------------------------------------------------------------------------------------------


class MemoryHistorian:
    def __init__(self) -> None:
        self.samples: list[Sample] = []
        self.comm: list[CommLogEntry] = []

    async def write(self, samples: Any) -> None:
        self.samples.extend(s for s in samples if s.quality is not Quality.STALE)

    async def latest(self, equipment_id: str, tags: Any = None) -> dict[str, Sample]:
        out: dict[str, Sample] = {}
        for s in self.samples:
            if s.equipment_id == equipment_id and (tags is None or s.tag in tags):
                out[s.tag] = s
        return out

    async def range(
        self, equipment_id: str, tag: str, start: datetime, end: datetime, max_points: int = 2000
    ) -> Series:
        rows = sorted(
            (
                s
                for s in self.samples
                if s.equipment_id == equipment_id and s.tag == tag and start <= s.ts_utc <= end
            ),
            key=lambda s: s.ts_utc,
        )
        downsampled = len(rows) > max_points
        rows = rows[:max_points]
        points = tuple(SeriesPoint(ts_utc=s.ts_utc, value=s.value, quality=s.quality) for s in rows)
        return Series(
            equipment_id=equipment_id,
            tag=tag,
            resolution="raw",
            bucket_s=1,
            points=points,
            gap_count=sum(1 for p in points if p.value is None),
            downsampled=downsampled,
        )

    async def count(self, equipment_id: str | None = None) -> int:
        return sum(
            1 for s in self.samples if equipment_id is None or s.equipment_id == equipment_id
        )

    async def log_comm(self, entry: CommLogEntry) -> None:
        self.comm.append(entry)

    async def comm_log(
        self, equipment_id: str | None, since: datetime | None, limit: int = 200
    ) -> list[CommLogEntry]:
        rows = [
            e
            for e in self.comm
            if (equipment_id is None or e.equipment_id == equipment_id)
            and (since is None or e.ts_utc >= since)
        ]
        return rows[-limit:]

    async def stats(self) -> dict[str, Any]:
        return {
            "samples": len(self.samples),
            "bytes": 0,
            "last_sample_utc": self.samples[-1].ts_utc if self.samples else None,
        }


class _LocalEventRepo:
    def __init__(self) -> None:
        self._events: dict[str, Event] = {}

    async def save(self, event: Event) -> None:
        self._events[event.id] = event

    async def get(self, event_id: str) -> Event | None:
        return self._events.get(event_id)

    async def list(
        self,
        equipment_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        open_only: bool = False,
        limit: int = 200,
    ) -> list[Event]:
        out = [
            e
            for e in self._events.values()
            if (equipment_id is None or e.equipment_id == equipment_id)
            and (since is None or e.start_utc >= since)
            and (until is None or e.start_utc <= until)
            and (not open_only or e.is_open)
        ]
        out.sort(key=lambda e: (e.start_utc, e.id), reverse=True)
        return out[: max(0, limit)]

    async def find_open(self, equipment_id: str, dedupe_key: str) -> Event | None:
        for e in self._events.values():
            if e.equipment_id == equipment_id and e.dedupe_key == dedupe_key and e.is_open:
                return e
        return None


class _LocalDiagnosisRepo:
    def __init__(self) -> None:
        self._by_event: dict[str, Diagnosis] = {}

    async def save(self, diagnosis: Diagnosis) -> None:
        self._by_event[diagnosis.event_id] = diagnosis

    async def get_for_event(self, event_id: str) -> Diagnosis | None:
        return self._by_event.get(event_id)

    async def list(self, equipment_id: str | None = None, limit: int = 100) -> list[Diagnosis]:
        out = [
            d
            for d in self._by_event.values()
            if equipment_id is None or d.equipment_id == equipment_id
        ]
        return out[:limit]


def _memory_repos() -> tuple[Any, Any]:
    """Repositórios do bloco 4 quando existem; senão os locais acima."""
    try:
        from forja.events.memory_store import (
            InMemoryDiagnosisRepository,
            InMemoryEventRepository,
        )
    except ImportError:
        return _LocalEventRepo(), _LocalDiagnosisRepo()
    return InMemoryEventRepository(), InMemoryDiagnosisRepository()


class AuditingEventRepo:
    """EventRepository + trilha de auditoria em memória (espelho de SqliteCoreStore.audit)."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.audits: list[dict[str, Any]] = []

    async def save(self, event: Event) -> None:
        await self._inner.save(event)

    async def get(self, event_id: str) -> Event | None:
        return await self._inner.get(event_id)

    async def list(self, **kwargs: Any) -> list[Event]:
        return await self._inner.list(**kwargs)

    async def find_open(self, equipment_id: str, dedupe_key: str) -> Event | None:
        return await self._inner.find_open(equipment_id, dedupe_key)

    async def audit(
        self,
        user: str,
        action: str,
        entity_type: str,
        entity_id: str,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        reason_pt: str = "",
    ) -> None:
        self.audits.append(
            {
                "user": user,
                "action": action,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "before": before,
                "after": after,
                "reason_pt": reason_pt,
            }
        )

    async def audit_list(self, limit: int = 200) -> list[dict[str, Any]]:
        return self.audits[-limit:]


class FakeRuleEngine:
    rules: tuple[Any, ...] = ()

    def open_events(self, equipment_id: str) -> list[Event]:
        return []

    async def on_batch(self, batch: Any) -> list[Any]:
        return []


class FakeDiagnosisEngine:
    def diagnose(self, event: Event) -> Diagnosis:
        raise NotImplementedError("o teste de API não diagnostica; use make_diagnosis()")


# ----------------------------------------------------------------------------------------------
# Construtores de dados de teste
# ----------------------------------------------------------------------------------------------


def make_sample(
    clock: FakeClock,
    equipment_id: str,
    tag: str,
    value: float | None,
    *,
    quality: Quality = Quality.SIMULATED,
    age_s: float = 0.0,
    reason_pt: str | None = None,
) -> Sample:
    return Sample(
        ts_utc=clock.now_utc() - timedelta(seconds=age_s),
        equipment_id=equipment_id,
        tag=tag,
        value=value,
        quality=quality,
        source="sim:teste",
        ts_mono_ns=clock.monotonic_ns() - int(age_s * 1e9),
        reason_pt=reason_pt,
    )


def make_event(
    clock: FakeClock,
    equipment_id: str,
    *,
    type_: str = "BELT_LOAD_LOW",
    title_pt: str = "Pouco material sobre a correia",
    severity: Severity = Severity.ATTENTION,
    start_offset_s: float = 0.0,
    is_open: bool = True,
    rule_id: str = "R-TESTE-001",
    event_id: str | None = None,
) -> Event:
    start = clock.now_utc() - timedelta(seconds=start_offset_s)
    what_changed = (
        WhatChangedItem(
            tag="belt_load",
            label_pt="Material na correia",
            unit="kg/m",
            before=2.0,
            now=1.1,
            delta=-45.0,
            delta_kind="pct",
            changed_first=True,
            ts_start_utc=start,
            text_pt="Antes: 2,00 kg/m · Agora: 1,10 kg/m · ↓ 45,0%",
        ),
    )
    pre = (make_sample(clock, equipment_id, "belt_load", 2.0, age_s=start_offset_s + 30),)
    extra: dict[str, Any] = {}
    if not is_open:
        extra = {"end_utc": clock.now_utc(), "status": EventStatus.RESOLVED}
    return Event(
        **({"id": event_id} if event_id else {}),
        equipment_id=equipment_id,
        type=type_,
        title_pt=title_pt,
        start_utc=start,
        severity=severity,
        summary_pt="Material na correia caiu de 2,00 para 1,10 kg/m (↓ 45,0%).",
        rule_id=rule_id,
        context=EventContext(
            pre_window_s=60, post_window_s=30, pre_samples=pre, what_changed=what_changed
        ),
        sources=(
            SourceRef(
                id=TEST_SOURCE_ID,
                kind="rule",
                title="Regra Forja de teste",
                reference=f"config/rules/{rule_id}.yaml",
                evidence_level=EvidenceLevel.FORJA_RULE,
            ),
        ),
        quality=Quality.SIMULATED,
        dedupe_key=f"{equipment_id}:{rule_id}",
        diagnosis_ref="belt_load_low",
        **extra,
    )


def make_diagnosis(clock: FakeClock, event: Event) -> Diagnosis:
    """Diagnosis v1.0 válido, construído à mão (sem o motor do bloco 4)."""
    evidence = (
        EvidenceItem(
            id="EV-RULE",
            text_pt=f"Regra Forja {event.rule_id} atendida.",
            evidence_level=EvidenceLevel.FORJA_RULE,
            ts_utc=event.start_utc,
        ),
    )
    hypotheses = (
        Hypothesis(
            id="H1",
            text_pt="Comportamento compatível com menos material chegando à correia.",
            evidence_level=EvidenceLevel.HYPOTHESIS,
            rationale_pt="Carga caiu e o acionamento compensou.",
            verification_ids=("V1",),
            source_ids=(TEST_SOURCE_ID,),
        ),
    )
    next_checks = (
        NextCheck(
            id="V1",
            order=1,
            text_pt="Verificar a alimentação de material sobre a correia.",
            how_pt="Observar a entrada do dosador.",
            evidence_level=EvidenceLevel.TECHNICAL_OPINION,
        ),
    )
    sources = tuple(event.sources)
    caveats = (
        Caveat(text_pt=MANDATORY_CAVEAT_PT),
        Caveat(text_pt="Os dados deste evento são SIMULADOS pela Forja."),
    )
    return Diagnosis(
        event_id=event.id,
        equipment_id=event.equipment_id,
        generated_at_utc=clock.now_utc(),
        summary=DiagnosisSummary(
            title_pt=event.title_pt,
            text_pt=event.summary_pt,
            internal_code=event.type,
            severity=event.severity,
        ),
        evidence=evidence,
        what_changed=event.context.what_changed,
        hypotheses=hypotheses,
        next_checks=next_checks,
        sources=sources,
        caveats=caveats,
        evidence_summary=Diagnosis.build_evidence_summary(
            evidence, hypotheses, next_checks, sources
        ),
    )


# ----------------------------------------------------------------------------------------------
# Mundo de teste
# ----------------------------------------------------------------------------------------------


@dataclass
class ApiWorld:
    app: Any
    container: Container
    clock: FakeClock
    bus: AsyncBus
    store: ConfigStore
    manager: FakeManager
    historian: MemoryHistorian
    events_repo: AuditingEventRepo
    diagnoses_repo: Any
    registry: FakeRegistry

    @property
    def simulator_ids(self) -> list[str]:
        return [p.id for p in self.store.profiles.values() if p.is_simulated]

    def _scenario_of(self, profile: EquipmentProfile) -> str:
        return str(profile.communication.options.get("scenario", "NORMAL_OPERATION")).upper()

    @property
    def comm_failure_id(self) -> str:
        for p in self.store.profiles.values():
            if p.is_simulated and self._scenario_of(p) == "COMMUNICATION_FAILURE":
                return p.id
        raise AssertionError("semente sem perfil simulado em COMMUNICATION_FAILURE")

    @property
    def healthy_sim_id(self) -> str:
        for p in self.store.profiles.values():
            if p.is_simulated and self._scenario_of(p) != "COMMUNICATION_FAILURE":
                return p.id
        raise AssertionError("semente sem perfil simulado saudável")

    def sample(self, equipment_id: str, tag: str, value: float | None, **kwargs: Any) -> Sample:
        return make_sample(self.clock, equipment_id, tag, value, **kwargs)

    def event(self, equipment_id: str, **kwargs: Any) -> Event:
        return make_event(self.clock, equipment_id, **kwargs)

    def diagnosis(self, event: Event) -> Diagnosis:
        return make_diagnosis(self.clock, event)

    @property
    def hub(self) -> Any:
        return self.app.state.stream_hub


def build_world(*, dev_mode: bool = False, extra_real_profiles: bool = True) -> ApiWorld:
    """Container de teste: config real da semente + fakes locais + FakeClock."""
    paths = resolve_paths(REPO_ROOT)
    store = ConfigStore(paths).load_all()
    edge = store.config.edge.model_copy(
        update={"name": DEV_EDGE_NAME if dev_mode else PROD_EDGE_NAME}
    )
    store.config = store.config.model_copy(update={"edge": edge})
    if extra_real_profiles:
        store.mappings[TEST_MAPPING_ID] = Mapping(
            mapping_id=TEST_MAPPING_ID,
            equipment_id="*",
            driver="modbus_tcp",
            source="teste: mapping vazio",
            entries=[],
        )
        store.profiles[MODBUS_TEST_ID] = EquipmentProfile(
            id=MODBUS_TEST_ID,
            name="Dosador de teste (Modbus)",
            communication=CommunicationConfig(
                driver="modbus_tcp", protocol="modbus_tcp", ip="127.0.0.1", port=1502
            ),
            mapping_profile=TEST_MAPPING_ID,
            is_example=True,
        )
        store.profiles[NEEDS_CONFIG_TEST_ID] = EquipmentProfile(
            id=NEEDS_CONFIG_TEST_ID,
            name="Dosador de teste (sem configuração)",
            communication=CommunicationConfig(driver="modbus_tcp"),
            mapping_profile=TEST_MAPPING_ID,
            is_example=True,
        )
    clock = FakeClock()
    bus = AsyncBus()
    registry = FakeRegistry()
    historian = MemoryHistorian()
    events_inner, diagnoses_repo = _memory_repos()
    events_repo = AuditingEventRepo(events_inner)
    manager = FakeManager(store, clock)
    container = Container(
        paths=paths,
        store=store,
        clock=clock,
        bus=bus,
        registry=registry,  # type: ignore[arg-type]
        historian=historian,
        events_repo=events_repo,
        diagnoses_repo=diagnoses_repo,
        manager=manager,  # type: ignore[arg-type]
        rule_engine=FakeRuleEngine(),
        diagnosis_engine=FakeDiagnosisEngine(),
        started_at_utc=clock.now_utc(),
    )
    app = create_app(container)
    return ApiWorld(
        app=app,
        container=container,
        clock=clock,
        bus=bus,
        store=store,
        manager=manager,
        historian=historian,
        events_repo=events_repo,
        diagnoses_repo=diagnoses_repo,
        registry=registry,
    )


async def shutdown_world(world: ApiWorld) -> None:
    """Para o hub SSE e limpa controles do simulador que a API possa ter criado no singleton."""
    await world.hub.stop()
    try:
        from forja.drivers.simulator.controls import SIMULATOR_CONTROLS
    except ImportError:
        return
    for eid in world.simulator_ids:
        SIMULATOR_CONTROLS.forget(eid)


async def settle(ticks: int = 6) -> None:
    """Deixa tasks de fundo (bus, hub) rodarem algumas iterações do loop."""
    for _ in range(ticks):
        await asyncio.sleep(0)


# ----------------------------------------------------------------------------------------------
# Fixtures (importar no módulo de teste: `from tests.integration.api_testkit import client, world`)
# ----------------------------------------------------------------------------------------------


@pytest.fixture
async def world() -> AsyncIterator[ApiWorld]:
    w = build_world()
    try:
        yield w
    finally:
        await shutdown_world(w)


@pytest.fixture
async def client(world: ApiWorld) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=world.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


# ----------------------------------------------------------------------------------------------
# Harness ASGI para SSE (httpx junta o corpo inteiro; aqui lemos evento a evento)
# ----------------------------------------------------------------------------------------------


@dataclass
class SseCapture:
    status: int | None = None
    headers: dict[str, str] = field(default_factory=dict)
    events: list[dict[str, str]] = field(default_factory=list)
    pending: str = ""
    arrived: asyncio.Event = field(default_factory=asyncio.Event)
    disconnect: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task[None] | None = None

    def feed(self, chunk: bytes) -> None:
        self.pending += chunk.decode("utf-8").replace("\r\n", "\n")
        while "\n\n" in self.pending:
            block, self.pending = self.pending.split("\n\n", 1)
            parsed = _parse_block(block)
            if parsed is not None:
                self.events.append(parsed)
        self.arrived.set()

    async def wait_for(self, count: int, timeout_s: float = 3.0) -> None:
        while len(self.events) < count:
            await asyncio.wait_for(self.arrived.wait(), timeout_s)
            self.arrived.clear()

    async def close(self, timeout_s: float = 3.0) -> None:
        self.disconnect.set()
        if self.task is not None:
            await asyncio.wait_for(self.task, timeout_s)


def _parse_block(block: str) -> dict[str, str] | None:
    fields: dict[str, str] = {}
    data: list[str] = []
    for line in block.split("\n"):
        if not line or line.startswith(":"):
            continue
        name, _, value = line.partition(":")
        value = value.removeprefix(" ")
        if name == "data":
            data.append(value)
        else:
            fields[name] = value
    if not fields and not data:
        return None
    fields["data"] = "\n".join(data)
    return fields


def open_sse(
    app: Any, path: str, *, query: str = "", headers: dict[str, str] | None = None
) -> SseCapture:
    """Chama a app ASGI direto, com `receive` que só desconecta quando o teste mandar."""
    cap = SseCapture()
    raw_headers = [(b"host", b"testserver"), (b"accept", b"text/event-stream")]
    for k, v in (headers or {}).items():
        raw_headers.append((k.lower().encode(), v.encode()))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "root_path": "",
        "headers": raw_headers,
        "client": ("127.0.0.1", 40000),
        "server": ("127.0.0.1", 8765),
    }
    request_sent = False

    async def receive() -> dict[str, Any]:
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await cap.disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            cap.status = int(message["status"])
            cap.headers = {k.decode().lower(): v.decode() for k, v in message.get("headers", [])}
        elif message["type"] == "http.response.body":
            cap.feed(message.get("body", b""))

    cap.task = asyncio.create_task(app(scope, receive, send), name="sse-harness")
    return cap
