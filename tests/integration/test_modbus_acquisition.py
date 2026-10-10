"""Aquisição real com driver Modbus TCP contra servidor falso, lado a lado com um simulador.

O equipamento Modbus para de responder: vira COMM_ERROR (buraco, nunca valor antigo), o simulador
segue gravando; o servidor volta: a aquisição reconecta sozinha. Só leitura no fio, sempre.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from forja.acquisition.backoff import Backoff
from forja.acquisition.manager import EquipmentManager
from forja.domain import (
    CommunicationConfig,
    ConnectionState,
    DataType,
    Endianness,
    EquipmentProfile,
    KnowledgeState,
    Mapping,
    MappingEntry,
    Quality,
    Scale,
)
from forja.drivers import SIMULATOR_CONTROLS, build_default_registry
from forja.drivers.modbus_tcp._client import READ_FUNCTION_CODES
from forja.infra import AsyncBus, SystemClock
from tests.fixtures.acquisition_fakes import InMemoryHistorian, make_paths, make_store, wait_until
from tests.fixtures.fake_modbus_server import FakeModbusServer, float32_words
from tests.unit.block1_helpers import load_sim_mapping, sim_profile

pytestmark = [pytest.mark.integration, pytest.mark.readonly]

MB = "TESTE_MB_AQ"
SIM = "TESTE_SIM_AQ"


@pytest.fixture
async def server() -> AsyncIterator[FakeModbusServer]:
    srv = await FakeModbusServer(unit_id=1).start()
    w0, w1 = float32_words(950.0)
    srv.holding.update({0: w0, 1: w1, 2: 1})
    try:
        yield srv
    finally:
        await srv.stop()


def modbus_profile(port: int) -> EquipmentProfile:
    return EquipmentProfile(
        id=MB,
        name="Dosador Modbus de teste",
        mapping_profile="teste_mb_aq",
        is_example=True,
        communication=CommunicationConfig(
            driver="modbus_tcp",
            protocol="modbus_tcp",
            ip="127.0.0.1",
            port=port,
            unit_id=1,
            poll_interval_s=0.25,
            timeout_s=0.3,
            connect_timeout_s=0.5,
            stale_after_s=1.0,
        ),
    )


def modbus_mapping() -> Mapping:
    def e(tag: str, address: int, dt: DataType) -> MappingEntry:
        return MappingEntry(
            semantic_tag=tag,
            protocol_address={"area": "holding", "address": address},
            datatype=dt,
            endianness=Endianness.BIG,
            scale=Scale(),
            source="teste: mapa fictício",
            evidence=KnowledgeState.HYPOTHESIS,
        )

    return Mapping(
        mapping_id="teste_mb_aq",
        equipment_id=MB,
        driver="modbus_tcp",
        source="teste",
        entries=[e("mass_flow", 0, DataType.FLOAT32), e("machine_state", 2, DataType.UINT16)],
    )


async def test_modbus_cai_volta_e_nao_derruba_o_simulador(
    tmp_path: Path, server: FakeModbusServer
) -> None:
    historian = InMemoryHistorian()
    sim = sim_profile(SIM, poll_interval_s=0.25)
    store = make_store(
        make_paths(tmp_path),
        [modbus_profile(server.port), sim],
        [modbus_mapping(), load_sim_mapping()],
    )
    manager = EquipmentManager(
        store,
        build_default_registry(),
        historian,
        AsyncBus(),
        SystemClock(),
        backoff_factory=lambda: Backoff(base_s=0.2, max_s=0.4, jitter=0.0),
    )
    await manager.start_all()
    try:
        await wait_until(lambda: len(historian.rows_for(MB, Quality.UNCERTAIN)) >= 4, timeout_s=10)
        values = {s.tag: s.value for s in historian.rows_for(MB, Quality.UNCERTAIN)}
        assert values["mass_flow"] == pytest.approx(950.0)
        assert values["machine_state"] == 1.0
        assert manager.status(MB).connection is ConnectionState.CONNECTED

        server.mode = "silent"
        await wait_until(
            lambda: manager.status(MB).connection is ConnectionState.ERROR, timeout_s=10
        )
        await wait_until(lambda: bool(historian.rows_for(MB, Quality.COMM_ERROR)), timeout_s=10)
        assert all(s.value is None for s in historian.rows_for(MB, Quality.COMM_ERROR))
        sim_before = len(historian.rows_for(SIM))
        await wait_until(lambda: len(historian.rows_for(SIM)) > sim_before + 20, timeout_s=10)

        server.mode = "ok"
        await wait_until(lambda: manager.status(MB).reconnect_count >= 1, timeout_s=15)
        await wait_until(
            lambda: manager.status(MB).connection is ConnectionState.CONNECTED, timeout_s=10
        )
        assert server.functions <= READ_FUNCTION_CODES
    finally:
        await manager.stop_all(timeout_s=2)
        SIMULATOR_CONTROLS.forget(SIM)
