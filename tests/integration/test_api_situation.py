"""Tela Agora: GET /api/v1/situation junta, por dosador, o que o gerente e a manutenção precisam.

Sem dados nunca conta como normal; a ordem segue a gravidade; o "desde quando" nunca é
inventado; o aviso antecipado usa a última avaliação guardada, sem recalcular o historiador.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from forja.domain import ConnectionState, Quality, Severity
from forja.service.commcenter import READ_TEST_PENDING_PT
from tests.integration.api_testkit import ApiWorld, build_world, shutdown_world

pytestmark = pytest.mark.integration


@pytest.fixture
async def plant() -> AsyncIterator[ApiWorld]:
    """Só os perfis da semente: o resultado não depende dos perfis extras de teste."""
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


def healthy(world: ApiWorld, eid: str, flow: float = 1000.0) -> None:
    world.manager.set_status(eid, connection=ConnectionState.CONNECTED)
    world.manager.set_samples(eid, {"mass_flow": world.sample(eid, "mass_flow", flow)})


def all_healthy(world: ApiWorld) -> None:
    for eid in world.store.profiles:
        healthy(world, eid)


def entry(body: dict[str, Any], eid: str) -> dict[str, Any]:
    return next(e for e in body["equipments"] if e["id"] == eid)


async def situation(api: httpx.AsyncClient) -> dict[str, Any]:
    resp = await api.get("/api/v1/situation")
    assert resp.status_code == 200
    return resp.json()


async def test_tudo_dentro_do_normal_quando_todos_tem_dado_e_nenhum_evento(
    api: httpx.AsyncClient, plant: ApiWorld
) -> None:
    all_healthy(plant)
    body = await situation(api)
    total = len(plant.store.profiles)
    assert body["summary"]["headline_pt"] == "Tudo dentro do normal"
    assert body["summary"]["tone"] == "ok"
    assert body["summary"]["total"] == total
    assert body["summary"]["normal"] == total
    assert {e["group"] for e in body["equipments"]} == {"normal"}
    assert body["data_source"] == "SIMULATED"
    assert all(e["focus"] is None for e in body["equipments"])


async def test_dosador_com_evento_mostra_desde_quando_o_que_mudou_e_o_que_verificar(
    api: httpx.AsyncClient, plant: ApiWorld
) -> None:
    all_healthy(plant)
    eid = plant.healthy_sim_id
    event = plant.event(eid, start_offset_s=720)
    await plant.events_repo.save(event)
    await plant.diagnoses_repo.save(plant.diagnosis(event))

    body = await situation(api)
    total = len(plant.store.profiles)
    assert body["summary"]["headline_pt"] == f"1 de {total} dosadores em atenção"
    assert body["summary"]["tone"] == "warn"
    assert body["equipments"][0]["id"] == eid, "quem pede atenção vem primeiro"

    item = entry(body, eid)
    assert item["group"] == "problem"
    assert item["severity"] == "ATTENTION"
    assert item["since_basis"] == "EVENT"
    assert item["since_utc"] == event.start_utc.isoformat()

    focus = item["focus"]
    assert focus["event_id"] == event.id
    assert focus["origin"] == "RULE"
    assert focus["changed_first"]["label_pt"] == "Material na correia"
    assert focus["hypothesis_pt"].startswith("Comportamento compatível com")
    assert focus["next_check"]["text_pt"] == "Verificar a alimentação de material sobre a correia."
    assert focus["next_check"]["evidence_pt"] == "Opinião técnica"
    assert focus["diagnosis_available"] is True

    forja = item["voices"]["forja_events"]
    assert [e["id"] for e in forja] == [event.id]
    assert forja[0]["origin_pt"] == "Evento detectado pela Forja"
    assert item["voices"]["early_warnings"] == []


async def test_sem_dados_nunca_conta_como_normal(api: httpx.AsyncClient, plant: ApiWorld) -> None:
    all_healthy(plant)
    failing = plant.comm_failure_id
    plant.manager.set_status(failing, connection=ConnectionState.ERROR)
    plant.manager.set_samples(
        failing,
        {"mass_flow": plant.sample(failing, "mass_flow", None, quality=Quality.COMM_ERROR)},
    )
    blocked = plant.healthy_sim_id
    plant.manager.set_status(blocked, detail_pt=READ_TEST_PENDING_PT)

    body = await situation(api)
    total = len(plant.store.profiles)
    assert entry(body, failing)["group"] == "no_data"
    assert entry(body, failing)["state_pt"] == "Sem comunicação"
    assert entry(body, blocked)["group"] == "no_data"
    assert entry(body, blocked)["state_pt"] == "Coleta não iniciada"
    assert "teste somente leitura" in entry(body, blocked)["reason_pt"]
    assert body["summary"]["no_data"] == 2
    assert body["summary"]["normal"] == total - 2
    assert body["summary"]["headline_pt"] == f"2 de {total} dosadores sem dados"
    assert body["summary"]["tone"] == "info"


async def test_ordem_segue_a_gravidade(api: httpx.AsyncClient, plant: ApiWorld) -> None:
    all_healthy(plant)
    first, second = list(plant.store.profiles)[:2]
    await plant.events_repo.save(plant.event(first, severity=Severity.ATTENTION))
    await plant.events_repo.save(
        plant.event(second, severity=Severity.CRITICAL, rule_id="R-TESTE-002")
    )
    body = await situation(api)
    assert [e["id"] for e in body["equipments"][:2]] == [second, first]
    assert body["equipments"][0]["severity"] == "CRITICAL"
    assert body["summary"]["critical"] == 1
    assert body["summary"]["attention"] == 2
    assert body["summary"]["tone"] == "crit"


async def test_alarme_do_kcm_sem_evento_da_forja_pede_atencao_sem_inventar_inicio(
    api: httpx.AsyncClient, plant: ApiWorld
) -> None:
    all_healthy(plant)
    eid = plant.healthy_sim_id
    plant.manager.set_samples(
        eid,
        {
            "mass_flow": plant.sample(eid, "mass_flow", 1000.0),
            "alarm_active": plant.sample(eid, "alarm_active", 1),
            "alarm_code": plant.sample(eid, "alarm_code", 56),
        },
    )
    body = await situation(api)
    item = entry(body, eid)
    assert item["group"] == "problem"
    kcm = item["voices"]["kcm_alarm"]
    assert kcm["state"] == "ACTIVE"
    assert kcm["code"] == "56"
    assert kcm["since_utc"] is None, "a hora da última leitura não é o início do alarme"
    assert kcm["since_basis"] == "UNDETERMINED"
    assert item["voices"]["forja_events"] == []
    assert item["focus"] is None


async def test_aviso_antecipado_usa_a_ultima_avaliacao_sem_recalcular(
    api: httpx.AsyncClient, plant: ApiWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    all_healthy(plant)
    engine = plant.container.early_warning
    assert engine is not None

    async def no_preview(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a tela Agora não pode disparar a prévia de regra no historiador")

    monkeypatch.setattr(engine, "preview", no_preview)
    eid = plant.healthy_sim_id
    warning = plant.event(
        eid, type_="EW_EFFORT_UP_LOAD_DOWN", rule_id="EW-BELTLOAD-001", title_pt="Esforço subindo"
    ).model_copy(update={"origin": "EARLY_WARNING"})
    await plant.events_repo.save(warning)

    body = await situation(api)
    item = entry(body, eid)
    assert [e["id"] for e in item["voices"]["early_warnings"]] == [warning.id]
    assert item["voices"]["early_warnings"][0]["origin_pt"] == "Aviso antecipado da Forja"
    assert item["voices"]["forja_events"] == []
    assert item["voices"]["early_warning_confirming"] == 0
