"""Driver Modbus TCP real contra servidor falso local (127.0.0.1, porta efêmera).

Prova: só funções de leitura chegam ao fio; leitura em bloco; 4 ordens de bytes; timeout,
equipamento desligado, exceção Modbus, resposta curta e queda de conexão viram erro honesto;
reconexão funciona; o bloqueio no fio impede qualquer função que não leia.
"""

from __future__ import annotations

import asyncio
import struct
import time
from collections.abc import AsyncIterator

import pytest

from forja.domain import (
    CommunicationConfig,
    ConfigError,
    DataType,
    DriverConnectError,
    DriverReadError,
    DriverSupportState,
    DriverTimeout,
    Endianness,
    EquipmentProfile,
    KnowledgeState,
    Mapping,
    MappingEntry,
    Quality,
    ReadOnlyContractViolation,
    ReadTestStage,
    Scale,
)
from forja.drivers import build_default_registry
from forja.drivers.modbus_tcp import ModbusTcpDriver, modbus_settings
from forja.drivers.modbus_tcp._client import READ_FUNCTION_CODES, ModbusReadClient
from forja.infra import FakeClock, SystemClock
from forja.normalization.normalizer import Normalizer
from forja.normalization.plan import ReadPlanCompiler
from tests.fixtures.fake_modbus_server import FakeModbusServer, float32_words

pytestmark = [pytest.mark.integration, pytest.mark.readonly]

EQ = "TESTE_MODBUS_DRV"
UNIT = 7


@pytest.fixture
async def server() -> AsyncIterator[FakeModbusServer]:
    srv = await FakeModbusServer(unit_id=UNIT).start()
    try:
        yield srv
    finally:
        await srv.stop()


def profile_for(
    port: int, *, timeout_s: float = 0.5, unit_id: int | str = UNIT
) -> EquipmentProfile:
    return EquipmentProfile(
        id=EQ,
        name="Dosador de teste (Modbus)",
        mapping_profile="teste_modbus",
        is_example=True,
        communication=CommunicationConfig(
            driver="modbus_tcp",
            protocol="modbus_tcp",
            ip="127.0.0.1",
            port=port,
            unit_id=unit_id,
            timeout_s=timeout_s,
            connect_timeout_s=1.0,
        ),
    )


def entry(
    tag: str,
    area: str,
    address: int,
    datatype: DataType,
    endianness: Endianness = Endianness.BIG,
    **extra: object,
) -> MappingEntry:
    addr: dict[str, object] = {"area": area, "address": address, **extra}
    return MappingEntry(
        semantic_tag=tag,
        protocol_address=addr,
        datatype=datatype,
        endianness=endianness,
        scale=Scale(),
        source="teste: mapa fictício",
        evidence=KnowledgeState.HYPOTHESIS,
    )


def mapping_of(*entries: MappingEntry) -> Mapping:
    return Mapping(
        mapping_id="teste_modbus",
        equipment_id=EQ,
        driver="modbus_tcp",
        source="teste",
        entries=list(entries),
    )


async def read_once(
    port: int, mapping: Mapping, *, timeout_s: float = 0.5
) -> tuple[ModbusTcpDriver, dict[str, object]]:
    profile = profile_for(port, timeout_s=timeout_s)
    clock = SystemClock()
    driver = ModbusTcpDriver(profile, mapping, clock)
    await driver.connect()
    plan = ReadPlanCompiler().compile(profile, mapping)
    frame = await driver.read(plan)
    batch = Normalizer().normalize(frame, profile, mapping, clock, plan)
    await driver.disconnect()
    return driver, {s.tag: s for s in batch.samples}


# --- leitura correta ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("endianness", "words_of"),
    [
        (Endianness.BIG, lambda v: float32_words(v, "ABCD")),
        (Endianness.BIG_WORD_SWAP, lambda v: float32_words(v, "CDAB")),
        (
            Endianness.LITTLE,
            lambda v: tuple(int.from_bytes(struct.pack("<f", v)[i : i + 2], "big") for i in (0, 2)),
        ),
        (
            Endianness.LITTLE_WORD_SWAP,
            lambda v: tuple(
                int.from_bytes(struct.pack(">f", v)[i : i + 2][::-1], "big") for i in (0, 2)
            ),
        ),
    ],
)
async def test_float32_nas_quatro_ordens_de_bytes(
    server: FakeModbusServer, endianness: Endianness, words_of: object
) -> None:
    w0, w1 = words_of(1234.5)  # type: ignore[operator]
    server.holding.update({10: w0, 11: w1})
    _, samples = await read_once(
        server.port, mapping_of(entry("mass_flow", "holding", 10, DataType.FLOAT32, endianness))
    )
    s = samples["mass_flow"]
    assert s.value == pytest.approx(1234.5)
    assert s.quality is Quality.UNCERTAIN  # mapping não validado contra a tela do KCM
    assert s.raw is not None
    assert len(s.raw) == 4


