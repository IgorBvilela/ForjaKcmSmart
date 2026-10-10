"""Plano de leitura Modbus: bit dentro de registrador e opção de leitura uma a uma."""

from __future__ import annotations

import pytest

from forja.domain import (
    CommunicationConfig,
    DataType,
    Endianness,
    EquipmentProfile,
    Mapping,
    MappingEntry,
    MappingValidationError,
    Scale,
)
from forja.normalization.plan import ReadPlanCompiler, layout_of

pytestmark = pytest.mark.unit


def _profile(**options: object) -> EquipmentProfile:
    return EquipmentProfile(
        id="PLANO_TESTE",
        name="Plano de teste",
        mapping_profile="mapa_teste",
        communication=CommunicationConfig(
            driver="modbus_tcp",
            protocol="modbus_tcp",
            ip="127.0.0.1",
            port=1502,
            unit_id=1,
            options=dict(options),
        ),
    )


def _mapping(*entries: MappingEntry) -> Mapping:
    return Mapping(
        mapping_id="mapa_teste", equipment_id="*", driver="modbus_tcp", entries=list(entries)
    )


def _e(tag: str, address: int, dt: DataType = DataType.UINT16, **extra: object) -> MappingEntry:
    return MappingEntry(
        semantic_tag=tag,
        protocol_address={"area": "holding", "address": address, **extra},
        datatype=dt,
        endianness=Endianness.BIG,
        scale=Scale(),
    )


def test_bit_vai_para_o_layout_e_compartilha_o_bloco() -> None:
    plan = ReadPlanCompiler().compile(
        _profile(), _mapping(_e("alarm_active", 10, bit=0), _e("machine_state", 10, bit=5))
    )
    assert len(plan.blocks) == 1
    layout = layout_of(plan.blocks[0])
    assert layout["alarm_active"]["bit"] == 0
    assert layout["machine_state"]["bit"] == 5


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ({"bit": 16}, "bit fora"),
        ({"bit": -1}, "bit fora"),
        ({"bit": 3, "count": 3}, "1 ou 2 registradores"),
    ],
)
def test_bit_invalido_e_recusado(extra: dict[str, object], message: str) -> None:
    with pytest.raises(MappingValidationError, match=message):
        ReadPlanCompiler().compile(_profile(), _mapping(_e("alarm_active", 10, **extra)))


def test_bit_em_coil_e_recusado() -> None:
    entry = MappingEntry(
        semantic_tag="alarm_active",
        protocol_address={"area": "coil", "address": 1, "bit": 0},
        datatype=DataType.BOOL,
        endianness=Endianness.BIG,
    )
    with pytest.raises(MappingValidationError, match="registradores"):
        ReadPlanCompiler().compile(_profile(), _mapping(entry))


def test_leitura_uma_a_uma_quando_o_equipamento_nao_aceita_bloco() -> None:
    entries = (_e("machine_state", 0), _e("alarm_code", 1), _e("stop_by", 2))
    joined = ReadPlanCompiler().compile(_profile(), _mapping(*entries))
    single = ReadPlanCompiler().compile(_profile(block_reads=False), _mapping(*entries))
    assert len(joined.blocks) == 1
    assert [b.count for b in single.blocks] == [1, 1, 1]
