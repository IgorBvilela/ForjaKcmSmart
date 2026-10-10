"""Instalação Windows: onde ficam os dados no modo empacotado e a preparação da pasta de dados
(que nunca sobrescreve configuração existente)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from forja.config.paths import resolve_paths
from forja.service.seed import seed_home

pytestmark = pytest.mark.unit


def test_empacotado_sem_forja_home_usa_programdata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("FORJA_HOME", raising=False)
    monkeypatch.delenv("FORJA_DATA_DIR", raising=False)
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    paths = resolve_paths()
    assert paths.home == (tmp_path / "ForjaKCM").resolve()
    assert paths.config_dir == paths.home / "config"
    assert paths.data_dir == paths.home / "var"
    assert paths.logs_dir == paths.home / "var" / "logs"


def test_forja_home_sempre_vence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FORJA_HOME", str(tmp_path / "outra"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert resolve_paths().home == (tmp_path / "outra").resolve()


def _source(tmp: Path) -> Path:
    src = tmp / "semente"
    (src / "config" / "equipment").mkdir(parents=True)
    (src / "config" / "forja.yaml").write_text("schema_version: 1\n", encoding="utf-8")
    (src / "config" / "equipment" / "a.yaml").write_text("id: A\n", encoding="utf-8")
    (src / "knowledge" / "diagnostics").mkdir(parents=True)
    (src / "knowledge" / "diagnostics" / "x.yaml").write_text("ref: x\n", encoding="utf-8")
    return src


def test_init_copia_semente_e_cria_pastas(tmp_path: Path) -> None:
    home = tmp_path / "ForjaKCM"
    created = seed_home(home, source=_source(tmp_path))
    assert (home / "config" / "forja.yaml").is_file()
    assert (home / "knowledge" / "diagnostics" / "x.yaml").is_file()
    assert (home / "var" / "logs").is_dir()
    assert (home / "var" / "backups").is_dir()
    assert "config/forja.yaml" in created


def test_init_nunca_sobrescreve_configuracao_existente(tmp_path: Path) -> None:
    home = tmp_path / "ForjaKCM"
    source = _source(tmp_path)
    seed_home(home, source=source)
    local = home / "config" / "equipment" / "a.yaml"
    local.write_text("id: A\nname: ajustado em campo\n", encoding="utf-8")
    created = seed_home(home, source=source)
    assert "ajustado em campo" in local.read_text(encoding="utf-8")
    assert created == []


def test_init_sem_semente_e_erro_claro(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="semente"):
        seed_home(tmp_path / "home", source=tmp_path / "nao_existe")
