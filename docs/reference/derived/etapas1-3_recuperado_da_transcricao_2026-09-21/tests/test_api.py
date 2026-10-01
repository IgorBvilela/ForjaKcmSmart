"""Testes da API local. Sobe o app real contra um historian temporário."""
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


def test_status_reports_events_and_read_errors(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    assert body["data_is_simulated"] is True
    assert body["events"]["enabled"] is True
    assert "read_errors_total" in body["historian"]
    assert "events_total" in body["historian"]
    assert "consecutive_failed_cycles" in body["acquisition"]


def test_latest_exposes_age_only_for_held_values(client):
    body = client.get("/api/latest").json()
    assert body, "a coleta deveria ter produzido valores"
    for tag, s in body.items():
        assert "quality" in s and "ts" in s
        if s["quality"] == "STALE":
            assert "age_s" in s, f"{tag} STALE sem idade declarada"
        else:
            assert "age_s" not in s


def test_events_endpoint_responds(client):
    r = client.get("/api/events")
    assert r.status_code == 200
    body = r.json()
    assert "events" in body and "count" in body
    # sem contexto por padrão (resposta leve)
    for ev in body["events"]:
        assert "context" not in ev


def test_events_with_context_and_missing_event(client):
    body = client.get("/api/events", params={"include_context": True}).json()
    for ev in body["events"]:
        assert "context" in ev
    assert client.get("/api/events/999999").status_code == 404
    assert client.get("/api/events/999999/diagnosis").status_code == 404


def test_read_errors_endpoint_responds(client):
    body = client.get("/api/read-errors").json()
    assert "read_errors" in body and "count" in body
    for e in body["read_errors"]:
        assert e["quality"] == "COMM_ERROR"


def test_rules_endpoint_lists_versioned_rules(client):
    body = client.get("/api/rules").json()
    assert body["rules"]
    assert all(r["rule_id"] and r["version"] for r in body["rules"])
    assert body["diagnostics_coverage"]["missing"] == []


def test_alarm_catalog_never_claims_universality(client):
    body = client.get("/api/alarms").json()
    assert body["alarms"]
    for a in body["alarms"]:
        assert a["universal"] is False
        assert a["scope"] and a["source"]
        assert "/" in a["key"]


def test_alarm_detail_for_known_and_unknown_code(client):
    known = client.get("/api/alarms/56").json()
    assert known["name"] == "BELTLOAD LOW"
    assert known["known"] is True
    assert known["universal"] is False

    unknown = client.get("/api/alarms/4242").json()
    assert unknown["known"] is False
    assert unknown["source"] == "UNKNOWN"


def test_cases_endpoint_returns_scoped_cases(client):
    body = client.get("/api/cases").json()
    assert body["cases"]
    for c in body["cases"]:
        assert c["scope_note"]


def test_dev_scenarios_carry_scope_with_every_code(client):
    body = client.get("/api/dev/scenarios").json()
    assert body
    for item in body:
        if item["emits_alarm"]:
            assert item["alarm"]["scope"]
            assert item["alarm"]["source"]
            assert item["alarm"]["universal"] is False


def test_api_has_no_write_endpoint_to_the_controller(client):
    """O único POST é a troca de cenário do simulador, e só em dev_mode."""
    from forja.api import main as api_main
    posts = [(r.path, r.methods) for r in api_main.app.routes
             if hasattr(r, "methods") and r.methods & {"POST", "PUT", "PATCH", "DELETE"}]
    assert len(posts) == 1
    assert posts[0][0] == "/api/dev/scenario"
