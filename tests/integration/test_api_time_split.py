"""Medida de tempo (FORJA_RULE): GET /api/v1/equipments/{id}/time-split e GET /api/v1/time-split.

Sem dados nunca conta como normal nem como fora do normal; aviso antecipado não conta como fora
do normal; o alarme do KCM ativo conta; as três partes somam o período.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import httpx
import pytest

from forja.domain import Quality
from tests.integration.api_testkit import ApiWorld, build_world, shutdown_world

pytestmark = pytest.mark.integration

SIM = Quality.SIMULATED
HOUR = 3600


@pytest.fixture
async def plant() -> AsyncIterator[ApiWorld]:
    w = build_world(extra_real_profiles=False)
    try:
        yield w
    finally:
        await shutdown_world(w)


@pytest.fixture
async def api(plant: ApiWorld) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=plant.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


def window(world: ApiWorld) -> dict[str, str]:
    now = world.clock.now_utc()
    return {"from": (now - timedelta(seconds=HOUR)).isoformat(), "to": now.isoformat()}


async def flow_every_minute(world: ApiWorld, eid: str, ages: range) -> None:
    await world.historian.write(
        [world.sample(eid, "mass_flow", 1000.0, quality=SIM, age_s=float(a)) for a in ages]
    )


async def alarm_every_minute(world: ApiWorld, eid: str, ages: range, code: float) -> None:
    samples = []
    for a in ages:
        samples.append(world.sample(eid, "alarm_code", code, quality=SIM, age_s=float(a)))
        samples.append(
            world.sample(eid, "alarm_active", 1.0 if code else 0.0, quality=SIM, age_s=float(a))
        )
    await world.historian.write(samples)


async def split_of(api: httpx.AsyncClient, world: ApiWorld, eid: str) -> dict[str, Any]:
    resp = await api.get(f"/api/v1/equipments/{eid}/time-split", params=window(world))
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_gap_is_no_data_rule_event_is_out_and_early_warning_never_counts(
    api: httpx.AsyncClient, plant: ApiWorld
) -> None:
    eid = plant.healthy_sim_id
    hold = 3 * plant.store.config.historian.forced_sample_every_s
    # leitura a cada minuto, com um buraco entre t=1140 s e t=1800 s
    await flow_every_minute(plant, eid, range(HOUR, 2460 - 1, -60))
    await flow_every_minute(plant, eid, range(1800, -1, -60))
    # evento de regra aberto desde t=2400 s; aviso antecipado aberto desde t=600 s
    await plant.events_repo.save(plant.event(eid, start_offset_s=1200))
    early = plant.event(eid, start_offset_s=3000, rule_id="R-AVISO-TESTE")
    await plant.events_repo.save(early.model_copy(update={"origin": "EARLY_WARNING"}))

    body = await split_of(api, plant, eid)
    no_data = 1800 - (1140 + hold)
    assert body["no_data_s"] == pytest.approx(no_data)
    assert body["out_s"] == pytest.approx(1200)
    assert body["normal_s"] == pytest.approx(HOUR - no_data - 1200)
    assert body["normal_s"] + body["out_s"] + body["no_data_s"] == pytest.approx(HOUR)
    assert body["reference_tag"] == "mass_flow"
    assert body["evidence_level"] == "FORJA_RULE"


async def test_active_kcm_alarm_counts_as_out_of_normal(
    api: httpx.AsyncClient, plant: ApiWorld
) -> None:
    eid = plant.healthy_sim_id
    await flow_every_minute(plant, eid, range(HOUR, -1, -60))
    await alarm_every_minute(plant, eid, range(HOUR, 3000, -60), 0)
    await alarm_every_minute(plant, eid, range(3000, 2700, -60), 56)
    await alarm_every_minute(plant, eid, range(2700, -1, -60), 0)

    body = await split_of(api, plant, eid)
    assert body["no_data_s"] == pytest.approx(0)
    assert body["out_s"] == pytest.approx(300), "alarme ativo de t=600 s a t=900 s"
    assert body["normal_s"] == pytest.approx(HOUR - 300)


async def test_without_any_reading_the_period_is_all_no_data(
    api: httpx.AsyncClient, plant: ApiWorld
) -> None:
    eid = plant.healthy_sim_id
    await plant.events_repo.save(plant.event(eid, start_offset_s=1200))
    body = await split_of(api, plant, eid)
    assert body["no_data_s"] == pytest.approx(HOUR)
    assert body["out_s"] == 0
    assert body["normal_s"] == 0


async def test_plant_wide_split_lists_every_equipment_in_config_order(
    api: httpx.AsyncClient, plant: ApiWorld
) -> None:
    resp = await api.get("/api/v1/time-split", params=window(plant))
    assert resp.status_code == 200
    body = resp.json()
    assert [e["id"] for e in body["equipments"]] == list(plant.store.profiles)
    assert "Sem dados" in body["definition_pt"]
    for item in body["equipments"]:
        assert item["normal_s"] + item["out_s"] + item["no_data_s"] == pytest.approx(item["span_s"])
