"""/plant e /equipments: estado em português, 'Sem comunicação' e STALE com idade."""

from __future__ import annotations

import httpx
import pytest

from forja.domain import ConnectionState, Quality, Severity
from tests.integration.api_testkit import (
    MODBUS_TEST_ID,
    NEEDS_CONFIG_TEST_ID,
    ApiWorld,
)

pytestmark = pytest.mark.integration


def _card(body: dict, equipment_id: str) -> dict:
    cards = {c["id"]: c for c in body["cards"]}
    return cards[equipment_id]


async def test_plant_has_one_card_per_profile(client: httpx.AsyncClient, world: ApiWorld) -> None:
    resp = await client.get("/api/v1/plant")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == len(world.store.profiles)
    assert [c["id"] for c in body["cards"]] == list(world.store.profiles)
    assert body["data_source_pt"]
    for card in body["cards"]:
        assert card["state_pt"] in {
            "Normal",
            "Atenção",
            "Crítico",
            "Sem comunicação",
            "Parado",
            "Desconhecido",
        }


async def test_plant_shows_sem_comunicacao_for_comm_error(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    eid = world.comm_failure_id
    world.manager.set_status(
        eid,
        connection=ConnectionState.ERROR,
        consecutive_errors=7,
        detail_pt="Tempo esgotado aguardando resposta do equipamento",
    )
    world.manager.set_samples(
        eid,
        {
            "mass_flow": world.sample(
                eid, "mass_flow", None, quality=Quality.COMM_ERROR, reason_pt="sem leitura"
            )
        },
    )
    card = _card((await client.get("/api/v1/plant")).json(), eid)
    assert card["state_pt"] == "Sem comunicação"
    assert card["connection"] == "ERROR"
    assert card["connection_pt"] == "Erro de comunicação"
    assert card["mass_flow"]["quality"] == "COMM_ERROR"
    assert card["mass_flow"]["quality_pt"] == "Sem comunicação"
    assert card["mass_flow"]["value"] is None
    assert card["mass_flow"]["is_usable"] is False


async def test_plant_normal_card_exposes_mass_flow_with_quality(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    eid = world.healthy_sim_id
    world.manager.set_status(eid, connection=ConnectionState.CONNECTED)
    world.manager.set_samples(eid, {"mass_flow": world.sample(eid, "mass_flow", 1298.5)})
    card = _card((await client.get("/api/v1/plant")).json(), eid)
    assert card["state_pt"] == "Normal"
    assert card["data_source"] == "SIMULATED"
    assert card["mass_flow"]["value"] == 1298.5
    assert card["mass_flow"]["unit"] == "kg/h"
    assert card["mass_flow"]["quality"] == "SIMULATED"
    assert card["mass_flow"]["quality_pt"] == "Simulado"
    assert card["mass_flow"]["is_usable"] is True
    assert card["active_anomaly_pt"] is None


async def test_plant_open_events_drive_state_and_anomaly(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    eid = world.healthy_sim_id
    world.manager.set_status(eid, connection=ConnectionState.CONNECTED)
    world.manager.set_samples(eid, {"mass_flow": world.sample(eid, "mass_flow", 1200.0)})
    attention = world.event(eid)
    await world.events_repo.save(attention)
    card = _card((await client.get("/api/v1/plant")).json(), eid)
    assert card["state_pt"] == "Atenção"
    assert card["active_anomaly_pt"] == attention.title_pt
    assert card["open_event_count"] == 1
    assert card["last_event"]["id"] == attention.id
    assert card["last_event"]["severity_pt"] == "Atenção"


async def test_plant_stop_event_is_parado_not_failure(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    eid = world.healthy_sim_id
    world.manager.set_status(eid, connection=ConnectionState.CONNECTED)
    world.manager.set_samples(eid, {"mass_flow": world.sample(eid, "mass_flow", 0.0)})
    stop = world.event(
        eid, type_="MACHINE_STOPPED", title_pt="Equipamento parado", severity=Severity.INFO
    )
    await world.events_repo.save(stop)
    card = _card((await client.get("/api/v1/plant")).json(), eid)
    assert card["state_pt"] == "Parado"
    assert card["active_anomaly_pt"] is None  # parada não é anomalia


async def test_plant_not_configured_is_desconhecido(client: httpx.AsyncClient) -> None:
    card = _card((await client.get("/api/v1/plant")).json(), NEEDS_CONFIG_TEST_ID)
    assert card["state_pt"] == "Desconhecido"
    assert card["connection_pt"] == "Não configurado"
    assert card["needs_configuration"] is True
    assert card["mass_flow"] is None


async def test_list_and_get_equipment(client: httpx.AsyncClient, world: ApiWorld) -> None:
    listing = (await client.get("/api/v1/equipments")).json()
    assert listing["count"] == len(world.store.profiles)
    by_id = {e["id"]: e for e in listing["equipments"]}
    assert by_id[MODBUS_TEST_ID]["is_example"] is True
    assert by_id[MODBUS_TEST_ID]["data_source"] == "EQUIPMENT"
    eid = world.healthy_sim_id
    detail = (await client.get(f"/api/v1/equipments/{eid}")).json()
    assert detail["profile"]["id"] == eid
    assert detail["mapping"]["mapping_id"] == world.store.profiles[eid].mapping_profile
    assert detail["mapping"]["readable"] >= 1
    assert "mass_flow" in detail["mapping"]["tags"]


async def test_unknown_equipment_is_404_with_envelope(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/equipments/NAO_EXISTE")
    assert resp.status_code == 404
    err = resp.json()["error"]
    assert err["code"] == "EQUIPMENT_NOT_FOUND"
    assert err["details"] == {"equipment_id": "NAO_EXISTE"}
    assert "Equipamento não encontrado" in err["message_pt"]


async def test_status_route_has_portuguese_labels(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    eid = world.healthy_sim_id
    world.manager.set_status(eid, connection=ConnectionState.RECONNECTING, reconnect_count=3)
    body = (await client.get(f"/api/v1/equipments/{eid}/status")).json()
    assert body["connection"] == "RECONNECTING"
    assert body["connection_pt"] == "Reconectando"
    assert body["support_state_pt"] == "Disponível"
    assert body["reconnect_count"] == 3


async def test_live_exposes_stale_with_age_and_original_value(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    eid = world.healthy_sim_id
    stale = world.sample(eid, "mass_flow", 1301.0, quality=Quality.STALE, age_s=12.0)
    fresh = world.sample(eid, "machine_state", 1.0)
    world.manager.set_status(eid, connection=ConnectionState.ERROR)
    world.manager.set_samples(
        eid,
        {"mass_flow": stale, "machine_state": fresh},
        ages_s={"mass_flow": 12.0, "machine_state": 0.0},
        is_stale=True,
        stale_for_s=7.0,
    )
    body = (await client.get(f"/api/v1/equipments/{eid}/live")).json()
    assert body["is_stale"] is True
    assert body["stale_for_s"] == 7.0
    tags = {t["tag"]: t for t in body["tags"]}
    assert tags["mass_flow"]["quality"] == "STALE"
    assert tags["mass_flow"]["quality_pt"] == "Valor antigo"
    assert tags["mass_flow"]["value"] == 1301.0  # valor original intacto
    assert tags["mass_flow"]["age_s"] == 12.0
    assert tags["mass_flow"]["is_usable"] is False
    assert tags["mass_flow"]["label_pt"] == "Vazão"
    assert tags["mass_flow"]["explanation_pt"]
    assert tags["machine_state"]["age_s"] == 0.0
    assert tags["machine_state"]["quality"] == "SIMULATED"


async def test_live_uses_manager_age_over_recomputation(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    eid = world.healthy_sim_id
    sample = world.sample(eid, "rpm", 61.0, age_s=2.0)
    world.manager.set_samples(eid, {"rpm": sample}, ages_s={"rpm": 2.0})
    world.clock.advance(30.0)  # o manager não recalculou; a API repete o que ele disse
    body = (await client.get(f"/api/v1/equipments/{eid}/live")).json()
    assert body["tags"][0]["age_s"] == 2.0
