"""SSE: snapshot, heartbeat (5 s pelo Clock), coalescência <= 2 Hz, event/status, Last-Event-ID."""

from __future__ import annotations

import asyncio
import json

import pytest

from forja.domain import (
    TOPIC_CONNECTION,
    TOPIC_EVENTS,
    TOPIC_SAMPLES,
    ConnectionState,
    EventTransition,
    Quality,
    SampleBatch,
)
from tests.integration.api_testkit import (
    ApiWorld,
    open_sse,
    settle,
)

pytestmark = pytest.mark.integration


def _batch(world: ApiWorld, equipment_id: str, value: float) -> SampleBatch:
    sample = world.sample(equipment_id, "mass_flow", value)
    return SampleBatch(
        equipment_id=equipment_id,
        ts_utc=world.clock.now_utc(),
        samples=(sample,),
        quality=Quality.SIMULATED,
        latency_ms=1.0,
    )


async def test_hub_sends_snapshot_then_heartbeat_by_clock(world: ApiWorld) -> None:
    gen = world.hub.stream(None, None)
    first = await asyncio.wait_for(gen.__anext__(), 3)
    assert first.event == "snapshot"
    snapshot = json.loads(first.data)
    assert {c["id"] for c in snapshot["plant"]} == set(world.store.profiles)
    assert set(snapshot["live"]) == set(world.store.profiles)
    await settle()
    world.clock.advance(5.0)
    second = await asyncio.wait_for(gen.__anext__(), 3)
    assert second.event == "heartbeat"
    beat = json.loads(second.data)
    assert beat["uptime_s"] == pytest.approx(5.0)
    assert beat["clients"] == 1
    assert int(second.id) == 1
    await gen.aclose()
    assert world.hub.client_count == 0


async def test_http_stream_delivers_snapshot_and_heartbeat_then_closes(world: ApiWorld) -> None:
    cap = open_sse(world.app, "/api/v1/stream")
    await cap.wait_for(1)
    assert cap.status == 200
    assert cap.headers["content-type"].startswith("text/event-stream")
    assert cap.headers["content-security-policy"] == "default-src 'self'; frame-ancestors 'none'"
    assert cap.headers["x-frame-options"] == "DENY"
    assert cap.headers["cache-control"] == "no-store"
    assert cap.events[0]["event"] == "snapshot"
    assert "plant" in json.loads(cap.events[0]["data"])
    await settle()
    world.clock.advance(5.0)
    await cap.wait_for(2)
    assert cap.events[1]["event"] == "heartbeat"
    assert cap.events[1]["id"] == "1"
    await cap.close()
    assert world.hub.client_count == 0


async def test_samples_are_coalesced_to_two_hertz(world: ApiWorld) -> None:
    eid = world.healthy_sim_id
    gen = world.hub.stream(eid, None)
    await gen.__anext__()  # snapshot
    await settle()
    for value in (1.0, 2.0, 3.0):
        await world.bus.publish(TOPIC_SAMPLES, _batch(world, eid, value))
    await settle()
    first = await asyncio.wait_for(gen.__anext__(), 3)
    assert first.event == "sample"
    assert json.loads(first.data)["tags"]["mass_flow"]["value"] == 1.0
    assert world.hub.buffered == 1  # os dois seguintes ficaram pendentes (coalescidos)
    world.clock.advance(0.5)
    second = await asyncio.wait_for(gen.__anext__(), 3)
    assert second.event == "sample"
    assert json.loads(second.data)["tags"]["mass_flow"]["value"] == 3.0  # só o mais novo
    assert json.loads(second.data)["quality_pt"] == "Simulado"
    await gen.aclose()


async def test_event_and_status_topics_reach_the_stream(world: ApiWorld) -> None:
    eid = world.healthy_sim_id
    gen = world.hub.stream(None, None)
    await gen.__anext__()
    await settle()
    event = world.event(eid)
    await world.bus.publish(TOPIC_EVENTS, EventTransition(kind="OPEN", event=event))
    got = await asyncio.wait_for(gen.__anext__(), 3)
    assert got.event == "event"
    payload = json.loads(got.data)
    assert payload["kind"] == "OPEN"
    assert payload["event"]["id"] == event.id
    assert payload["event"]["severity_pt"] == "Atenção"
    assert "pre_samples" not in payload["event"]["context"]
    world.manager.set_status(eid, connection=ConnectionState.CONNECTED)
    await world.bus.publish(
        TOPIC_CONNECTION,
        {"equipment_id": eid, "previous": "CONNECTING", "current": "CONNECTED"},
    )
    status = await asyncio.wait_for(gen.__anext__(), 3)
    assert status.event == "status"
    body = json.loads(status.data)
    assert body["equipment_id"] == eid
    assert body["status"]["connection_pt"] == "Conectado"
    await gen.aclose()


async def test_stream_filters_by_equipment(world: ApiWorld) -> None:
    eid = world.healthy_sim_id
    other = world.comm_failure_id
    gen = world.hub.stream(eid, None)
    snap = json.loads((await gen.__anext__()).data)
    assert [c["id"] for c in snap["plant"]] == [eid]
    assert list(snap["live"]) == [eid]
    await settle()
    await world.bus.publish(TOPIC_SAMPLES, _batch(world, other, 9.0))
    await world.bus.publish(TOPIC_SAMPLES, _batch(world, eid, 7.0))
    got = await asyncio.wait_for(gen.__anext__(), 3)
    assert json.loads(got.data)["equipment_id"] == eid
    await gen.aclose()


async def test_last_event_id_replays_buffer_or_falls_back_to_snapshot(world: ApiWorld) -> None:
    hub = world.hub
    hub.publish("event", {"n": 1}, None)
    hub.publish("event", {"n": 2}, None)
    hub.publish("event", {"n": 3}, None)
    gen = hub.stream(None, "1")
    replayed = [await gen.__anext__(), await gen.__anext__()]
    assert [r.event for r in replayed] == ["event", "event"]
    assert [json.loads(r.data)["n"] for r in replayed] == [2, 3]
    await gen.aclose()
    assert hub.replay_plan("3") == []
    assert hub.replay_plan("99") is None
    assert hub.replay_plan("abc") is None
    world.clock.advance(61.0)  # buffer de 60 s expirou
    hub.publish("heartbeat", {}, None)
    assert hub.replay_plan("1") is None
    stale = hub.stream(None, "1")
    assert (await stale.__anext__()).event == "snapshot"
    await stale.aclose()


async def test_http_stream_honours_last_event_id_header(world: ApiWorld) -> None:
    world.hub.publish("event", {"n": 1}, None)
    world.hub.publish("event", {"n": 2}, None)
    cap = open_sse(world.app, "/api/v1/stream", headers={"Last-Event-ID": "1"})
    await cap.wait_for(1)
    assert cap.events[0]["event"] == "event"
    assert cap.events[0]["id"] == "2"
    await cap.close()


async def test_stream_unknown_equipment_is_404(world: ApiWorld) -> None:
    cap = open_sse(world.app, "/api/v1/stream", query="eq=NAO_EXISTE")
    await asyncio.wait_for(cap.task, 3)
    assert cap.status == 404
    assert cap.headers["content-security-policy"]
    assert json.loads(cap.pending)["error"]["code"] == "EQUIPMENT_NOT_FOUND"
