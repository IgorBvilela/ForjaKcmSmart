"""Gravação de configuração: atômica, com histórico da versão anterior e conflito detectado."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from forja.config.loader import load_mapping, load_profile
from forja.config.paths import ForjaPaths
from forja.config.writer import ConfigConflict, ConfigWriter, config_hash
from forja.domain import (
    CommunicationConfig,
    ConfigError,
    EquipmentProfile,
    Mapping,
    MappingEntry,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 10, 15, 0, 0, tzinfo=UTC)


def _paths(tmp: Path) -> ForjaPaths:
    paths = ForjaPaths(
        home=tmp,
        config_dir=tmp / "config",
        knowledge_dir=tmp / "knowledge",
        data_dir=tmp / "var",
        logs_dir=tmp / "var" / "logs",
        backups_dir=tmp / "var" / "backups",
    )
    paths.equipment_dir.mkdir(parents=True)
    paths.mappings_dir.mkdir(parents=True)
    return paths


def _profile(**comm: object) -> EquipmentProfile:
    return EquipmentProfile(
        id="EQUIP_TESTE",
        name="Equipamento de teste",
        mapping_profile="equip_teste",
        communication=CommunicationConfig(**comm),  # type: ignore[arg-type]
    )


def _mapping(version: int = 1) -> Mapping:
    return Mapping(
        mapping_id="equip_teste",
        version=version,
        equipment_id="EQUIP_TESTE",
        driver="modbus_tcp",
        entries=[MappingEntry(semantic_tag="mass_flow")],
    )


def test_perfil_novo_e_gravado_e_relido_igual(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    writer = ConfigWriter(paths)
    profile = _profile(driver="UNKNOWN")
    saved = writer.save_profile(profile, expected_hash=None, now=NOW)
    assert saved.path == paths.equipment_dir / "equip_teste.yaml"
    assert load_profile(saved.path) == profile
    assert saved.config_hash == config_hash(profile)
    assert saved.previous_path is None


def test_perfil_existente_guarda_a_versao_anterior_no_historico(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    original = paths.equipment_dir / "qualquer_nome.yaml"
    original.write_text(
        "# comentário de campo que precisa sobreviver no histórico\n"
        + yaml.safe_dump(_profile(driver="UNKNOWN").model_dump(mode="json")),
        encoding="utf-8",
    )
    writer = ConfigWriter(paths)
    current = load_profile(original)
    updated = _profile(driver="modbus_tcp", protocol="modbus_tcp", ip="127.0.0.1", port=502)
    saved = writer.save_profile(updated, expected_hash=config_hash(current), now=NOW)
    assert saved.path == original  # o arquivo existente é atualizado, não duplicado
    assert load_profile(original) == updated
    assert saved.previous_path is not None
    assert saved.previous_path.read_text(encoding="utf-8").startswith("# comentário de campo")
    assert paths.config_dir / "_history" in saved.previous_path.parents


def test_hash_divergente_e_conflito(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    writer = ConfigWriter(paths)
    writer.save_profile(_profile(driver="UNKNOWN"), expected_hash=None, now=NOW)
    with pytest.raises(ConfigConflict):
        writer.save_profile(_profile(driver="simulator"), expected_hash="0" * 64, now=NOW)


def test_mapping_ganha_versao_nova_e_conflito_de_versao(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    writer = ConfigWriter(paths)
    first = writer.save_mapping(_mapping(), expected_version=None, now=NOW)
    assert first.mapping.version == 1
    second = writer.save_mapping(_mapping(), expected_version=1, now=NOW)
    assert second.mapping.version == 2
    assert load_mapping(second.path).version == 2
    assert second.previous_path is not None
    with pytest.raises(ConfigConflict):
        writer.save_mapping(_mapping(), expected_version=1, now=NOW)


def test_id_invalido_para_nome_de_arquivo_e_recusado(tmp_path: Path) -> None:
    writer = ConfigWriter(_paths(tmp_path))
    sneaky = Mapping.model_construct(mapping_id="../fora", equipment_id="X", entries=[])
    with pytest.raises(ConfigError):
        writer.save_mapping(sneaky, expected_version=None, now=NOW)
    assert not (tmp_path / "config" / "fora.yaml").exists()


def test_gravacao_e_atomica_sem_arquivo_temporario_sobrando(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    writer = ConfigWriter(paths)
    writer.save_profile(_profile(driver="UNKNOWN"), expected_hash=None, now=NOW)
    leftovers = [p.name for p in paths.equipment_dir.iterdir() if not p.name.endswith(".yaml")]
    assert leftovers == []