async def test_tags_contiguas_viram_uma_unica_requisicao(server: FakeModbusServer) -> None:
    server.holding.update({0: 1, 1: 2, 2: 3})
    server.inputs.update({100: 40})
    mapping = mapping_of(
        entry("machine_state", "holding", 0, DataType.UINT16),
        entry("alarm_code", "holding", 1, DataType.UINT16),
        entry("stop_by", "holding", 2, DataType.UINT16),
        entry("rpm", "input", 100, DataType.INT16),
    )
    _, samples = await read_once(server.port, mapping)
    assert [samples[t].value for t in ("machine_state", "alarm_code", "stop_by", "rpm")] == [
        1.0,
        2.0,
        3.0,
        40.0,
    ]
    assert [(r.function, r.start, r.quantity) for r in server.requests] == [
        (3, 0, 3),
        (4, 100, 1),
    ]


async def test_coils_discretes_e_bit_dentro_de_registrador(server: FakeModbusServer) -> None:
    server.coils.update({5: True})
    server.discretes.update({9: False})
    server.holding.update({20: 0b0000_0000_0000_1000})
    mapping = mapping_of(
        entry("alarm_active", "coil", 5, DataType.BOOL),
        entry("control_mode", "discrete", 9, DataType.BOOL),
        entry("machine_state", "holding", 20, DataType.UINT16, bit=3),
    )
    _, samples = await read_once(server.port, mapping)
    assert samples["alarm_active"].value == 1.0
    assert samples["control_mode"].value == 0.0
    assert samples["machine_state"].value == 1.0
    assert server.functions == {1, 2, 3}


async def test_unit_id_vai_no_quadro(server: FakeModbusServer) -> None:
    server.holding.update({0: 9})
    await read_once(server.port, mapping_of(entry("alarm_code", "holding", 0, DataType.UINT16)))
    assert {r.unit for r in server.requests} == {UNIT}


# --- só leitura no fio ------------------------------------------------------------------------


async def test_sessao_inteira_so_usa_funcoes_de_leitura(server: FakeModbusServer) -> None:
    server.holding.update({i: i for i in range(10)})
    server.inputs.update({i: i for i in range(10)})
    server.coils.update({0: True})
    server.discretes.update({0: True})
    mapping = mapping_of(
        entry("mass_flow", "holding", 0, DataType.FLOAT32),
        entry("rpm", "input", 0, DataType.UINT16),
        entry("alarm_active", "coil", 0, DataType.BOOL),
        entry("control_mode", "discrete", 0, DataType.BOOL),
    )
    for _ in range(5):
        await read_once(server.port, mapping)
    assert server.requests
    assert server.functions <= READ_FUNCTION_CODES


async def test_bloqueio_no_fio_impede_funcao_que_nao_le(server: FakeModbusServer) -> None:
    """Mesmo que um código futuro tente, a PDU de outra função nunca vira quadro."""
    from pymodbus.pdu.register_message import WriteSingleRegisterRequest

    client = ModbusReadClient("127.0.0.1", server.port, timeout_s=0.5, connect_timeout_s=1.0)
    await client.open()
    try:
        inner = client._client
        assert inner is not None
        request = WriteSingleRegisterRequest(address=0, registers=[1], dev_id=UNIT)
        with pytest.raises(ReadOnlyContractViolation):
            await inner.execute(False, request)
        await asyncio.sleep(0.1)
        assert server.requests == []
    finally:
        client.close()


def test_cliente_nao_expoe_metodo_de_escrita() -> None:
    public = {n for n in dir(ModbusReadClient) if not n.startswith("_")}
    assert public == {"connected", "open", "close", "read"}


# --- falhas honestas --------------------------------------------------------------------------


async def test_equipamento_desligado_vira_falha_de_conexao() -> None:
    srv = await FakeModbusServer().start()
    port = srv.port
    await srv.stop()
    driver = ModbusTcpDriver(
        profile_for(port), mapping_of(entry("rpm", "holding", 0, DataType.UINT16)), SystemClock()
    )
    with pytest.raises((DriverConnectError, DriverTimeout)):
        await driver.connect()
    health = await driver.health()
    assert health.connected is False
    assert health.consecutive_errors == 1


async def test_silencio_vira_timeout_dentro_do_prazo(server: FakeModbusServer) -> None:
    server.mode = "silent"
    profile = profile_for(server.port, timeout_s=0.3)
    mapping = mapping_of(entry("rpm", "holding", 0, DataType.UINT16))
    driver = ModbusTcpDriver(profile, mapping, SystemClock())
    await driver.connect()
    plan = ReadPlanCompiler().compile(profile, mapping)
    t0 = time.monotonic()
    with pytest.raises(DriverTimeout):
        await driver.read(plan)
    assert time.monotonic() - t0 < 2.0
    await driver.disconnect()


