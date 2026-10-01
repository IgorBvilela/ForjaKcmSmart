"""Watchdog: task sem tick por mais de 3 × poll_interval é cancelada e recriada."""

from __future__ import annotations

from pathlib import Path

import pytest

from forja.acquisition.manager import EquipmentManager
from forja.acquisition.watchdog import Watchdog
from forja.domain import ConnectionState, Quality
from forja.infra import AsyncBus, FakeClock
from tests.fixtures.acquisition_fakes import (
    DriverLog,
    FakeRegistry,
    InMemoryHistorian,
    fake_pipeline,
    hanging_factory,
    make_paths,
    make_profile,
    make_store,
    ok_factory,
    run_for,
)

pytestmark = pytest.mark.integration

A, B = "EQ_A", "EQ_B"


async def test_watchdog_unit_overdue_and_restart_count() -> None:
    clock = FakeClock()
    wd = Watchdog(clock, check_interval_s=1.0, factor=3.0)
    last_tick = {"ns": clock.monotonic_ns()}
    restarted: list[str] = []

    async def _restart() -> None:
        restarted.append(A)
        last_tick["ns"] = clock.monotonic_ns()

    wd.watch(A, poll_interval_s=1.0, last_tick=lambda: last_tick["ns"], restart=_restart)
    assert wd.watched() == [A]
    clock.advance(3.0)
    assert wd.is_overdue(A) is False, "3,0 s não passa de 3 × 1 s"
    assert await wd.check_once() == []
    clock.advance(0.1)
    assert wd.is_overdue(A) is True
    assert await wd.check_once() == [A]
    assert wd.restarts[A] == 1
    assert restarted == [A]
    assert wd.is_overdue(A) is False, "após o restart o tick foi renovado"
    wd.unwatch(A)
    assert wd.silence_s(A) is None
    assert wd.is_overdue(A) is False


async def test_watchdog_restart_failure_is_contained() -> None:
    clock = FakeClock()
    wd = Watchdog(clock)

    async def _restart() -> None:
        raise RuntimeError("falha fake ao reiniciar")

    wd.watch(A, poll_interval_s=1.0, last_tick=lambda: None, restart=_restart)
    clock.advance(10)
    assert await wd.check_once() == []
    assert wd.restarts.get(A, 0) == 0


async def test_hung_task_is_restarted_and_recovers(tmp_path: Path) -> None:
    clock = FakeClock()
    registry = FakeRegistry()
    hang_log, ok_log = DriverLog(), DriverLog()
    registry.add(A, hanging_factory(hang_log), ok_factory(ok_log))
    registry.add(B, ok_factory())
    store = make_store(make_paths(tmp_path), [make_profile(A), make_profile(B)])
    historian = InMemoryHistorian()
    manager = EquipmentManager(
        store, registry, historian, AsyncBus(), clock, pipeline=fake_pipeline()
    )
    try:
        await manager.start_all()
        await run_for(clock, 1)
        first_task = manager.task_of(A)
        assert first_task is not None
        assert hang_log.reads == 1
        assert manager.status(A).restart_count == 0

        await run_for(clock, 4)  # silêncio > 3 × 1 s

        assert manager.status(A).restart_count == 1
        assert manager.watchdog.restarts[A] == 1
        assert first_task.done()
        second_task = manager.task_of(A)
        assert second_task is not None
        assert second_task is not first_task
        assert registry.create_calls[A] == 2
        assert hang_log.disconnects == 1, "driver travado foi desconectado no shutdown da task"

        await run_for(clock, 3)
        assert manager.status(A).connection is ConnectionState.CONNECTED
        assert ok_log.reads >= 2
        live = manager.live(A)
        assert live.samples
        assert all(s.quality is Quality.SIMULATED for s in live.samples.values())
        # B nunca foi tocado
        assert manager.status(B).restart_count == 0
        assert registry.create_calls[B] == 1
    finally:
        await manager.stop_all(timeout_s=1)


async def test_healthy_loops_are_never_restarted(tmp_path: Path) -> None:
    clock = FakeClock()
    registry = FakeRegistry()
    registry.set_default(ok_factory())
    store = make_store(
        make_paths(tmp_path), [make_profile(A), make_profile(B, poll_interval_s=2.0)]
    )
    manager = EquipmentManager(
        store, registry, InMemoryHistorian(), AsyncBus(), clock, pipeline=fake_pipeline()
    )
    try:
        await manager.start_all()
        await run_for(clock, 60)
        assert manager.status(A).restart_count == 0
        assert manager.status(B).restart_count == 0
        assert manager.watchdog.restarts == {}
        assert registry.create_calls == {A: 1, B: 1}
    finally:
        await manager.stop_all(timeout_s=1)


async def test_restart_with_broken_factory_marks_error_and_retries(tmp_path: Path) -> None:
    clock = FakeClock()
    registry = FakeRegistry()
    ok_log = DriverLog()

    def _broken(*_args: object) -> object:
        raise RuntimeError("não dá para recriar (fake)")

    # 1ª criação trava; 2ª falha ao recriar; 3ª volta a funcionar
    registry.add(A, hanging_factory(), _broken, ok_factory(ok_log))  # type: ignore[arg-type]
    store = make_store(make_paths(tmp_path), [make_profile(A)])
    manager = EquipmentManager(
        store, registry, InMemoryHistorian(), AsyncBus(), clock, pipeline=fake_pipeline()
    )
    try:
        await manager.start_all()
        await run_for(clock, 5)  # t=4: restart 1 falha ao recriar
        status = manager.status(A)
        assert status.restart_count == 1
        assert status.connection is ConnectionState.ERROR
        assert "recriar o driver" in status.detail_pt
        assert not manager.is_running(A)
        assert A in manager.watchdog.watched(), "continua vigiado para tentar de novo"

        await run_for(clock, 5)  # t=8: restart 2 recria com driver bom
        status = manager.status(A)
        assert status.restart_count == 2
        assert manager.is_running(A)
        assert status.connection is ConnectionState.CONNECTED
        assert ok_log.reads >= 1
    finally:
        await manager.stop_all(timeout_s=1)
