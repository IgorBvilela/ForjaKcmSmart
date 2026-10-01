"""Histórico (GAP = null, nunca interpola), eventos, ack auditado, diagnóstico e alarmes."""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest

from forja.domain import Diagnosis, Quality
from tests.integration.api_testkit import (
    ApiWorld,
)

pytestmark = pytest.mark.integration


async def test_history_returns_gap_as_null_and_never_interpolates(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    eid = world.healthy_sim_id
    await world.historian.write(
        [
            world.sample(eid, "mass_flow", 1300.0, age_s=30),
            world.sample(eid, "mass_flow", None, quality=Quality.COMM_ERROR, age_s=20),
            world.sample(eid, "mass_flow", 1290.0, age_s=10),
        ]
    )
    resp = await client.get(f"/api/v1/equipments/{eid}/history", params={"tags": "mass_flow"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["interpolated"] is False
    assert body["max_points"] == 2000
    series = body["series"]
    assert len(series) == 1
    assert series[0]["tag"] == "mass_flow"
    assert [p["value"] for p in series[0]["points"]] == [1300.0, None, 1290.0]
    assert series[0]["gap_count"] == 1


async def test_history_accepts_multiple_tags_and_window(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    eid = world.healthy_sim_id
    now = world.clock.now_utc()
    resp = await client.get(
        f"/api/v1/equipments/{eid}/history",
        params={
            "tags": "mass_flow,rpm,mass_flow",
            "from": (now - timedelta(hours=2)).isoformat(),
            "to": now.isoformat(),
            "maxPoints": 500,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert [s["tag"] for s in body["series"]] == ["mass_flow", "rpm"]
    assert body["max_points"] == 500


@pytest.mark.parametrize(
    ("params", "code"),
    [
        ({"tags": "nao_existe"}, "UNKNOWN_TAG"),
        ({"tags": " , "}, "VALIDATION_ERROR"),
        ({}, "VALIDATION_ERROR"),
    ],
)
async def test_history_rejects_bad_tags(
    client: httpx.AsyncClient, world: ApiWorld, params: dict[str, str], code: str
) -> None:
    resp = await client.get(f"/api/v1/equipments/{world.healthy_sim_id}/history", params=params)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == code


async def test_history_rejects_inverted_window(client: httpx.AsyncClient, world: ApiWorld) -> None:
    now = world.clock.now_utc()
    resp = await client.get(
        f"/api/v1/equipments/{world.healthy_sim_id}/history",
        params={
            "tags": "rpm",
            "from": now.isoformat(),
            "to": (now - timedelta(minutes=1)).isoformat(),
        },
    )
    assert resp.status_code == 422
    assert "anterior" in resp.json()["error"]["message_pt"]


async def test_events_list_is_newest_first_with_limit(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    eid = world.healthy_sim_id
    older = world.event(eid, start_offset_s=600, is_open=False, rule_id="R-TESTE-001")
    newer = world.event(eid, start_offset_s=60, rule_id="R-TESTE-002")
    await world.events_repo.save(older)
    await world.events_repo.save(newer)
    body = (await client.get(f"/api/v1/equipments/{eid}/events")).json()
    assert body["count"] == 2
    assert [e["id"] for e in body["events"]] == [newer.id, older.id]
    assert body["events"][0]["status_pt"] == "Aberto"
    assert body["events"][1]["status_pt"] == "Resolvido"
    assert "pre_samples" not in body["events"][0]["context"]
    assert body["events"][0]["context"]["pre_sample_count"] == 1
    limited = (await client.get(f"/api/v1/equipments/{eid}/events", params={"limit": 1})).json()
    assert [e["id"] for e in limited["events"]] == [newer.id]
    open_only = (
        await client.get(f"/api/v1/equipments/{eid}/events", params={"open_only": "true"})
    ).json()
    assert [e["id"] for e in open_only["events"]] == [newer.id]


async def test_event_detail_includes_sample_windows(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    eid = world.healthy_sim_id
    event = world.event(eid)
    await world.events_repo.save(event)
    body = (await client.get(f"/api/v1/events/{event.id}")).json()
    assert body["id"] == event.id
    assert body["type"] == "BELT_LOAD_LOW"
    assert body["title_pt"] == event.title_pt
    assert body["severity_pt"] == "Atenção"
    assert body["quality_pt"] == "Simulado"
    assert len(body["context"]["pre_samples"]) == 1
    assert body["context"]["what_changed"][0]["changed_first"] is True
    missing = await client.get("/api/v1/events/nao-existe")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "EVENT_NOT_FOUND"


async def test_ack_is_audited_and_idempotency_is_refused(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    eid = world.healthy_sim_id
    event = world.event(eid)
    await world.events_repo.save(event)
    resp = await client.post(
        f"/api/v1/events/{event.id}/ack", json={"user": "manutencao.turno1", "note_pt": "Visto."}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ACKNOWLEDGED"
    assert body["status_pt"] == "Reconhecido"
    assert body["acked_by"] == "manutencao.turno1"
    assert body["is_open"] is True  # reconhecer não encerra
    assert len(world.events_repo.audits) == 1
    audit = world.events_repo.audits[0]
    assert audit["action"] == "EVENT_ACK"
    assert audit["entity_id"] == event.id
    assert audit["before"]["status"] == "OPEN"
    assert audit["after"]["status"] == "ACKNOWLEDGED"
    assert audit["reason_pt"] == "Visto."
    again = await client.post(f"/api/v1/events/{event.id}/ack", json={"user": "outro"})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "EVENT_NOT_OPEN"


@pytest.mark.parametrize(
    "payload",
    [
        {"user": ""},
        {"user": "x" * 65},
        {"user": "ok", "extra": 1},
        {"user": "<script>"},
        {},
    ],
)
async def test_ack_validates_body(
    client: httpx.AsyncClient, world: ApiWorld, payload: dict[str, object]
) -> None:
    event = world.event(world.healthy_sim_id)
    await world.events_repo.save(event)
    resp = await client.post(f"/api/v1/events/{event.id}/ack", json=payload)
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    for item in err["details"]:
        assert set(item) == {"loc", "msg", "type"}  # nunca ecoa o corpo recebido
    assert world.events_repo.audits == []


async def test_diagnosis_404_then_roundtrip_v1(client: httpx.AsyncClient, world: ApiWorld) -> None:
    eid = world.healthy_sim_id
    event = world.event(eid)
    await world.events_repo.save(event)
    missing = await client.get(f"/api/v1/events/{event.id}/diagnosis")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "DIAGNOSIS_NOT_FOUND"
    diagnosis = world.diagnosis(event)
    await world.diagnoses_repo.save(diagnosis)
    resp = await client.get(f"/api/v1/events/{event.id}/diagnosis")
    assert resp.status_code == 200
    body = resp.json()
    assert body["diagnosis_schema_version"] == "1.0"
    assert body["event_id"] == event.id
    assert list(body)[:5] == [
        "diagnosis_schema_version",
        "diagnosis_id",
        "event_id",
        "equipment_id",
        "generated_at_utc",
    ]
    assert Diagnosis.model_validate(body) == diagnosis
    assert any("não representam causa confirmada" in c["text_pt"] for c in body["caveats"])


async def test_alarm_lookup_uses_profile_key_and_is_honest(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    eid = world.healthy_sim_id
    profile = world.store.profiles[eid]
    resp = await client.get("/api/v1/alarms/lookup", params={"equipment_id": eid, "code": "56"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == "56"
    assert body["key"]["application"] == profile.application
    assert body["key"]["software_version"] == profile.controller.software_version
    assert body["title_pt"]
    assert body["qualifier_pt"]
    if not body["catalogued"]:
        assert body["qualifier_pt"] == "Não catalogado"
        assert "não catalogado" in body["title_pt"]
    bad = await client.get("/api/v1/alarms/lookup", params={"equipment_id": eid, "code": "56;drop"})
    assert bad.status_code == 422
