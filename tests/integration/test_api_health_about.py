"""/health, /api/v1/system/about e /api/v1/system/health com Container de teste."""

from __future__ import annotations

import httpx
import pytest

from forja.version import DIAGNOSIS_SCHEMA_VERSION, __version__
from tests.integration.api_testkit import (
    ApiWorld,
    build_world,
    shutdown_world,
)

pytestmark = pytest.mark.integration


async def test_health_liveness(client: httpx.AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "version": __version__}


async def test_about_is_read_only_and_describes_data_source(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    resp = await client.get("/api/v1/system/about")
    assert resp.status_code == 200
    body = resp.json()
    assert body["read_only"] is True
    assert body["version"] == __version__
    assert body["diagnosis_schema_version"] == DIAGNOSIS_SCHEMA_VERSION
    assert body["data_source"] == "MIXED"  # semente simulada + perfis Modbus de teste
    assert body["data_source_pt"].startswith("DADOS MISTOS")
    assert body["equipment_count"] == len(world.store.profiles)
    assert body["python"]
    assert body["sqlite"]
    assert body["dev_mode"] is False
    assert body["docs_url"] is None


async def test_about_uptime_follows_the_clock_port(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    before = (await client.get("/api/v1/system/about")).json()["uptime_s"]
    world.clock.advance(42.0)
    after = (await client.get("/api/v1/system/about")).json()["uptime_s"]
    assert after - before == pytest.approx(42.0)


async def test_about_simulated_only_world_says_simulated() -> None:
    w = build_world(extra_real_profiles=False)
    try:
        transport = httpx.ASGITransport(app=w.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            body = (await c.get("/api/v1/system/about")).json()
        assert body["data_source"] == "SIMULATED"
        assert body["data_source_pt"] == "DADOS SIMULADOS"
    finally:
        await shutdown_world(w)


async def test_system_health_reports_every_block(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    eid = world.healthy_sim_id
    await world.historian.write([world.sample(eid, "mass_flow", 1234.0)])
    await world.events_repo.save(world.event(eid))
    resp = await client.get("/api/v1/system/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert set(body["equipments"]) == set(world.store.profiles)
    assert body["equipments"][eid]["connection_pt"]
    assert body["historian"]["samples"] == 1
    assert body["bus"]["dropped"] == 0
    assert body["events"] == {"rules_loaded": 0, "open_events": 1}


async def test_unknown_route_uses_error_envelope(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/nao-existe")
    assert resp.status_code == 404
    body = resp.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message_pt", "details"}
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["message_pt"] == "Rota não encontrada."
