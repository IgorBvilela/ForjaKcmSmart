"""API da fase F: alertas (três vozes separadas), aviso antecipado e casos anteriores."""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest

from forja.domain import Quality, Sample
from tests.integration.api_testkit import ApiWorld

pytestmark = pytest.mark.integration

PO_BASE = "GTEX_PHA_PO_BASE"
BARRILHA = "EXEMPLO_BARRILHA"
KCM_03 = "EXEMPLO_KCM_03"


def alarm_samples(
    world: ApiWorld,
    eid: str,
    active: float | None,
    code: float | None,
    *,
    quality: Quality = Quality.SIMULATED,
) -> dict[str, Sample]:
    return {
        "alarm_active": world.sample(eid, "alarm_active", active, quality=quality),
        "alarm_code": world.sample(eid, "alarm_code", code, quality=quality),
    }


async def test_alertas_separam_alarme_do_kcm_de_evento_e_aviso_da_forja(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    world.manager.set_samples(BARRILHA, alarm_samples(world, BARRILHA, 1, 56))
    rule_event = world.event(BARRILHA, rule_id="R-BELTLOAD-001")
    warning = world.event(
        BARRILHA,
        type_="EW_EFFORT_UP_LOAD_DOWN",
        rule_id="EW-BELTLOAD-001",
        title_pt="Esforço subindo",
    ).model_copy(update={"origin": "EARLY_WARNING"})
    closed = world.event(BARRILHA, rule_id="R-RATE-001", type_="RATE_LOW", is_open=False)
    for e in (rule_event, warning, closed):
        await world.events_repo.save(e)

    resp = await client.get(f"/api/v1/equipments/{BARRILHA}/alerts")
    assert resp.status_code == 200
    body = resp.json()
    kcm = body["kcm_alarm"]
    assert kcm["state"] == "ACTIVE"
    assert kcm["code"] == "56"
    assert kcm["source_pt"] == "informado pelo KCM"
    assert "KCM" in kcm["note_pt"]
    assert [e["id"] for e in body["forja_events"]] == [rule_event.id]
    assert body["forja_events"][0]["origin_pt"] == "Evento detectado pela Forja"
    assert [e["id"] for e in body["early_warnings"]] == [warning.id]
    assert body["early_warnings"][0]["origin_pt"] == "Aviso antecipado da Forja"
    assert body["counts"] == {
        "kcm_alarm": 1,
        "forja_events": 1,
        "forja_events_unacknowledged": 1,
        "early_warnings": 1,
    }
    assert "não é alarme do KCM" in body["notes_pt"]["early_warning"]


async def test_alarme_do_kcm_sem_leitura_atual_fica_desconhecido(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    world.manager.set_samples(
        KCM_03, alarm_samples(world, KCM_03, None, None, quality=Quality.COMM_ERROR)
    )
    kcm = (await client.get(f"/api/v1/equipments/{KCM_03}/alerts")).json()["kcm_alarm"]
    assert kcm["state"] == "UNKNOWN"
    assert "desconhecido" in kcm["state_pt"]

    world.manager.set_samples(KCM_03, alarm_samples(world, KCM_03, 0, 0))
    kcm = (await client.get(f"/api/v1/equipments/{KCM_03}/alerts")).json()["kcm_alarm"]
    assert kcm["state"] == "NONE"


async def test_reconhecer_evento_mantem_aberto_e_registra_quem(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    event = world.event(BARRILHA)
    await world.events_repo.save(event)
    ack = await client.post(
        f"/api/v1/events/{event.id}/ack", json={"user": "Técnico de turno", "note_pt": "visto"}
    )
    assert ack.status_code == 200
    body = (await client.get(f"/api/v1/equipments/{BARRILHA}/alerts")).json()
    assert body["forja_events"][0]["status"] == "ACKNOWLEDGED"
    assert body["forja_events"][0]["acked_by"] == "Técnico de turno"
    assert body["counts"]["forja_events_unacknowledged"] == 0


async def _write_drift(world: ApiWorld, eid: str, minutes: int) -> None:
    """Esforço subindo 1 ponto/min, material caindo 1,5%/min, vazão no setpoint, em operação."""
    samples = []
    for k in range(minutes * 6 + 1):
        age = (minutes * 60) - k * 10
        progress = k * 10 / 60
        for tag, value in (
            ("drive_command", 40 + progress),
            ("belt_load", 1.5 * (1 - 0.015 * progress)),
            ("mass_flow", 900.0),
            ("setpoint", 900.0),
            ("machine_state", 1.0),
        ):
            samples.append(world.sample(eid, tag, value, age_s=age))
    await world.historian.write(samples)


async def test_aviso_antecipado_mostra_regras_sinais_e_previa(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    await _write_drift(world, BARRILHA, 20)
    resp = await client.get(f"/api/v1/equipments/{BARRILHA}/early-warning")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert "Não é previsão de falha" in body["disclaimer_pt"]
    rules = {r["id"]: r for r in body["rules"]}
    rule = rules["EW-BELTLOAD-001"]
    assert rule["preview"] is True
    assert rule["state"] == "CONFIRMING"
    assert "avaliações seguidas" in rule["state_pt"]
    assert rule["threshold_basis"] == "FORJA_RULE"
    assert "Não são limites do KCM" in rule["threshold_note_pt"]
    drive = next(s for s in rule["signals"] if s["tag"] == "drive_command")
    assert drive["verdict"] == "MET"
    assert "subiu" in drive["text_pt"]
    assert "pelo menos 8 pontos" in drive["limit_pt"]
    assert any(v is not None for v in drive["spark"])
    assert len(drive["spark"]) <= 60
    # a prévia não abre aviso nem mexe na contagem
    assert rule["met_streak"] == 0
    assert await world.events_repo.list(equipment_id=BARRILHA, open_only=True) == []


async def test_aviso_aberto_aparece_como_ativo_e_no_historico(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    engine = world.container.early_warning
    await _write_drift(world, BARRILHA, 20)
    opened = []
    for _ in range(3):
        for t in await engine.evaluate(world.historian, BARRILHA, force=True):
            await world.events_repo.save(t.event)
            opened.append(t)
        world.clock.advance(1)
    assert [t.kind for t in opened if t.event.rule_id == "EW-BELTLOAD-001"] == ["OPEN"]
    body = (await client.get(f"/api/v1/equipments/{BARRILHA}/early-warning")).json()
    rule = next(r for r in body["rules"] if r["id"] == "EW-BELTLOAD-001")
    assert rule["state"] == "ACTIVE"
    assert rule["state_pt"] == "Merece atenção"
    assert rule["open_event_id"] == opened[0].event.id
    assert body["active_count"] >= 1
    assert body["recent"][0]["origin"] == "EARLY_WARNING"
    event = (await client.get(f"/api/v1/events/{opened[0].event.id}")).json()
    assert event["pre_event"]["narrative_pt"][0].startswith("Aviso antecipado")


async def test_regra_de_aplicacao_wbf_nao_vale_para_aplicacao_desconhecida(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    body = (await client.get(f"/api/v1/equipments/{KCM_03}/early-warning")).json()
    assert "EW-BELTLOAD-001" not in {r["id"] for r in body["rules"]}
    assert body["rules"], "regras sem restrição de aplicação continuam valendo"


async def test_casos_do_equipamento_da_aplicacao_e_recorrencia(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    for offset in (7200, 3600):
        await world.events_repo.save(world.event(PO_BASE, start_offset_s=offset, is_open=False))
    own = (await client.get(f"/api/v1/equipments/{PO_BASE}/cases")).json()
    assert [c["id"] for c in own["field_cases"]] == ["CASE-2026-09-GTEX-PHA-PO-BASE-VELOCIDADE"]
    case = own["field_cases"][0]
    assert case["cause_confirmed"] is False
    assert case["cause_pt"] == "Causa não confirmada"
    assert case["evidence_pt"] == "Observado em campo"
    assert all("evidence_pt" in m for m in case["measurements"])
    assert own["recurrence"][0]["count"] == 2
    assert own["recurrence"][0]["first_changed"]["label_pt"] == "Material na correia"

    other = (await client.get(f"/api/v1/equipments/{BARRILHA}/cases")).json()
    assert other["field_cases"] == []
    assert [c["id"] for c in other["same_application_cases"]] == [
        "CASE-2026-09-GTEX-PHA-PO-BASE-VELOCIDADE"
    ]


async def test_evento_traz_o_que_aconteceu_antes(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    event = world.event(BARRILHA)
    event = event.model_copy(update={"start_utc": event.start_utc + timedelta(seconds=25)})
    await world.events_repo.save(event)
    body = (await client.get(f"/api/v1/events/{event.id}")).json()
    assert body["origin"] == "RULE"
    pre = body["pre_event"]
    assert pre["first_tag"] == "belt_load"
    assert pre["lead_s"] == pytest.approx(25)
    assert "25 s antes da abertura" in pre["narrative_pt"][0]
