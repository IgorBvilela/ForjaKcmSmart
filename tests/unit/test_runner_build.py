"""Montagem do serviço: EngineBridge, PeriodicJobs, build_container, start/stop.

build_container com módulos reais só roda se todos os blocos existirem; caso contrário o teste
é pulado com o motivo, e a montagem é provada com stubs injetados em sys.modules.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from forja.acquisition.manager import EquipmentManager
from forja.config import ConfigStore, ForjaPaths
from forja.domain import (
    TOPIC_DIAGNOSES,
    TOPIC_EVENTS,
    TOPIC_SAMPLES,
    ConnectionState,
    Event,
    EventContext,
    EventTransition,
    Quality,
    Sample,
    SampleBatch,
    Severity,
)
from forja.infra import AsyncBus, FakeClock
from forja.service import Container, EngineBridge, PeriodicJobs, build_container, start, stop
from tests.fixtures.acquisition_fakes import (
    Collector,
    FakeRegistry,
    InMemoryHistorian,
    fake_pipeline,
    make_paths,
    make_profile,
    make_store,
    ok_factory,
    run_for,
    settle,
    wait_until,
)

pytestmark = pytest.mark.unit

REAL_MODULES = (
    "forja.drivers.registry",
    "forja.historian.sqlite",
    "forja.historian.core_store",
    "forja.events.engine",
    "forja.events.rules",
    "forja.diagnostics.engine",
    "forja.diagnostics.library",
)


def _missing_modules() -> list[str]:
    missing: list[str] = []
    for name in REAL_MODULES:
        try:
            if importlib.util.find_spec(name) is None:
                missing.append(name)
        except (ImportError, ValueError):
            missing.append(name)
    return missing


# --- stubs -----------------------------------------------------------------------------------


class StubRuleEngine:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs
        self.batches: list[SampleBatch] = []
        self.next: list[EventTransition] = []
        self.fail = False

    async def on_batch(self, batch: SampleBatch) -> list[EventTransition]:
        self.batches.append(batch)
        if self.fail:
            raise RuntimeError("motor de regras quebrou (stub)")
        out, self.next = self.next, []
        return out


class StubDiagnosisEngine:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.events: list[Event] = []

    def diagnose(self, event: Event) -> Any:
        self.events.append(event)
        return types.SimpleNamespace(event_id=event.id, equipment_id=event.equipment_id)


class StubRepo:
    def __init__(self) -> None:
        self.saved: list[Any] = []
        self.closed = False

    async def save(self, obj: Any) -> None:
        self.saved.append(obj)

    async def get(self, _id: str) -> Any:
        return None

    async def get_for_event(self, _id: str) -> Any:
        return None

    async def list(self, *args: Any, **kwargs: Any) -> list[Any]:
        return list(self.saved)

    async def find_open(self, *_args: Any) -> Any:
        return None

    async def close(self) -> None:
        self.closed = True


def _event(clock: FakeClock, eid: str = "EQ_A") -> Event:
    return Event(
        equipment_id=eid,
        type="BELT_LOAD_LOW",
        title_pt="Pouco material sobre a correia",
        start_utc=clock.now_utc(),
        severity=Severity.ATTENTION,
        summary_pt="Resumo de teste.",
        rule_id="R-BELTLOAD-001",
        context=EventContext(pre_window_s=60, post_window_s=30),
        quality=Quality.SIMULATED,
        dedupe_key=f"{eid}:R-BELTLOAD-001",
    )


def _batch(clock: FakeClock, eid: str = "EQ_A") -> SampleBatch:
    s = Sample(
        ts_utc=clock.now_utc(),
        equipment_id=eid,
        tag="belt_load",
        value=1.0,
        quality=Quality.SIMULATED,
        source="sim:teste",
    )
    return SampleBatch(
        equipment_id=eid, ts_utc=clock.now_utc(), samples=(s,), quality=Quality.SIMULATED
    )


# --- EngineBridge -----------------------------------------------------------------------------


async def test_bridge_open_transition_saves_publishes_and_diagnoses() -> None:
    clock = FakeClock()
    bus = AsyncBus()
    rules, diag = StubRuleEngine(), StubDiagnosisEngine()
    events_repo, diag_repo = StubRepo(), StubRepo()
    bridge = EngineBridge(bus, rules, diag, events_repo, diag_repo)
    ev_col = Collector(bus, TOPIC_EVENTS).start()
    dg_col = Collector(bus, TOPIC_DIAGNOSES).start()
    try:
        event = _event(clock)
        rules.next = [EventTransition(kind="OPEN", event=event)]
        done = await bridge.handle(_batch(clock))
        await settle()
        assert len(done) == 1
        assert events_repo.saved == [event]
        assert diag.events == [event]
        assert len(diag_repo.saved) == 1
        assert diag_repo.saved[0].event_id == event.id
        assert len(ev_col.items) == 1
        assert ev_col.items[0].kind == "OPEN"
        assert len(dg_col.items) == 1
        assert bridge.transitions == 1
        assert bridge.diagnoses == 1
        assert bridge.errors == 0

        rules.next = [EventTransition(kind="UPDATE", event=event)]
        await bridge.handle(_batch(clock))
        await settle()
        assert len(diag.events) == 1, "UPDATE não gera diagnóstico novo"
        assert len(ev_col.items) == 2
    finally:
        await ev_col.close()
        await dg_col.close()


async def test_bridge_contains_rule_engine_failures() -> None:
    clock = FakeClock()
    rules, diag = StubRuleEngine(), StubDiagnosisEngine()
    bridge = EngineBridge(AsyncBus(), rules, diag, StubRepo(), StubRepo())
    rules.fail = True
    assert await bridge.handle(_batch(clock)) == []
    assert bridge.errors == 1
    assert bridge.batches == 1


async def test_bridge_run_consumes_topic_samples() -> None:
    clock = FakeClock()
    bus = AsyncBus()
    rules = StubRuleEngine()
    bridge = EngineBridge(bus, rules, StubDiagnosisEngine(), StubRepo(), StubRepo())
    bridge.attach()
    task = asyncio.create_task(bridge.run())
    try:
        await bus.publish(TOPIC_SAMPLES, _batch(clock))
        await bus.publish(TOPIC_SAMPLES, "lixo que não é lote")
        await settle()
        assert len(rules.batches) == 1
        assert bridge.batches == 1
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


# --- PeriodicJobs -----------------------------------------------------------------------------


async def test_periodic_jobs_follow_the_clock() -> None:
    clock = FakeClock()
    historian = InMemoryHistorian()
    jobs = PeriodicJobs(historian, clock)
    tasks = jobs.start_tasks()
    try:
        await run_for(clock, 59)
        assert historian.rollup_runs == 0
        await run_for(clock, 1)
        assert historian.rollup_runs == 1
        assert historian.retention_runs == 0
        await run_for(clock, 3540, step=60)
        assert historian.retention_runs == 1
        assert historian.rollup_runs == 60
        assert jobs.runs == {"run_rollups": 60, "run_retention": 1}
        assert jobs.last_result["run_retention"] == {"deleted": 0}
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def test_periodic_jobs_without_methods_and_with_errors() -> None:
    clock = FakeClock()
    bare = object()
    jobs = PeriodicJobs(bare, clock)
    tasks = jobs.start_tasks()
    await settle()
    assert all(t.done() for t in tasks), "historian sem jobs: tasks terminam sozinhas"
    assert await jobs.run_once("run_rollups") is None

    class Broken:
        async def run_rollups(self) -> dict[str, int]:
            raise RuntimeError("rollup quebrou")

    jobs2 = PeriodicJobs(Broken(), clock, rollup_every_s=1.0)
    t = asyncio.create_task(jobs2.run_rollups_forever())
    try:
        await run_for(clock, 3)
        assert jobs2.errors["run_rollups"] == 3
        assert not t.done(), "erro no job não derruba a task"
    finally:
        t.cancel()
        await asyncio.gather(t, return_exceptions=True)


# --- start / stop com container de stubs ----------------------------------------------------


def _stub_container(
    tmp_path: Path,
) -> tuple[Container, FakeClock, InMemoryHistorian, StubRuleEngine]:
    clock = FakeClock()
    bus = AsyncBus()
    historian = InMemoryHistorian()
    registry = FakeRegistry()
    registry.set_default(ok_factory())
    store = make_store(make_paths(tmp_path), [make_profile("EQ_A"), make_profile("EQ_B")])
    manager = EquipmentManager(store, registry, historian, bus, clock, pipeline=fake_pipeline())
    rules = StubRuleEngine()
    core = StubRepo()
    container = Container(
        paths=store.paths,
        store=store,
        clock=clock,
        bus=bus,
        registry=registry,
        historian=historian,
        events_repo=core,
        diagnoses_repo=core,
        manager=manager,
        rule_engine=rules,
        diagnosis_engine=StubDiagnosisEngine(),
        started_at_utc=clock.now_utc(),
    )
    return container, clock, historian, rules


async def test_start_and_stop_are_graceful(tmp_path: Path) -> None:
    container, clock, historian, rules = _stub_container(tmp_path)
    await start(container)
    assert container.runtime.started is True
    await start(container)  # idempotente
    await run_for(clock, 5)

    assert rules.batches, "RuleEngine recebeu lotes pelo bus"
    assert {b.equipment_id for b in rules.batches} == {"EQ_A", "EQ_B"}
    assert container.runtime.bridge is not None
    assert container.runtime.bridge.batches >= 10
    assert await historian.count() > 0
    assert container.uptime_s == pytest.approx(5.0)

    tasks = list(container.runtime.tasks)
    await stop(container, timeout_s=1)
    await settle()
    assert all(t.done() for t in tasks)
    assert container.runtime.tasks == []
    assert container.runtime.started is False
    assert historian.flushed
    assert historian.closed
    assert container.events_repo.closed  # type: ignore[attr-defined]
    assert not container.manager.is_running("EQ_A")
    await stop(container, timeout_s=1)  # parar duas vezes é inofensivo


# --- build_container ------------------------------------------------------------------------


def _repo_paths(tmp_path: Path) -> ForjaPaths:
    root = Path(__file__).resolve().parents[2]
    return ForjaPaths(
        home=root,
        config_dir=root / "config",
        knowledge_dir=root / "knowledge",
        data_dir=tmp_path / "var",
        logs_dir=tmp_path / "var" / "logs",
        backups_dir=tmp_path / "var" / "backups",
    )


def rt_core_closed_later(container: Container) -> bool:
    """O core store (não a view) está na lista de fechamento."""
    return any(hasattr(c, "opened") for c in container.runtime.closeables)


async def test_build_container_wiring_with_stubs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    created: dict[str, Any] = {}

    class StubHistorian(InMemoryHistorian):
        def __init__(self, db_path: Path, config: Any, clock: Any) -> None:
            super().__init__()
            created["historian"] = (db_path, config, clock)
            self.opened = False

        async def open(self) -> None:
            self.opened = True

    class StubCore(StubRepo):
        def __init__(self, db_path: Path, clock: Any) -> None:
            super().__init__()
            created["core"] = (db_path, clock)
            self.opened = False
            # como o SqliteCoreStore real: uma view por porta
            self.events = self
            self.diagnoses = self

        async def open(self) -> None:
            self.opened = True

    def _module(name: str, **attrs: Any) -> types.ModuleType:
        mod = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(mod, k, v)
        return mod

    registry = FakeRegistry()
    registry.set_default(ok_factory())
    monkeypatch.setitem(
        sys.modules,
        "forja.historian.sqlite",
        _module("forja.historian.sqlite", SqliteHistorian=StubHistorian),
    )
    monkeypatch.setitem(
        sys.modules,
        "forja.historian.core_store",
        _module("forja.historian.core_store", SqliteCoreStore=StubCore),
    )
    monkeypatch.setitem(
        sys.modules,
        "forja.drivers.registry",
        _module("forja.drivers.registry", build_default_registry=lambda: registry),
    )
    monkeypatch.setitem(
        sys.modules,
        "forja.events.engine",
        _module("forja.events.engine", RuleEngine=StubRuleEngine),
    )
    monkeypatch.setitem(
        sys.modules,
        "forja.events.rules",
        _module("forja.events.rules", load_rules=lambda d: ["regra-stub", d]),
    )
    monkeypatch.setitem(
        sys.modules,
        "forja.diagnostics.engine",
        _module("forja.diagnostics.engine", DiagnosisEngine=StubDiagnosisEngine),
    )
    monkeypatch.setitem(
        sys.modules,
        "forja.diagnostics.library",
        _module("forja.diagnostics.library", load_library=lambda d: ("biblioteca-stub", d)),
    )

    clock = FakeClock(datetime(2026, 5, 1, tzinfo=UTC))
    paths = _repo_paths(tmp_path)
    container = await build_container(paths, clock)

    assert isinstance(container.store, ConfigStore)
    assert container.store.profiles
    assert container.clock is clock
    assert container.registry is registry
    assert isinstance(container.manager, EquipmentManager)
    assert container.started_at_utc == clock.now_utc()
    assert paths.data_dir.is_dir()
    assert paths.logs_dir.is_dir()
    assert paths.backups_dir.is_dir()

    historian = container.historian
    assert isinstance(historian, StubHistorian)
    assert historian.opened
    assert created["historian"] == (paths.historian_db, container.store.config.historian, clock)
    assert created["core"] == (paths.core_db, clock)
    assert container.events_repo is container.diagnoses_repo
    assert container.events_repo.opened  # type: ignore[attr-defined]
    assert rt_core_closed_later(container)

    rules = container.rule_engine
    assert isinstance(rules, StubRuleEngine)
    assert rules.args[0] == ["regra-stub", paths.rules_dir]
    assert rules.args[1] is container.store.alarms
    assert rules.args[2] is container.store.stop_by
    assert rules.args[3] is clock
    ev = container.store.config.events
    assert rules.args[4:7] == (ev.pre_window_s, ev.post_window_s, ev.buffer_s)
    assert rules.kwargs["profiles"] is container.store.profiles
    diag = container.diagnosis_engine
    assert isinstance(diag, StubDiagnosisEngine)
    assert diag.args == (("biblioteca-stub", paths.knowledge_dir / "diagnostics"), clock)

    rt = container.runtime
    assert rt.bridge is not None
    assert rt.jobs is not None
    assert rt.closeables == [historian, container.events_repo]
    assert rt.jobs.rollup_every_s == 60.0
    assert rt.jobs.retention_every_s == 3600.0

    await start(container)
    await run_for(clock, 3)
    assert rules.batches, "lotes dos perfis-semente chegam ao RuleEngine"
    await stop(container, timeout_s=1)
    assert historian.closed


@pytest.mark.integration
async def test_build_container_real_modules(tmp_path: Path) -> None:
    """Stack real (blocos 1, 2 e 4) com SQLite em tmp_path. Pulado se algum módulo faltar.

    O historian real grava em thread: antes de avançar o FakeClock, espera-se a I/O real
    terminar (wait_until), senão o watchdog veria silêncio falso.
    """
    missing = _missing_modules()
    if missing:
        pytest.skip(f"módulos de outros blocos ainda ausentes: {', '.join(missing)}")
    from forja.drivers.simulator.controls import SIMULATOR_CONTROLS

    clock = FakeClock()
    paths = _repo_paths(tmp_path)
    container = await build_container(paths, clock)
    sim_ids = [p.id for p in container.store.profiles.values() if p.is_simulated]
    for eid in sim_ids:
        SIMULATOR_CONTROLS.forget(eid)
    bridge = container.runtime.bridge
    assert bridge is not None
    try:
        assert paths.historian_db.exists()
        assert paths.core_db.exists()
        healthy = [
            eid
            for eid, p in container.store.profiles.items()
            if str(p.communication.options.get("scenario", "")).upper() != "COMMUNICATION_FAILURE"
        ]
        await start(container)
        n = len(container.store.profiles)
        await wait_until(lambda: bridge.batches >= n)  # primeiro poll de todos (t=0)
        clock.advance(1.0)
        # saudáveis fazem poll a cada 1 s; o que falha segue o backoff com jitter (~1 s ± 20%)
        await wait_until(lambda: bridge.batches >= n + len(healthy))
        await wait_until(
            lambda: all(s.last_read_utc is not None for s in container.manager.statuses().values())
        )
        statuses = container.manager.statuses()
        assert set(statuses) == set(container.store.profiles)
        assert all(s.restart_count == 0 for s in statuses.values())
        for eid in healthy:
            assert statuses[eid].connection is ConnectionState.CONNECTED, eid
            live = container.manager.live(eid)
            assert live.samples, eid
            assert all(s.quality is Quality.SIMULATED for s in live.samples.values()), eid

        async def _has_rows() -> bool:
            return await container.historian.count() > 0

        await wait_until(_has_rows)
    finally:
        await stop(container, timeout_s=5)
        for eid in sim_ids:
            SIMULATOR_CONTROLS.forget(eid)
    assert container.runtime.started is False
    assert container.runtime.tasks == []
