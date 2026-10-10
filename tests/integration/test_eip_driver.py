"""Driver EtherNet/IP real contra respondedor falso local (127.0.0.1, porta efêmera).

Prova: só RegisterSession/UnRegisterSession/ListIdentity/SendRRData no encapsulamento e só
Get_Attribute_Single no CIP; uma requisição por atributo; classe/instância/atributo vêm do
mapping; falhas viram erro honesto; o bloqueio impede montar qualquer serviço que não leia.
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
from forja.drivers.ethernet_ip import EthernetIpDriver, eip_settings
from forja.drivers.ethernet_ip._client import (
    ENCAP_COMMANDS,
    READ_SERVICES,
    EipReadClient,
    cip_read_request,
    encapsulate,
    logical_path,
)
from forja.infra import FakeClock, SystemClock
from forja.normalization.normalizer import Normalizer
from forja.normalization.plan import ReadPlanCompiler
from tests.fixtures.fake_eip_server import FakeEipServer

pytestmark = [pytest.mark.integration, pytest.mark.readonly]

EQ = "TESTE_EIP_DRV"
# Números de teste. Nenhum vem de equipamento real.
CLS, INST, ATTR = 4, 150, 3


@pytest.fixture
async def server() -> AsyncIterator[FakeEipServer]:
    srv = await FakeEipServer().start()
    data = struct.pack("<f", 1234.5) + struct.pack("<h", -7) + bytes((0b0000_0100, 9))
    srv.attributes[(CLS, INST, ATTR)] = data
    srv.attributes[(CLS, INST + 1, ATTR)] = struct.pack("<f", 2.25)
    try:
        yield srv
    finally:
        await srv.stop()


def profile_for(port: int, *, timeout_s: float = 0.5) -> EquipmentProfile:
    return EquipmentProfile(
        id=EQ,
        name="Dosador de teste (EtherNet/IP)",
        mapping_profile="teste_eip",
        is_example=True,
        communication=CommunicationConfig(
            driver="ethernet_ip",
            protocol="ethernet_ip",
            ip="127.0.0.1",
            port=port,
            timeout_s=timeout_s,
            connect_timeout_s=1.0,
        ),
    )


def entry(
    tag: str, dt: DataType, offset: int, instance: int = INST, **extra: object
) -> MappingEntry:
    return MappingEntry(
        semantic_tag=tag,
        protocol_address={
            "kind": "assembly",
            "class": CLS,
            "instance": instance,
            "attribute": ATTR,
            "offset": offset,
            **extra,
        },
        datatype=dt,
        endianness=Endianness.LITTLE,
        scale=Scale(),
        source="teste: mapa fictício",
        evidence=KnowledgeState.HYPOTHESIS,
    )


def mapping_of(*entries: MappingEntry) -> Mapping:
    return Mapping(
        mapping_id="teste_eip",
        equipment_id=EQ,
        driver="ethernet_ip",
        source="teste",
        entries=list(entries),
    )


async def read_once(port: int, mapping: Mapping) -> tuple[EthernetIpDriver, dict[str, object]]:
    profile = profile_for(port)
    clock = SystemClock()
    driver = EthernetIpDriver(profile, mapping, clock)
    await driver.connect()
    plan = ReadPlanCompiler().compile(profile, mapping)
    frame = await driver.read(plan)
    batch = Normalizer().normalize(frame, profile, mapping, clock, plan)
    await driver.disconnect()
    return driver, {s.tag: s for s in batch.samples}


async def test_le_float_int_e_bit_do_atributo(server: FakeEipServer) -> None:
    mapping = mapping_of(
        entry("mass_flow", DataType.FLOAT32, 0),
        entry("rpm", DataType.INT16, 4),
        entry("alarm_active", DataType.UINT8, 6, bit=2, length=1),
        entry("alarm_code", DataType.UINT8, 7, length=1),
        entry("belt_load", DataType.FLOAT32, 0, instance=INST + 1),
    )
    _, samples = await read_once(server.port, mapping)
    assert samples["mass_flow"].value == pytest.approx(1234.5)
    assert samples["rpm"].value == -7.0
    assert samples["alarm_active"].value == 1.0
    assert samples["alarm_code"].value == 9.0
    assert samples["belt_load"].value == pytest.approx(2.25)
    assert samples["mass_flow"].quality is Quality.UNCERTAIN
    reads = [r for r in server.requests if r.command == 0x6F]
    assert [(r.service, r.class_id, r.instance, r.attribute) for r in reads] == [
        (0x0E, CLS, INST, ATTR),
        (0x0E, CLS, INST + 1, ATTR),
    ]


async def test_sessao_e_aberta_e_encerrada_so_com_comandos_permitidos(
    server: FakeEipServer,
) -> None:
    await read_once(server.port, mapping_of(entry("mass_flow", DataType.FLOAT32, 0)))
    await asyncio.sleep(0.05)
    assert server.commands <= ENCAP_COMMANDS
    assert {0x65, 0x6F, 0x66} <= server.commands
    assert server.services <= READ_SERVICES


async def test_identidade_do_dispositivo_aparece_na_saude(server: FakeEipServer) -> None:
    driver = EthernetIpDriver(
        profile_for(server.port), mapping_of(entry("mass_flow", DataType.FLOAT32, 0)), SystemClock()
    )
    await driver.connect()
    health = await driver.health()
    assert health.connected is True
    assert "Dispositivo de teste" in health.detail_pt
    await driver.disconnect()


def test_bloqueio_recusa_servico_e_comando_que_nao_leem() -> None:
    path = logical_path(CLS, INST, ATTR)
    with pytest.raises(ReadOnlyContractViolation):
        cip_read_request(0x10, path)  # serviço de alteração de atributo
    with pytest.raises(ReadOnlyContractViolation):
        cip_read_request(0x4C, path)  # serviço de tag de outro fabricante
    with pytest.raises(ReadOnlyContractViolation):
        encapsulate(0x70, 1, b"", bytes(8))  # SendUnitData (conexão de I/O)
    assert cip_read_request(0x0E, path)[0] == 0x0E


def test_cliente_nao_expoe_metodo_de_escrita() -> None:
    public = {n for n in dir(EipReadClient) if not n.startswith("_")}
    assert public == {"connected", "open", "close", "identity", "read_attribute", "read_all"}


def test_caminho_logico_8_e_16_bits() -> None:
    assert logical_path(4, 100, 3) == bytes((0x20, 4, 0x24, 100, 0x30, 3))
    assert logical_path(4, 0x1234, 3) == bytes((0x20, 4, 0x25, 0, 0x34, 0x12, 0x30, 3))


async def test_atributo_inexistente_vira_erro_em_portugues(server: FakeEipServer) -> None:
    mapping = mapping_of(entry("mass_flow", DataType.FLOAT32, 0, instance=999))
    profile = profile_for(server.port)
    driver = EthernetIpDriver(profile, mapping, SystemClock())
    await driver.connect()
    with pytest.raises(DriverReadError, match="atributo não suportado"):
        await driver.read(ReadPlanCompiler().compile(profile, mapping))
    await driver.disconnect()


async def test_atributo_menor_que_o_mapping_e_recusado(server: FakeEipServer) -> None:
    mapping = mapping_of(entry("mass_flow", DataType.FLOAT32, 6))  # 6+4 > 8 bytes
    profile = profile_for(server.port)
    driver = EthernetIpDriver(profile, mapping, SystemClock())
    await driver.connect()
    with pytest.raises(DriverReadError, match="devolveu 8 bytes"):
        await driver.read(ReadPlanCompiler().compile(profile, mapping))
    await driver.disconnect()


async def test_silencio_vira_timeout(server: FakeEipServer) -> None:
    server.mode = "silent"
    mapping = mapping_of(entry("mass_flow", DataType.FLOAT32, 0))
    profile = profile_for(server.port, timeout_s=0.3)
    driver = EthernetIpDriver(profile, mapping, SystemClock())
    await driver.connect()
    t0 = time.monotonic()
    with pytest.raises(DriverTimeout):
        await driver.read(ReadPlanCompiler().compile(profile, mapping))
    assert time.monotonic() - t0 < 2.0
    await driver.disconnect()


async def test_resposta_invalida_e_queda(server: FakeEipServer) -> None:
    mapping = mapping_of(entry("mass_flow", DataType.FLOAT32, 0))
    profile = profile_for(server.port)
    plan = ReadPlanCompiler().compile(profile, mapping)
    driver = EthernetIpDriver(profile, mapping, SystemClock())
    await driver.connect()
    server.mode = "garbage"
    with pytest.raises(DriverReadError):
        await driver.read(plan)
    await driver.disconnect()
    server.mode = "ok"
    await driver.connect()
    assert (await driver.read(plan)).blocks
    await server.drop_clients()
    await asyncio.sleep(0.05)
    with pytest.raises((DriverConnectError, DriverReadError, DriverTimeout)):
        await driver.read(plan)
    await driver.disconnect()
    await driver.connect()
    assert (await driver.read(plan)).blocks
    await driver.disconnect()


async def test_dispositivo_desligado_vira_falha_de_conexao() -> None:
    srv = await FakeEipServer().start()
    port = srv.port
    await srv.stop()
    driver = EthernetIpDriver(
        profile_for(port), mapping_of(entry("mass_flow", DataType.FLOAT32, 0)), SystemClock()
    )
    with pytest.raises((DriverConnectError, DriverTimeout)):
        await driver.connect()


@pytest.mark.parametrize(
    ("changes", "message"),
    [({"ip": "UNKNOWN"}, "IP não informado"), ({"port": "UNKNOWN"}, "porta não informada")],
)
def test_configuracao_incompleta_e_recusada(changes: dict[str, object], message: str) -> None:
    base = profile_for(44818)
    profile = base.model_copy(
        update={"communication": base.communication.model_copy(update=changes)}
    )
    with pytest.raises(ConfigError, match=message):
        eip_settings(profile)


def test_registro_cria_driver_experimental() -> None:
    registry = build_default_registry()
    info = registry.support()["ethernet_ip"]
    assert info.state is DriverSupportState.EXPERIMENTAL
    driver = registry.create(
        profile_for(44818), mapping_of(entry("mass_flow", DataType.FLOAT32, 0)), FakeClock()
    )
    assert driver.name == "ethernet_ip"
    assert driver.capabilities().supports_device_identification is True


async def test_teste_somente_leitura_ponta_a_ponta(server: FakeEipServer) -> None:
    from forja.acquisition.loop import default_pipeline
    from forja.acquisition.test_read import run_read_test

    mapping = Mapping.model_validate(
        mapping_of(entry("mass_flow", DataType.FLOAT32, 0)).model_dump(mode="json")
    )
    result = await run_read_test(
        profile_for(server.port),
        mapping,
        registry=build_default_registry(),
        pipeline=default_pipeline(),
        clock=SystemClock(),
    )
    assert result.final is ReadTestStage.READ_OBTAINED
    assert result.values["mass_flow"].value == pytest.approx(1234.5)
    assert server.services == {0x0E}
