"""Relatório por período e CSV de eventos: cobertura no tempo, eventos por origem, alarmes que o
KCM informou com o texto do catálogo da chave e o resumo em português."""

from __future__ import annotations

import csv
import io
from datetime import timedelta

import httpx
import pytest

from forja.domain import Quality
from tests.integration.api_testkit import ApiWorld

pytestmark = pytest.mark.integration

EQ = "EXEMPLO_BARRILHA"


async def _seed(world: ApiWorld) -> tuple[str, str]:
    now = world.clock.now_utc()
    start = now - timedelta(hours=1)
    samples = []
    for k in range(0, 3601, 30):
        age = 3600 - k
        if 1800 <= k < 2700:  # 15 min sem comunicação no meio do período
            samples.append(
                world.sample(EQ, "mass_flow", None, quality=Quality.COMM_ERROR, age_s=age)
            )
        else:
            samples.append(world.sample(EQ, "mass_flow", 900.0, age_s=age))
    for age, code in ((3000, 0), (2400, 56), (2000, 0), (600, 56)):
        samples.append(world.sample(EQ, "alarm_code", float(code), age_s=age))
    await world.historian.write(samples)
    for offset in (2500, 900):
        await world.events_repo.save(world.event(EQ, start_offset_s=offset, is_open=False))
    warning = world.event(
        EQ, type_="EW_EFFORT_UP_LOAD_DOWN", rule_id="EW-BELTLOAD-001", start_offset_s=300
    ).model_copy(update={"origin": "EARLY_WARNING"})
    await world.events_repo.save(warning)
    return start.isoformat(), now.isoformat()


async def test_relatorio_do_periodo(client: httpx.AsyncClient, world: ApiWorld) -> None:
    start, end = await _seed(world)
    resp = await client.get(f"/api/v1/equipments/{EQ}/report", params={"from": start, "to": end})
    assert resp.status_code == 200, resp.text
    report = resp.json()
    assert report["data_source"] == "SIMULATED"
    flow = next(t for t in report["tags"] if t["tag"] == "mass_flow")
    assert flow["coverage"] == pytest.approx(0.75, abs=0.03)
    assert flow["average"] == pytest.approx(900.0)
    assert flow["comm_error_points"] == 30
    groups = {(g["origin"], g["type"]): g["count"] for g in report["event_groups"]}
    assert groups[("RULE", "BELT_LOAD_LOW")] == 2
    assert groups[("EARLY_WARNING", "EW_EFFORT_UP_LOAD_DOWN")] == 1
    assert report["events_total"] == 3
    alarm = report["kcm_alarms"][0]
    assert alarm["code"] == "56"
    assert alarm["times"] == 2
    assert alarm["qualifier_pt"] == "Observado nesta aplicação"
    text = " ".join(report["narrative_pt"])
    assert "Dados simulados" in text
    assert "2 evento(s) detectado(s) pela Forja" in text
    assert "1 aviso(s) antecipado(s)" in text
    assert "O KCM informou alarme: 56" in text
    assert any("não afirmam causa" in c for c in report["caveats_pt"])


async def test_csv_de_eventos_com_origem(client: httpx.AsyncClient, world: ApiWorld) -> None:
    start, end = await _seed(world)
    resp = await client.get(
        f"/api/v1/equipments/{EQ}/events.csv", params={"from": start, "to": end}
    )
    assert resp.status_code == 200
    assert "eventos" in resp.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(resp.text.lstrip("﻿")), delimiter=";"))
    assert len(rows) == 3
    assert {r["origem"] for r in rows} == {
        "Evento detectado pela Forja",
        "Aviso antecipado da Forja",
    }
    assert all(r["inicio_utc"].endswith("Z") for r in rows)
    assert rows[0]["primeira_variavel"] == "Material na correia"


async def test_periodo_invertido_e_recusado(client: httpx.AsyncClient, world: ApiWorld) -> None:
    now = world.clock.now_utc()
    resp = await client.get(
        f"/api/v1/equipments/{EQ}/report",
        params={"from": now.isoformat(), "to": (now - timedelta(hours=1)).isoformat()},
    )
    assert resp.status_code == 422
