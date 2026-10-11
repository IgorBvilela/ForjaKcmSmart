"""Turnos e resumo do turno: GET /api/v1/shifts e GET /api/v1/shift-summary. Somente leitura.

O relógio de teste começa em 2026-01-01 12:00 UTC, 09:00 no fuso da planta (America/Sao_Paulo,
UTC-3). Os turnos são de exemplo do teste; os da planta vêm de `config/forja.yaml`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import httpx
import pytest

from forja.config.models import PlantConfig, ShiftConfig
from forja.domain import Quality
from tests.integration.api_testkit import ApiWorld, build_world, shutdown_world

pytestmark = pytest.mark.integration

SIM = Quality.SIMULATED
HOUR = 3600
SHIFTS = [
    ShiftConfig(name="Turno 1", start="06:00", end="14:00"),
    ShiftConfig(name="Turno 2", start="14:00", end="22:00"),
    ShiftConfig(name="Turno 3", start="22:00", end="06:00"),
]


def with_shifts(world: ApiWorld, shifts: list[ShiftConfig]) -> None:
    world.store.config = world.store.config.model_copy(update={"plant": PlantConfig(shifts=shifts)})


@pytest.fixture
async def plant() -> AsyncIterator[ApiWorld]:
    w = build_world(extra_real_profiles=False)
    with_shifts(w, SHIFTS)
    try:
        yield w
    finally:
        await shutdown_world(w)


@pytest.fixture
async def api(plant: ApiWorld) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=plant.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


async def flow_every_minute(world: ApiWorld, eid: str, ages: range) -> None:
    await world.historian.write(
        [world.sample(eid, "mass_flow", 1000.0, quality=SIM, age_s=float(a)) for a in ages]
    )


async def summary(api: httpx.AsyncClient, **params: Any) -> dict[str, Any]:
    resp = await api.get("/api/v1/shift-summary", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def item(body: dict[str, Any], eid: str) -> dict[str, Any]:
    return next(e for e in body["equipments"] if e["id"] == eid)


async def test_shifts_lists_the_configured_shifts_and_the_running_one(
    api: httpx.AsyncClient,
) -> None:
    resp = await api.get("/api/v1/shifts")
    assert resp.status_code == 200
    body = resp.json()
    assert body["timezone"] == "America/Sao_Paulo"
    assert body["today"] == "2026-01-01"
    assert [s["name"] for s in body["shifts"]] == ["Turno 1", "Turno 2", "Turno 3"]
    assert body["shifts"][2] == {
        "index": 2,
        "name": "Turno 3",
        "start": "22:00",
        "end": "06:00",
        "crosses_midnight": True,
    }
    assert body["current"] == {"index": 0, "date": "2026-01-01"}


async def test_shifts_is_empty_without_configuration(
    api: httpx.AsyncClient, plant: ApiWorld
) -> None:
    with_shifts(plant, [])
    body = (await api.get("/api/v1/shifts")).json()
    assert body["shifts"] == []
    assert body["current"] is None


async def test_running_shift_summary_stops_at_now_and_says_in_progress(
    api: httpx.AsyncClient, plant: ApiWorld
) -> None:
    eid = plant.healthy_sim_id
    await flow_every_minute(plant, eid, range(3 * HOUR, -1, -60))
    body = await summary(api, shift=0, date="2026-01-01")
    assert body["from_utc"].startswith("2026-01-01T09:00:00")
    assert body["to_utc"].startswith("2026-01-01T12:00:00")
    assert body["in_progress"] is True
    assert body["shift"] == {"index": 0, "name": "Turno 1", "start": "06:00", "end": "14:00"}
    assert body["date"] == "2026-01-01"
    assert body["evidence_level"] == "FORJA_RULE"
    assert body["data_source"] == "SIMULATED"
    split = item(body, eid)
    assert split["span_s"] == 3 * HOUR
    assert split["normal_s"] + split["out_s"] + split["no_data_s"] == pytest.approx(3 * HOUR)
    assert split["normal_pct"] > 90
    assert split["data_source"] == "SIMULATED"


async def test_summary_lists_forja_events_and_kcm_alarms_and_counts_warnings_apart(
    api: httpx.AsyncClient, plant: ApiWorld
) -> None:
    eid = plant.healthy_sim_id
    await flow_every_minute(plant, eid, range(3 * HOUR, -1, -60))
    await plant.events_repo.save(plant.event(eid, start_offset_s=HOUR))
    early = plant.event(eid, start_offset_s=2 * HOUR, rule_id="R-AVISO-TESTE")
    await plant.events_repo.save(early.model_copy(update={"origin": "EARLY_WARNING"}))
    await plant.historian.write(
        [plant.sample(eid, "alarm_code", 56.0, quality=SIM, age_s=float(a)) for a in (1800, 1740)]
    )
    split = item(await summary(api, shift=0, date="2026-01-01"), eid)
    assert [e["title_pt"] for e in split["events"]] == ["Pouco material sobre a correia"]
    assert split["events"][0]["severity"] == "ATTENTION"
    assert split["events_total"] == 1
    assert split["early_warnings"] == 1
    assert [a["code"] for a in split["kcm_alarms"]] == ["56"]
    assert split["kcm_alarms"][0]["title_pt"]


async def test_summary_for_a_free_period_has_no_shift(
    api: httpx.AsyncClient, plant: ApiWorld
) -> None:
    now = plant.clock.now_utc()
    body = await summary(
        api, **{"from": (now - timedelta(hours=2)).isoformat(), "to": now.isoformat()}
    )
    assert body["shift"] is None
    assert body["date"] is None
    assert body["in_progress"] is False
    assert {e["id"] for e in body["equipments"]} == set(plant.store.profiles)


async def test_finished_night_shift_crosses_midnight(
    api: httpx.AsyncClient, plant: ApiWorld
) -> None:
    body = await summary(api, shift=2, date="2025-12-31")
    assert body["from_utc"].startswith("2026-01-01T01:00:00")
    assert body["to_utc"].startswith("2026-01-01T09:00:00")
    assert body["in_progress"] is False


@pytest.mark.parametrize(
    ("params", "status"),
    [
        ({"shift": 7, "date": "2026-01-01"}, 404),
        ({"shift": 0}, 422),
        ({}, 422),
        ({"shift": 1, "date": "2026-01-02"}, 422),
        ({"shift": 0, "date": "01/01/2026"}, 422),
    ],
)
async def test_summary_refuses_what_it_cannot_answer(
    api: httpx.AsyncClient, params: dict[str, Any], status: int
) -> None:
    resp = await api.get("/api/v1/shift-summary", params=params)
    assert resp.status_code == status, resp.text
    assert resp.json()["error"]["message_pt"]


async def test_shift_routes_are_read_only(api: httpx.AsyncClient) -> None:
    for path in ("/api/v1/shifts", "/api/v1/shift-summary"):
        resp = await api.post(path, json={})
        assert resp.status_code == 405, path
