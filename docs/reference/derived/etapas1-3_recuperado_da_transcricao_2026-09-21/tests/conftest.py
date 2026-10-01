"""Fixtures compartilhadas."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """App real, config temporária, banco temporário.

    A pasta de trabalho vira a raiz do projeto para que os caminhos relativos
    da ficha do equipamento e da base de casos resolvam como em produção.
    """
    monkeypatch.chdir(ROOT)
    cfg = yaml.safe_load((ROOT / "config" / "edge.yaml").read_text(encoding="utf-8"))
    cfg["historian_url"] = f"sqlite:///{tmp_path.as_posix()}/api.db"
    cfg["simulator"]["scenario"] = "NORMAL_OPERATION"
    cfg["dev_mode"] = True
    path = tmp_path / "edge_test.yaml"
    path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")

    from forja.api import main as api_main
    monkeypatch.setattr(api_main, "CONFIG_PATH", str(path))
    with TestClient(api_main.app) as c:
        yield c
