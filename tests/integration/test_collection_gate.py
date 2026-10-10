"""Porteira da coleta (ADR 0026) na partida e na recarga: driver real só lê o KCM depois de um
teste somente leitura bem-sucedido da MESMA configuração, inclusive com YAML editado à mão."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from forja.acquisition.manager import GATE_FAILED_PT, EquipmentManager
from forja.domain import ConnectionState, EquipmentProfile, Mapping
from forja.drivers import SIMULATOR_CONTROLS, build_default_registry
from forja.infra import AsyncBus, SystemClock
from forja.service.commcenter import (
    READ_TEST_PENDING_PT,
    collection_gate_for,
    reading_fingerprint,
)
from tests.fixtures.acquisition_fakes import InMemoryHistorian, make_paths, make_store, wait_until
from tests.fixtures.fake_modbus_server import FakeModbusServer, float32_words
from tests.integration.test_modbus_acquisition import MB, SIM, modbus_mapping, modbus_profile
from tests.unit.block1_helpers import load_sim_mapping, sim_profile

pytestmark = [pytest.mark.integration, pytest.mark.readonly]


class ReadTests:
    """Registro de testes somente leitura em memória (mesma interface do core store)."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def record(self, profile: EquipmentProfile, mapping: Mapping, *, success: bool) -> None:
        self.rows.insert(
            0,
            {
                "equipment_id": profile.id,
                "success": success,
                "fingerprint": reading_fingerprint(profile, mapping),
            },
        )

    async def list_read_tests(self, equipment_id: str, limit: int = 50) -> list[dict[str, Any]]:
        return [r for r in self.rows if r["equipment_id"] == equipment_id][:limit]


@pytest.fixture
async def server() -> AsyncIterator[FakeModbusServer]:
    srv = await FakeModbusServer(unit_id=1).start()
    w0, w1 = float32_words(950.0)
    srv.holding.update({0: w0, 1: w1, 2: 1})
    try:
        yield srv
    finally:
        await srv.stop()


def manager_for(tmp_path: Path, port: int, gate: Any) -> tuple[EquipmentManager, InMemoryHistorian]:
    historian = InMemoryHistorian()
    store = make_store(
        make_paths(tmp_path),
        [modbus_profile(port), sim_profile(SIM, poll_interval_s=0.25)],
        [modbus_mapping(), load_sim_mapping()],
    )
    manager = EquipmentManager(
        store, build_default_registry(), historian, AsyncBus(), SystemClock(), collection_gate=gate
    )
    return manager, historian


async def test_sem_teste_o_driver_real_nao_conecta_e_o_simulador_segue(
    tmp_path: Path, server: FakeModbusServer
) -> None:
    tests = ReadTests()
    manager, historian = manager_for(tmp_path, server.port, collection_gate_for(tests))
    await manager.start_all()
    try:
        await wait_until(lambda: len(historian.rows_for(SIM)) >= 3, timeout_s=10)
        status = manager.status(MB)
        assert status.connection is ConnectionState.DISCONNECTED
        assert status.detail_pt == READ_TEST_PENDING_PT
        assert manager.driver_of(MB) is None
        assert historian.rows_for(MB) == []
        assert server.functions == set(), "nenhum pacote pode ter ido ao equipamento"
    finally:
        await manager.stop_all(timeout_s=2)
        SIMULATOR_CONTROLS.forget(SIM)


async def test_teste_da_mesma_configuracao_libera_e_de_outra_nao(
    tmp_path: Path, server: FakeModbusServer
) -> None:
    tests = ReadTests()
    profile, mapping = modbus_profile(server.port), modbus_mapping()
    other = profile.model_copy(
        update={"communication": profile.communication.model_copy(update={"port": 1})}
    )
    tests.record(other, mapping, success=True)
    tests.record(profile, mapping, success=False)
    manager, historian = manager_for(tmp_path, server.port, collection_gate_for(tests))
    await manager.start_all()
    try:
        assert manager.status(MB).detail_pt == READ_TEST_PENDING_PT

        tests.record(profile, mapping, success=True)
        await manager.reload(MB, profile=profile, mapping=mapping)
        await wait_until(
            lambda: manager.status(MB).connection is ConnectionState.CONNECTED, timeout_s=10
        )
        await wait_until(lambda: bool(historian.rows_for(MB)), timeout_s=10)
    finally:
        await manager.stop_all(timeout_s=2)
        SIMULATOR_CONTROLS.forget(SIM)


async def test_falha_na_conferencia_bloqueia(tmp_path: Path, server: FakeModbusServer) -> None:
    async def broken(profile: EquipmentProfile, mapping: Mapping) -> str | None:
        raise RuntimeError("banco indisponível")

    manager, _ = manager_for(tmp_path, server.port, broken)
    await manager.start_all()
    try:
        assert manager.status(MB).detail_pt == GATE_FAILED_PT
        assert manager.driver_of(MB) is None
        assert server.functions == set()
    finally:
        await manager.stop_all(timeout_s=2)
        SIMULATOR_CONTROLS.forget(SIM)


async def test_simulador_nao_precisa_de_teste() -> None:
    gate = collection_gate_for(ReadTests())
    assert await gate(sim_profile(SIM), load_sim_mapping()) is None
