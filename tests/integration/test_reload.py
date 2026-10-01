"""reload(id) recarrega perfil e mapping de UM equipamento sem tocar nos demais."""

from __future__ import annotations

from pathlib import Path

import pytest

from forja.acquisition.manager import EquipmentManager
from forja.domain import ConfigError, ConnectionState, Quality
from forja.infra import AsyncBus, FakeClock
from tests.fixtures.acquisition_fakes import (
    TAGS,
    DriverLog,
    FakeRegistry,
    InMemoryHistorian,
    fake_pipeline,
    make_mapping,
    make_paths,
    make_profile,
    make_store,
    ok_factory,
    run_for,
)

pytestmark = pytest.mark.integration

A, B, C = "EQ_A", "EQ_B", "EQ_C"


def _rig(tmp_path: Path) -> tuple[EquipmentManager, FakeRegistry, FakeClock, DriverLog]:
    clock = FakeClock()
    registry = FakeRegistry()
    log_a = DriverLog()
    registry.add(A, ok_factory(log_a))
    registry.set_default(ok_factory())
    store = make_store(
        make_paths(tmp_path),
        [make_profile(A), make_profile(B), make_profile(C)],
        [make_mapping("fake_wbf"), make_mapping("fake_two_tags", tags=("mass_flow", "rpm"))],
    )
    manager = EquipmentManager(
        store, registry, InMemoryHistorian(), AsyncBus(), clock, pipeline=fake_pipeline()
    )
    return manager, registry, clock, log_a


async def test_reload_changes_one_equipment_only(tmp_path: Path) -> None:
    manager, registry, clock, log_a = _rig(tmp_path)
    try:
        await manager.start_all()
        await run_for(clock, 3)
        task_a, task_c = manager.task_of(A), manager.task_of(C)
        old_task_b = manager.task_of(B)
        reads_a_before = log_a.reads
        assert set(manager.live(B).samples) == set(TAGS)

        new_profile = make_profile(B, mapping_id="fake_two_tags", poll_interval_s=2.0)
        await manager.reload(
            B, profile=new_profile, mapping=make_mapping("fake_two_tags", ("mass_flow", "rpm"))
        )
        await run_for(clock, 4)

        # B mudou
        assert manager.task_of(B) is not old_task_b
        assert old_task_b is not None
        assert old_task_b.done()
        assert registry.create_calls[B] == 2
        assert manager.profile(B).communication.poll_interval_s == 2.0
        assert set(manager.live(B).samples) == {"mass_flow", "rpm"}
        assert manager.status(B).connection is ConnectionState.CONNECTED
        # A e C não foram tocados: mesma task, mesmo driver, continuam lendo
        assert manager.task_of(A) is task_a
        assert manager.task_of(C) is task_c
        assert registry.create_calls[A] == 1
        assert registry.create_calls[C] == 1
        assert log_a.reads > reads_a_before
        assert manager.status(A).reconnect_count == 0
        assert manager.status(A).restart_count == 0
    finally:
        await manager.stop_all(timeout_s=1)


async def test_reload_from_disk(tmp_path: Path) -> None:
    manager, registry, clock, _ = _rig(tmp_path)
    paths = make_paths(tmp_path)
    (paths.equipment_dir / "b.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                f"id: {B}",
                'name: "Equipamento B recarregado"',
                "mapping_profile: fake_disk",
                "is_example: true",
                "communication:",
                "  driver: simulator",
                "  poll_interval_s: 3.0",
                "  stale_after_s: 9.0",
            ]
        ),
        encoding="utf-8",
    )
    (paths.mappings_dir / "fake_disk.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                "mapping_id: fake_disk",
                "version: 2",
                'equipment_id: "*"',
                "driver: simulator",
                "source: disco de teste",
                "entries:",
                "  - { semantic_tag: rpm, protocol_address: 'sim:rpm', datatype: float32,"
                " endianness: big, scale: { factor: 1, offset: 0 }, source: teste,"
                " evidence: FORJA_RULE }",
            ]
        ),
        encoding="utf-8",
    )
    try:
        await manager.start_all()
        await run_for(clock, 2)
        await manager.reload(B)
        await run_for(clock, 4)
        prof = manager.profile(B)
        assert prof.name == "Equipamento B recarregado"
        assert prof.communication.poll_interval_s == 3.0
        assert set(manager.live(B).samples) == {"rpm"}
        assert manager.live(B).samples["rpm"].quality is Quality.SIMULATED
        assert manager.live(B).samples["rpm"].source == "driver:simulator:fake_disk@2"
        assert registry.create_calls[A] == 1
    finally:
        await manager.stop_all(timeout_s=1)


async def test_reload_rejects_wrong_id_and_unknown_equipment(tmp_path: Path) -> None:
    manager, _, clock, _ = _rig(tmp_path)
    try:
        await manager.start_all()
        with pytest.raises(ConfigError):
            await manager.reload(B, profile=make_profile(C), mapping=make_mapping())
        with pytest.raises(ConfigError):
            await manager.reload(
                B, profile=make_profile(B, mapping_id="x_y"), mapping=make_mapping("outro")
            )
        with pytest.raises(KeyError):
            await manager.reload("EQ_NAO_EXISTE")
        # B segue rodando normalmente
        await run_for(clock, 2)
        assert manager.is_running(B)
        assert manager.status(B).connection is ConnectionState.CONNECTED
    finally:
        await manager.stop_all(timeout_s=1)


async def test_reload_rolls_back_when_new_driver_fails(tmp_path: Path) -> None:
    manager, registry, clock, _ = _rig(tmp_path)

    def _broken(*_args: object) -> object:
        raise ValueError("perfil novo inválido (fake)")

    try:
        await manager.start_all()
        await run_for(clock, 2)
        registry.add(B, _broken, ok_factory())  # type: ignore[arg-type]
        bad_profile = make_profile(B, poll_interval_s=7.0)
        with pytest.raises(ValueError):
            await manager.reload(B, profile=bad_profile, mapping=make_mapping())
        await run_for(clock, 3)
        assert manager.profile(B).communication.poll_interval_s == 1.0, "voltou ao antigo"
        assert manager.is_running(B)
        assert manager.status(B).connection is ConnectionState.CONNECTED
        assert manager.is_running(A)
        assert manager.is_running(C)
    finally:
        await manager.stop_all(timeout_s=1)


async def test_reload_to_not_configured_driver(tmp_path: Path) -> None:
    manager, _, clock, _ = _rig(tmp_path)
    try:
        await manager.start_all()
        await run_for(clock, 2)
        await manager.reload(
            B, profile=make_profile(B, driver="modbus_tcp"), mapping=make_mapping()
        )
        await run_for(clock, 2)
        status = manager.status(B)
        assert status.connection is ConnectionState.NOT_CONFIGURED
        assert status.driver == "modbus_tcp"
        assert not manager.is_running(B)
        assert manager.is_running(A)
        assert manager.is_running(C)
    finally:
        await manager.stop_all(timeout_s=1)