async def test_excecao_modbus_vira_erro_com_texto_em_portugues(server: FakeModbusServer) -> None:
    mapping = mapping_of(entry("rpm", "holding", 500, DataType.UINT16))  # endereço inexistente
    profile = profile_for(server.port)
    driver = ModbusTcpDriver(profile, mapping, SystemClock())
    await driver.connect()
    with pytest.raises(DriverReadError, match="endereço não existe"):
        await driver.read(ReadPlanCompiler().compile(profile, mapping))
    await driver.disconnect()


async def test_resposta_curta_e_rejeitada(server: FakeModbusServer) -> None:
    server.holding.update({0: 1, 1: 2})
    server.mode = "short"
    mapping = mapping_of(entry("mass_flow", "holding", 0, DataType.FLOAT32))
    profile = profile_for(server.port)
    driver = ModbusTcpDriver(profile, mapping, SystemClock())
    await driver.connect()
    with pytest.raises((DriverReadError, DriverTimeout)):
        await driver.read(ReadPlanCompiler().compile(profile, mapping))
    await driver.disconnect()


async def test_queda_de_conexao_e_reconexao(server: FakeModbusServer) -> None:
    server.holding.update({0: 77})
    mapping = mapping_of(entry("alarm_code", "holding", 0, DataType.UINT16))
    profile = profile_for(server.port, timeout_s=0.3)
    driver = ModbusTcpDriver(profile, mapping, SystemClock())
    plan = ReadPlanCompiler().compile(profile, mapping)
    await driver.connect()
    assert (await driver.read(plan)).blocks
    await server.drop_clients()
    await asyncio.sleep(0.05)
    with pytest.raises((DriverConnectError, DriverReadError, DriverTimeout)):
        await driver.read(plan)
    await driver.disconnect()
    await driver.connect()
    frame = await driver.read(plan)
    assert frame.blocks
    assert server.connections == 2
    await driver.disconnect()


# --- configuração e registro --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"ip": "UNKNOWN"}, "IP não informado"),
        ({"ip": "999.1.1.1"}, "IP inválido"),
        ({"port": "UNKNOWN"}, "porta não informada"),
        ({"unit_id": "UNKNOWN"}, "unit id"),
        ({"unit_id": 300}, "unit id fora"),
    ],
)
def test_configuracao_incompleta_e_recusada_com_motivo(
    changes: dict[str, object], message: str
) -> None:
    base = profile_for(502)
    comm = base.communication.model_copy(update=changes)
    profile = base.model_copy(update={"communication": comm})
    with pytest.raises(ConfigError, match=message):
        modbus_settings(profile)


def test_registro_cria_driver_experimental_com_contrato() -> None:
    registry = build_default_registry()
    info = registry.support()["modbus_tcp"]
    assert info.state is DriverSupportState.EXPERIMENTAL
    assert "pendente" in info.reason_pt
    driver = registry.create(
        profile_for(502), mapping_of(entry("rpm", "holding", 0, DataType.UINT16)), FakeClock()
    )
    assert driver.name == "modbus_tcp"
    assert driver.capabilities().support_state is DriverSupportState.EXPERIMENTAL


async def test_teste_somente_leitura_ponta_a_ponta(server: FakeModbusServer) -> None:
    from forja.acquisition.loop import default_pipeline
    from forja.acquisition.test_read import run_read_test

    server.holding.update(dict(enumerate(float32_words(812.25))))
    mapping = mapping_of(entry("mass_flow", "holding", 0, DataType.FLOAT32))
    result = await run_read_test(
        profile_for(server.port),
        mapping,
        registry=build_default_registry(),
        pipeline=default_pipeline(),
        clock=SystemClock(),
    )
    assert result.final is ReadTestStage.READ_OBTAINED
    assert result.values["mass_flow"].value == pytest.approx(812.25)
    assert [s[0] for s in result.stages][:3] == [
        ReadTestStage.CONNECTING,
        ReadTestStage.HANDSHAKE,
        ReadTestStage.SESSION_CREATED,
    ]
    assert server.functions == {3}


async def test_teste_somente_leitura_com_endereco_errado_e_honesto(
    server: FakeModbusServer,
) -> None:
    from forja.acquisition.loop import default_pipeline
    from forja.acquisition.test_read import run_read_test

    result = await run_read_test(
        profile_for(server.port),
        mapping_of(entry("mass_flow", "holding", 900, DataType.FLOAT32)),
        registry=build_default_registry(),
        pipeline=default_pipeline(),
        clock=SystemClock(),
    )
    assert result.final is ReadTestStage.INVALID_RESPONSE
    assert result.error_pt is not None
    assert result.values == {}
