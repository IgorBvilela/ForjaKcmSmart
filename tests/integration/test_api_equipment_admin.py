"""Cadastro de equipamentos: criar, ficha técnica, arquivar e restaurar, catálogo de alarmes.

Configuração gravada numa CÓPIA da semente em pasta temporária. Nada fala com o KCM: equipamento
novo nasce com protocolo não identificado e coleta desligada; arquivar não apaga o histórico.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from forja.config.loader import load_mapping, load_profile
from forja.config.writer import ConfigWriter
from forja.service.seed import seed_home
from tests.integration.api_testkit import ApiWorld

pytestmark = pytest.mark.integration

USER = "tecnico"
NEW = "PHA_DOSADOR_03"


def identity(**over: Any) -> dict[str, Any]:
    data = {
        "name": "Dosador 03",
        "plant": "Planta de teste",
        "area": "PHA",
        "line": "UNKNOWN",
        "application": "WBF",
        "application_evidence": "FIELD_OBSERVED",
        "notes_pt": "",
    }
    data.update(over)
    return data


async def _create(client: httpx.AsyncClient, **over: Any) -> httpx.Response:
    body = {"id": NEW, "identity": identity(**over), "user": USER, "reason_pt": "visita"}
    return await client.post("/api/v1/equipments", json=body)


async def test_criar_nasce_sem_protocolo_com_mapping_todo_desconhecido_e_auditado(
    cfg_client: httpx.AsyncClient, cfg_world: ApiWorld
) -> None:
    resp = await _create(cfg_client)
    assert resp.status_code == 201, resp.text
    view = resp.json()
    comm = view["profile"]["communication"]
    assert comm["driver"] == "UNKNOWN"
    assert comm["collection_enabled"] is False
    assert view["mapping"]["readable"] == 0
    assert "controller.software_version" in view["unknown_fields"]
    assert cfg_world.manager.added == [NEW]

    writer = ConfigWriter(cfg_world.container.paths)
    path = writer.find_profile_file(NEW)
    assert path is not None
    assert load_profile(path).name == "Dosador 03"
    assert "tela Equipamentos" in path.read_text(encoding="utf-8").splitlines()[0]
    mapping_path = writer.find_mapping_file("pha_dosador_03")
    assert mapping_path is not None
    assert all(e.protocol_address == "UNKNOWN" for e in load_mapping(mapping_path).entries)

    audit = await cfg_world.core.audit_list()
    assert audit[0]["action"] == "EQUIPMENT_CREATE"
    assert audit[0]["entity_id"] == NEW

    comm_view = (await cfg_client.get(f"/api/v1/communication/{NEW}")).json()
    assert comm_view["state"]["code"] == "PROTOCOL_UNKNOWN"


async def test_criar_recusa_id_repetido_e_invalido(
    cfg_client: httpx.AsyncClient,
) -> None:
    assert (await _create(cfg_client)).status_code == 201
    again = await _create(cfg_client)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "EQUIPMENT_EXISTS"
    bad = await cfg_client.post(
        "/api/v1/equipments", json={"id": "minusculo", "identity": identity(), "user": USER}
    )
    assert bad.status_code == 422
    bad_app = await _create(cfg_client, application="XYZ")
    assert bad_app.status_code == 422


async def test_ficha_tecnica_salva_com_evidencia_e_conflito(
    cfg_client: httpx.AsyncClient, cfg_world: ApiWorld
) -> None:
    eq = "GTEX_PHA_PO_BASE"
    sheet = (await cfg_client.get(f"/api/v1/equipments/{eq}/datasheet")).json()
    data = sheet["datasheet"]
    data["controller"]["software_version"] = "Ver de teste"
    data["host_interface"]["evidence"] = "FIELD_CONFIRMED"
    data["components"] = [
        {"type": "Encoder", "model": "UNKNOWN", "serial": "UNKNOWN", "evidence": "FIELD_OBSERVED"}
    ]
    body = {**data, "base_hash": sheet["config_hash"], "user": USER, "reason_pt": "visita"}
    resp = await cfg_client.post(f"/api/v1/equipments/{eq}/datasheet", json=body)
    assert resp.status_code == 200, resp.text
    saved = resp.json()
    assert saved["profile"]["controller"]["software_version"] == "Ver de teste"
    assert saved["profile"]["components"][0]["type"] == "Encoder"
    assert "controller.software_version" not in saved["unknown_fields"]
    # a comunicação não muda pela ficha
    assert saved["profile"]["communication"] == sheet["profile"]["communication"]
    audit = await cfg_world.core.audit_list()
    assert audit[0]["action"] == "EQUIPMENT_DATASHEET_SAVE"
    # quem viu a versão anterior não sobrescreve a nova
    stale = await cfg_client.post(f"/api/v1/equipments/{eq}/datasheet", json=body)
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "CONFIG_CONFLICT"


async def test_arquivar_e_restaurar_sem_apagar_nada(
    cfg_client: httpx.AsyncClient, cfg_world: ApiWorld
) -> None:
    eq = "EXEMPLO_KCM_03"
    wrong = await cfg_client.post(
        f"/api/v1/equipments/{eq}/archive",
        json={"confirm_id": "OUTRO", "user": USER, "reason_pt": "demo fora da planta"},
    )
    assert wrong.status_code == 422
    resp = await cfg_client.post(
        f"/api/v1/equipments/{eq}/archive",
        json={"confirm_id": eq, "user": USER, "reason_pt": "demo fora da planta"},
    )
    assert resp.status_code == 200, resp.text
    assert eq not in cfg_world.store.profiles
    assert cfg_world.manager.removed == [eq]
    assert (await cfg_client.get(f"/api/v1/equipments/{eq}")).status_code == 404
    archived = (await cfg_client.get("/api/v1/archived-equipments")).json()
    assert [a["equipment_id"] for a in archived["equipments"]] == [eq]

    # uma atualização do programa (init) não traz o exemplo arquivado de volta
    home = cfg_world.container.paths.home
    from forja.config.paths import find_repo_root

    created = seed_home(home, find_repo_root())
    assert not any("exemplo_kcm_03" in c for c in created)

    # criar com o id arquivado é recusado: restaurar é o caminho
    clash = await cfg_client.post(
        "/api/v1/equipments", json={"id": eq, "identity": identity(), "user": USER}
    )
    assert clash.status_code == 409
    assert clash.json()["error"]["code"] == "EQUIPMENT_ARCHIVED"

    restored = await cfg_client.post(
        f"/api/v1/archived-equipments/{eq}/restore", json={"user": USER, "reason_pt": "volta"}
    )
    assert restored.status_code == 200, restored.text
    assert eq in cfg_world.store.profiles
    assert (await cfg_client.get("/api/v1/archived-equipments")).json()["count"] == 0
    actions = [a["action"] for a in await cfg_world.core.audit_list()]
    assert actions[:2] == ["EQUIPMENT_RESTORE", "EQUIPMENT_ARCHIVE"]


async def test_catalogo_de_alarmes_separa_a_chave_do_equipamento(
    cfg_client: httpx.AsyncClient,
) -> None:
    wbf = (await cfg_client.get("/api/v1/equipments/EXEMPLO_BARRILHA/alarm-catalog")).json()
    assert wbf["key"]["application"] == "WBF"
    codes = [a["key"]["code"] for a in wbf["alarms"]]
    assert "56" in codes
    assert all(a["key"]["application"] == "WBF" for a in wbf["alarms"])
    assert "software_version" in wbf["key_unknown"]
    assert "combinação exata" in wbf["note_pt"]

    other = (await cfg_client.get("/api/v1/equipments/EXEMPLO_KCM_03/alarm-catalog")).json()
    assert "56" not in [a["key"]["code"] for a in other["alarms"]]
    assert "56" in [a["key"]["code"] for a in other["other_keys"]]
