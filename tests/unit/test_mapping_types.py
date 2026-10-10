"""Mapping lido de YAML/JSON: tipos de dado e ordem de bytes viram os tipos certos.

Sem isso, todo driver real decodificaria errado (texto em vez de DataType): float32 seria lido
com 1 registrador e toda leitura sairia 'Inválido'. Erro de digitação é recusado.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from forja.config.loader import load_mapping
from forja.domain import DataType, Endianness, MappingEntry, MappingValidationError

pytestmark = pytest.mark.unit


def test_texto_vira_datatype_e_endianness() -> None:
    e = MappingEntry.model_validate(
        {
            "semantic_tag": "mass_flow",
            "protocol_address": {"area": "holding", "address": 0},
            "datatype": "FLOAT32",
            "endianness": "big_word_swap",
        }
    )
    assert e.datatype is DataType.FLOAT32
    assert e.endianness is Endianness.BIG_WORD_SWAP


def test_unknown_continua_unknown() -> None:
    e = MappingEntry.model_validate({"semantic_tag": "rpm"})
    assert e.datatype == "UNKNOWN"
    assert e.endianness == "UNKNOWN"
    assert not e.is_readable


@pytest.mark.parametrize(("field", "value"), [("datatype", "flaot32"), ("endianness", "abcd")])
def test_erro_de_digitacao_e_recusado(field: str, value: str) -> None:
    with pytest.raises(ValueError, match="desconhecid"):
        MappingEntry.model_validate({"semantic_tag": "rpm", field: value})


def test_arquivo_yaml_produz_tipos_prontos_para_decodificar(tmp_path: Path) -> None:
    path = tmp_path / "m.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "mapping_id": "m_teste",
                "equipment_id": "EQ",
                "driver": "modbus_tcp",
                "entries": [
                    {
                        "semantic_tag": "mass_flow",
                        "protocol_address": {"area": "holding", "address": 4},
                        "datatype": "float32",
                        "endianness": "big",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    entry = load_mapping(path).entries[0]
    assert entry.datatype is DataType.FLOAT32
    assert entry.endianness is Endianness.BIG


def test_arquivo_yaml_com_tipo_invalido_e_erro_de_mapping(tmp_path: Path) -> None:
    path = tmp_path / "m.yaml"
    path.write_text(
        "mapping_id: m_teste\nequipment_id: EQ\nentries:\n"
        "  - {semantic_tag: rpm, datatype: inteiro}\n",
        encoding="utf-8",
    )
    with pytest.raises(MappingValidationError, match="datatype"):
        load_mapping(path)
