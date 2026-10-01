"""Comunicação: suporte honesto por driver e teste somente leitura (409 para UNSUPPORTED)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from forja.domain import ConfigError, NotConfigured, ReadTestStage
from tests.integration.api_testkit import (
    MODBUS_TEST_ID,
    NEEDS_CONFIG_TEST_ID,
    TEST_MAPPING_ID,
    ApiWorld,
    FakeReadTestResult,
)

pytestmark = pytest.mark.integration

FIELD_CONFIG_PT = "Disponível após configuração de campo"


def _body(world: ApiWorld, equipment_id: str, mapping_id: str | None = None) -> dict[str, Any]:
    profile = world.store.profiles[equipment_id]
    mapping = world.store.mappings[mapping_id or profile.mapping_profile]
    return {
        "profile": profile.model_dump(mode="json"),
        "mapping": mapping.model_dump(mode="json"),
    }


async def test_drivers_never_claim_false_availability(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    resp = await client.get("/api/v1/communication/drivers")
    assert resp.status_code == 200
    body = resp.json()
    assert body["read_only"] is True
    drivers = body["drivers"]
    assert drivers["simulator"]["state"] == "AVAILABLE"
    assert drivers["simulator"]["state_pt"] == "Disponível"
    assert drivers["modbus_tcp"]["state"] == "UNSUPPORTED"
    assert drivers["modbus_tcp"]["state_pt"] == "Não suportado"
    assert drivers["ethernet_ip"]["state"] == "UNSUPPORTED"
    by_id = {e["equipment_id"]: e for e in body["equipments"]}
    assert set(by_id) == set(world.store.profiles)
    assert by_id[MODBUS_TEST_ID]["support_state"] == "UNSUPPORTED"
    assert by_id[MODBUS_TEST_ID]["message_pt"] == FIELD_CONFIG_PT
    assert by_id[NEEDS_CONFIG_TEST_ID]["support_state"] == "NEEDS_CONFIGURATION"
    assert by_id[NEEDS_CONFIG_TEST_ID]["needs_configuration"] is True
    assert by_id[NEEDS_CONFIG_TEST_ID]["ip_known"] is False
    sim = by_id[world.healthy_sim_id]
    assert sim["support_state"] == "AVAILABLE"
    assert sim["message_pt"] == ""
    assert sim["connection_pt"]


async def test_test_read_unsupported_driver_is_honest_409(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    resp = await client.post("/api/v1/communication/test-read", json=_body(world, MODBUS_TEST_ID))
    assert resp.status_code == 409
    err = resp.json()["error"]
    assert err["code"] == "DRIVER_UNSUPPORTED"
    assert err["message_pt"] == FIELD_CONFIG_PT
    assert err["details"]["driver"] == "modbus_tcp"
    assert world.manager.test_read_calls == []  # nem tentou


async def test_test_read_needs_configuration_is_409(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    # Driver real sem IP/protocolo: UNSUPPORTED vence hoje (fase J/K), mas a resposta é 409 honesta.
    resp = await client.post(
        "/api/v1/communication/test-read", json=_body(world, NEEDS_CONFIG_TEST_ID)
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] in {"DRIVER_UNSUPPORTED", "NEEDS_CONFIGURATION"}
    assert world.manager.test_read_calls == []
    # Se o manager recusar por NotConfigured, a API traduz em 409 NEEDS_CONFIGURATION.
    world.manager.test_read_error = NotConfigured("IP ou protocolo não definidos")
    resp = await client.post(
        "/api/v1/communication/test-read", json=_body(world, world.healthy_sim_id)
    )
    assert resp.status_code == 409
    err = resp.json()["error"]
    assert err["code"] == "NEEDS_CONFIGURATION"
    assert "Não configurado" in err["message_pt"]


async def test_test_read_with_simulator_returns_stages(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    eid = world.healthy_sim_id
    resp = await client.post("/api/v1/communication/test-read", json=_body(world, eid))
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["final"] == "READ_OBTAINED"
    assert body["final_pt"] == "Leitura obtida"
    assert body["read_only"] is True
    assert body["stages"][0][0] == "CONNECTING"
    assert len(world.manager.test_read_calls) == 1


async def test_test_read_timeout_result_is_reported_not_hidden(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    now = world.clock.now_utc()
    world.manager.test_read_result = FakeReadTestResult(
        stages=[
            (ReadTestStage.CONNECTING, now, "Conectando"),
            (ReadTestStage.TIMEOUT, now, "Timeout"),
        ],
        final=ReadTestStage.TIMEOUT,
        values={},
        latency_ms=None,
        error_pt="Timeout: Tempo esgotado aguardando resposta do equipamento",
    )
    resp = await client.post(
        "/api/v1/communication/test-read", json=_body(world, world.healthy_sim_id)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert body["final_pt"] == "Timeout"
    assert "Tempo esgotado" in body["error_pt"]


async def test_test_read_mapping_of_other_equipment_is_422(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    body = _body(world, world.healthy_sim_id)
    body["mapping"]["equipment_id"] = "OUTRO_EQUIPAMENTO"
    resp = await client.post("/api/v1/communication/test-read", json=body)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "MAPPING_MISMATCH"


async def test_test_read_config_error_becomes_422(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    world.manager.test_read_error = ConfigError("options.seed deve ser inteiro")
    resp = await client.post(
        "/api/v1/communication/test-read", json=_body(world, world.healthy_sim_id)
    )
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "CONFIG_INVALID"
    assert "seed" in err["details"]["detail"]


async def test_test_read_rejects_unknown_fields_without_echo(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    body = _body(world, world.healthy_sim_id)
    body["profile"]["senha"] = "segredo-que-nao-pode-voltar"
    resp = await client.post("/api/v1/communication/test-read", json=body)
    assert resp.status_code == 422
    text = resp.text
    assert "segredo-que-nao-pode-voltar" not in text
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_test_read_uses_profile_mapping_pair(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    eid = world.healthy_sim_id
    resp = await client.post(
        "/api/v1/communication/test-read", json=_body(world, eid, TEST_MAPPING_ID)
    )
    # mapping de teste é "*": aceito; o fake manager recebe o par e responde
    assert resp.status_code == 200
    profile, mapping = world.manager.test_read_calls[-1]
    assert profile.id == eid
    assert mapping.mapping_id == TEST_MAPPING_ID
