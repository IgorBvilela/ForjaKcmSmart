"""Controles do simulador: só para driver simulator (409 nos demais); nada chega ao KCM."""

from __future__ import annotations

import httpx
import pytest

from tests.integration.api_testkit import (
    MODBUS_TEST_ID,
    ApiWorld,
)

pytestmark = pytest.mark.integration


async def test_get_simulator_before_driver_exists(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    eid = world.healthy_sim_id
    expected = str(
        world.store.profiles[eid].communication.options.get("scenario", "NORMAL_OPERATION")
    )
    resp = await client.get(f"/api/v1/simulator/{eid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["equipment_id"] == eid
    assert body["controls"]["scenario"] == expected
    assert body["controls"]["overrides"] == {}
    codes = {s["code"] for s in body["scenarios"]}
    assert "NORMAL_OPERATION" in codes
    assert "REFILL" not in codes
    assert all(s["title_pt"] for s in body["scenarios"])
    assert "belt_load" in body["sliders"]
    assert "Nenhum comando chega ao KCM" in body["note_pt"]


@pytest.mark.parametrize(
    ("method", "suffix", "json"),
    [
        ("GET", "", None),
        ("POST", "/scenario", {"scenario": "BELTLOAD_LOW"}),
        ("POST", "/controls", {"overrides": {"rpm": 10}}),
        ("DELETE", "/controls", None),
    ],
)
async def test_non_simulator_equipment_gets_409(
    client: httpx.AsyncClient, method: str, suffix: str, json: dict | None
) -> None:
    resp = await client.request(method, f"/api/v1/simulator/{MODBUS_TEST_ID}{suffix}", json=json)
    assert resp.status_code == 409
    err = resp.json()["error"]
    assert err["code"] == "NOT_SIMULATOR"
    assert err["details"]["driver"] == "modbus_tcp"
    assert "não usa o simulador" in err["message_pt"]


async def test_set_scenario_changes_controls(client: httpx.AsyncClient, world: ApiWorld) -> None:
    eid = world.healthy_sim_id
    resp = await client.post(f"/api/v1/simulator/{eid}/scenario", json={"scenario": "BELTLOAD_LOW"})
    assert resp.status_code == 200
    assert resp.json()["controls"]["scenario"] == "BELTLOAD_LOW"
    again = (await client.get(f"/api/v1/simulator/{eid}")).json()
    assert again["controls"]["scenario"] == "BELTLOAD_LOW"


async def test_unknown_scenario_is_422(client: httpx.AsyncClient, world: ApiWorld) -> None:
    eid = world.healthy_sim_id
    resp = await client.post(f"/api/v1/simulator/{eid}/scenario", json={"scenario": "REFILL"})
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "UNKNOWN_SCENARIO"
    assert "NORMAL_OPERATION" in err["details"]["valid"]
    lowercase = await client.post(
        f"/api/v1/simulator/{eid}/scenario", json={"scenario": "beltload_low"}
    )
    assert lowercase.status_code == 422
    assert lowercase.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_controls_set_and_clear(client: httpx.AsyncClient, world: ApiWorld) -> None:
    eid = world.healthy_sim_id
    resp = await client.post(
        f"/api/v1/simulator/{eid}/controls", json={"overrides": {"belt_load": 0.9, "rpm": 30}}
    )
    assert resp.status_code == 200
    assert resp.json()["controls"]["overrides"] == {"belt_load": 0.9, "rpm": 30.0}
    merged = await client.post(f"/api/v1/simulator/{eid}/controls", json={"overrides": {"rpm": 45}})
    assert merged.json()["controls"]["overrides"] == {"belt_load": 0.9, "rpm": 45.0}
    cleared = await client.delete(f"/api/v1/simulator/{eid}/controls")
    assert cleared.status_code == 200
    assert cleared.json()["controls"]["overrides"] == {}


@pytest.mark.parametrize(
    "payload",
    [
        {"overrides": {"tare": 1.0}},
        {"overrides": {"write_setpoint": 5}},
        {"overrides": {}},
        {"overrides": {"rpm": "rapido"}},
        {"sliders": {"rpm": 1}},
    ],
)
async def test_controls_reject_unknown_or_invalid_sliders(
    client: httpx.AsyncClient, world: ApiWorld, payload: dict[str, object]
) -> None:
    resp = await client.post(f"/api/v1/simulator/{world.healthy_sim_id}/controls", json=payload)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_unknown_equipment_is_404(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/simulator/NAO_EXISTE")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "EQUIPMENT_NOT_FOUND"
