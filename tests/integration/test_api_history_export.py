"""API: exportação CSV do histórico e análise "o que mudou nesta janela"."""

from __future__ import annotations

import csv
import io
from datetime import timedelta

import httpx
import pytest

from forja.domain import Quality
from tests.integration.api_testkit import ApiWorld

pytestmark = pytest.mark.integration


def _csv(text: str, delimiter: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text.lstrip("﻿")), delimiter=delimiter))


async def test_csv_bruto_preserva_instante_valor_unidade_e_qualidade(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    eid = world.healthy_sim_id
    await world.historian.write(
        [
            world.sample(eid, "mass_flow", 1300.0, age_s=30),
            world.sample(
                eid,
                "mass_flow",
                None,
                quality=Quality.COMM_ERROR,
                age_s=20,
                reason_pt="Tempo esgotado",
            ),
        ]
    )
    resp = await client.get(f"/api/v1/equipments/{eid}/history.csv", params={"tags": "mass_flow"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    rows = _csv(resp.text, ";")
    assert [(r["valor"], r["unidade"], r["qualidade"]) for r in rows] == [
        ("1300,0", "kg/h", "SIMULATED"),
        ("", "kg/h", "COMM_ERROR"),
    ]
    assert rows[1]["motivo"] == "Tempo esgotado"
    assert all(r["data_hora_utc"].endswith("Z") for r in rows)


async def test_csv_padrao_e_resumido(client: httpx.AsyncClient, world: ApiWorld) -> None:
    eid = world.healthy_sim_id
    await world.historian.write([world.sample(eid, "rpm", 61.5, age_s=5)])
    resp = await client.get(
        f"/api/v1/equipments/{eid}/history.csv",
        params={"tags": "rpm", "dialect": "std", "resolution": "auto"},
    )
    assert resp.status_code == 200
    rows = _csv(resp.text, ",")
    assert rows
    assert {"media", "minimo", "maximo", "pior_qualidade"} <= set(rows[0])


async def test_csv_sem_tags_usa_o_mapping_do_equipamento(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    eid = world.healthy_sim_id
    await world.historian.write([world.sample(eid, "belt_load", 2.0, age_s=5)])
    resp = await client.get(f"/api/v1/equipments/{eid}/history.csv")
    assert resp.status_code == 200
    assert {r["tag"] for r in _csv(resp.text, ";")} == {"belt_load"}


async def test_csv_recusa_tag_desconhecida(client: httpx.AsyncClient, world: ApiWorld) -> None:
    resp = await client.get(
        f"/api/v1/equipments/{world.healthy_sim_id}/history.csv", params={"tags": "inexistente"}
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "UNKNOWN_TAG"


async def test_what_changed_conta_a_ordem_das_mudancas(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    eid = world.healthy_sim_id
    samples = []
    for i in range(60):
        age = 600 - i * 10
        drive = 60.0 if i < 20 else 60.0 + (i - 19) * 0.75
        flow = 1300.0 if i < 30 else 1300.0 - (i - 29) * 8.0
        samples.append(world.sample(eid, "drive_command", drive, age_s=age))
        samples.append(world.sample(eid, "mass_flow", flow, age_s=age))
    await world.historian.write(samples)
    now = world.clock.now_utc()
    resp = await client.get(
        f"/api/v1/equipments/{eid}/what-changed",
        params={
            "tags": "mass_flow,drive_command",
            "from": (now - timedelta(minutes=11)).isoformat(),
            "to": now.isoformat(),
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["interpolated"] is False
    assert body["first_changed_tag"] == "drive_command"
    assert [c["item"]["tag"] for c in body["changes"]] == ["drive_command", "mass_flow"]
    assert body["changes"][1]["offset_s"] > 0
    assert body["narrative_pt"]
    assert any("não é causa" in c for c in body["caveats_pt"])
    assert set(body["stats"]) == {"mass_flow", "drive_command"}


async def test_what_changed_sem_dados_responde_sem_inventar(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    resp = await client.get(
        f"/api/v1/equipments/{world.healthy_sim_id}/what-changed", params={"tags": "mass_flow"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["changes"] == []
    assert body["first_changed_tag"] is None


async def test_what_changed_equipamento_inexistente_404(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/equipments/NAO_EXISTE/what-changed")
    assert resp.status_code == 404


async def test_catalogo_de_variaveis_em_portugues(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/tags")
    assert resp.status_code == 200
    by_code = {t["code"]: t for t in resp.json()["tags"]}
    assert by_code["mass_flow"]["label_pt"] == "Vazão"
    assert by_code["mass_flow"]["unit"] == "kg/h"
    assert by_code["machine_state"]["kind"] == "DISCRETE"


async def test_detalhe_do_equipamento_lista_tags_legiveis(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    resp = await client.get(f"/api/v1/equipments/{world.healthy_sim_id}")
    assert resp.status_code == 200
    mapping = resp.json()["mapping"]
    assert "mass_flow" in mapping["readable_tags"]
    assert len(mapping["readable_tags"]) == mapping["readable"]
