"""Central de Comunicação: configuração, mapping, teste somente leitura e ativação da coleta.

Configuração gravada numa CÓPIA da semente em pasta temporária (nada toca o config/ do repo).
Regras provadas: conflito de versão/hash; mapping compartilhado não é editável; a rota de
configuração nunca liga a coleta; mudar o que afeta a leitura pausa a coleta de driver real;
ativar coleta de driver real exige teste somente leitura bem-sucedido da configuração salva;
toda gravação é auditada.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from forja.config.loader import load_profile
from forja.config.writer import ConfigWriter
from tests.integration.api_testkit import ApiWorld

pytestmark = pytest.mark.integration

EQ = "GTEX_PHA_PO_BASE"
OWN_MAPPING = "gtex_pha_po_base"
USER = "tecnico"


async def _view(client: httpx.AsyncClient, eq: str = EQ) -> dict[str, Any]:
    resp = await client.get(f"/api/v1/communication/{eq}")
    assert resp.status_code == 200, resp.text
    return dict(resp.json())


def _modbus_comm(view: dict[str, Any], **changes: Any) -> dict[str, Any]:
    comm = dict(view["profile"]["communication"])
    comm.update(
        {
            "driver": "modbus_tcp",
            "protocol": "modbus_tcp",
            "ip": "127.0.0.1",
            "port": 1502,
            "unit_id": 1,
            "options": {},
        }
    )
    comm.update(changes)
    return comm


def _own_mapping(world: ApiWorld, *, address: int = 0) -> dict[str, Any]:
    mapping = world.store.mappings[OWN_MAPPING].model_dump(mode="json")
    mapping["driver"] = "modbus_tcp"
    for entry in mapping["entries"]:
        if entry["semantic_tag"] == "mass_flow":
            entry.update(
                {
                    "protocol_address": {"area": "holding", "address": address},
                    "datatype": "float32",
                    "endianness": "big",
                    "scale": {"factor": 1, "offset": 0},
                    "source": "teste: documento fictício, página 1",
                }
            )
    return dict(mapping)


async def _switch_to_modbus(client: httpx.AsyncClient, world: ApiWorld) -> dict[str, Any]:
    view = await _view(client)
    resp = await client.post(
        f"/api/v1/communication/{EQ}/mapping",
        json={"mapping": _own_mapping(world), "base_version": 1, "user": USER},
    )
    assert resp.status_code == 200, resp.text
    view = await _view(client)
    resp = await client.post(
        f"/api/v1/communication/{EQ}/config",
        json={
            "communication": _modbus_comm(view),
            "mapping_profile": OWN_MAPPING,
            "base_hash": view["config_hash"],
            "user": USER,
            "reason_pt": "protocolo confirmado na tela do KCM",
        },
    )
    assert resp.status_code == 200, resp.text
    return dict(resp.json())


async def test_visao_inicial_mostra_simulador_e_mapping_compartilhado(
    cfg_client: httpx.AsyncClient,
) -> None:
    view = await _view(cfg_client)
    assert view["state"]["code"] == "SIMULATED"
    assert view["mapping_shared"] is True
    assert len(view["config_hash"]) == 64
    assert view["read_only"] is True
    assert view["drivers"]["modbus_tcp"]["state"] == "EXPERIMENTAL"


async def test_validacao_sem_rede_aponta_o_que_falta(
    cfg_client: httpx.AsyncClient, cfg_world: ApiWorld
) -> None:
    view = await _view(cfg_client)
    resp = await cfg_client.post(
        f"/api/v1/communication/{EQ}/validate",
        json={
            "communication": _modbus_comm(view, port="UNKNOWN"),
            "mapping": _own_mapping(cfg_world),
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert any("porta não informada" in e for e in body["errors"])
    resp = await cfg_client.post(
        f"/api/v1/communication/{EQ}/validate",
        json={"communication": _modbus_comm(view), "mapping": _own_mapping(cfg_world)},
    )
    body = resp.json()
    assert body["ok"] is True
    assert body["blocks"] == [
        {
            "block_id": "holding:0:2",
            "area": "holding",
            "address": 0,
            "count": 2,
            "tags": ["mass_flow"],
        }
    ]
    assert any("experimental" in w for w in body["warnings"])
    assert cfg_world.manager.test_read_calls == []


async def test_mapping_compartilhado_do_simulador_nao_e_editavel(
    cfg_client: httpx.AsyncClient, cfg_world: ApiWorld
) -> None:
    sim = cfg_world.store.mappings["simulator_wbf"].model_dump(mode="json")
    sim["equipment_id"] = EQ
    resp = await cfg_client.post(
        f"/api/v1/communication/{EQ}/mapping",
        json={"mapping": sim, "base_version": 1, "user": USER},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "MAPPING_SHARED"


async def test_mapping_proprio_ganha_versao_historico_e_auditoria(
    cfg_client: httpx.AsyncClient, cfg_world: ApiWorld
) -> None:
    resp = await cfg_client.post(
        f"/api/v1/communication/{EQ}/mapping",
        json={"mapping": _own_mapping(cfg_world), "base_version": 1, "user": USER},
    )
    assert resp.status_code == 200, resp.text
    assert cfg_world.store.mappings[OWN_MAPPING].version == 2
    writer = ConfigWriter(cfg_world.container.paths)
    assert list((writer.history_dir / "mappings").glob(f"{OWN_MAPPING}__*.yaml"))
    assert cfg_world.core.audits[-1]["action"] == "MAPPING_SAVE"
    # quem editou a versão 1 de novo perde: conflito, nada gravado
    resp = await cfg_client.post(
        f"/api/v1/communication/{EQ}/mapping",
        json={"mapping": _own_mapping(cfg_world, address=10), "base_version": 1, "user": USER},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFIG_CONFLICT"
    assert cfg_world.store.mappings[OWN_MAPPING].version == 2


async def test_mapping_com_endereco_incoerente_e_recusado(
    cfg_client: httpx.AsyncClient, cfg_world: ApiWorld
) -> None:
    mapping = _own_mapping(cfg_world)
    for entry in mapping["entries"]:
        if entry["semantic_tag"] == "mass_flow":
            entry["protocol_address"] = {"area": "registrador_magico", "address": 0}
    resp = await cfg_client.post(
        f"/api/v1/communication/{EQ}/mapping",
        json={"mapping": mapping, "base_version": 1, "user": USER},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "MAPPING_INVALID"


async def test_trocar_para_modbus_grava_audita_e_pausa_a_coleta(
    cfg_client: httpx.AsyncClient, cfg_world: ApiWorld
) -> None:
    body = await _switch_to_modbus(cfg_client, cfg_world)
    assert body["collection_paused_by_change"] is True
    assert body["collection"]["enabled"] is False
    assert body["state"]["code"] == "EXPERIMENTAL"
    saved = load_profile(ConfigWriter(cfg_world.container.paths).find_profile_file(EQ))  # type: ignore[arg-type]
    assert saved.communication.driver == "modbus_tcp"
    assert saved.communication.collection_enabled is False
    assert saved.mapping_profile == OWN_MAPPING
    assert EQ in cfg_world.manager.reloads
    actions = [a["action"] for a in cfg_world.core.audits]
    assert actions[-2:] == ["MAPPING_SAVE", "COMM_CONFIG_SAVE"]
    assert cfg_world.core.audits[-1]["reason_pt"] == "protocolo confirmado na tela do KCM"


async def test_hash_antigo_e_conflito(cfg_client: httpx.AsyncClient) -> None:
    view = await _view(cfg_client)
    resp = await cfg_client.post(
        f"/api/v1/communication/{EQ}/config",
        json={
            "communication": view["profile"]["communication"],
            "base_hash": "0" * 64,
            "user": USER,
        },
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "CONFIG_CONFLICT"


async def test_rota_de_configuracao_nunca_liga_a_coleta(
    cfg_client: httpx.AsyncClient, cfg_world: ApiWorld
) -> None:
    await _switch_to_modbus(cfg_client, cfg_world)
    view = await _view(cfg_client)
    comm = dict(view["profile"]["communication"])
    comm["collection_enabled"] = True
    comm["poll_interval_s"] = 2.0
    resp = await cfg_client.post(
        f"/api/v1/communication/{EQ}/config",
        json={"communication": comm, "base_hash": view["config_hash"], "user": USER},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["collection"]["enabled"] is False


async def test_ativar_coleta_exige_teste_somente_leitura_da_configuracao_salva(
    cfg_client: httpx.AsyncClient, cfg_world: ApiWorld
) -> None:
    await _switch_to_modbus(cfg_client, cfg_world)
    resp = await cfg_client.post(
        f"/api/v1/communication/{EQ}/collection", json={"active": True, "user": USER}
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "READ_TEST_REQUIRED"

    view = await _view(cfg_client)
    resp = await cfg_client.post(
        "/api/v1/communication/test-read",
        json={"profile": view["profile"], "mapping": view["mapping"], "user": USER},
    )
    assert resp.status_code == 200, resp.text
    test = resp.json()
    assert test["success"] is True
    assert test["fingerprint"] == view["fingerprint"]
    assert cfg_world.core.read_tests[-1]["fingerprint"] == view["fingerprint"]
    assert (await _view(cfg_client))["state"]["code"] == "READ_TEST_OK"

    resp = await cfg_client.post(
        f"/api/v1/communication/{EQ}/collection",
        json={"active": True, "user": USER, "reason_pt": "leitura conferida"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["collection"]["enabled"] is True
    assert cfg_world.core.audits[-1]["action"] == "COLLECTION_ON"

    resp = await cfg_client.post(
        f"/api/v1/communication/{EQ}/collection", json={"active": False, "user": USER}
    )
    assert resp.status_code == 200
    assert resp.json()["collection"]["enabled"] is False
    assert cfg_world.core.audits[-1]["action"] == "COLLECTION_OFF"


async def test_teste_que_falhou_nao_libera_a_coleta(
    cfg_client: httpx.AsyncClient, cfg_world: ApiWorld
) -> None:
    from forja.domain import ReadTestStage
    from tests.integration.api_testkit import FakeReadTestResult

    await _switch_to_modbus(cfg_client, cfg_world)
    now = cfg_world.clock.now_utc()
    cfg_world.manager.test_read_result = FakeReadTestResult(
        stages=[
            (ReadTestStage.CONNECTING, now, "Conectando"),
            (ReadTestStage.TIMEOUT, now, "Timeout"),
        ],
        final=ReadTestStage.TIMEOUT,
        values={},
        latency_ms=None,
        error_pt="Timeout",
    )
    view = await _view(cfg_client)
    resp = await cfg_client.post(
        "/api/v1/communication/test-read",
        json={"profile": view["profile"], "mapping": view["mapping"], "user": USER},
    )
    assert resp.json()["success"] is False
    assert (await _view(cfg_client))["state"]["code"] == "READ_TEST_FAILED"
    resp = await cfg_client.post(
        f"/api/v1/communication/{EQ}/collection", json={"active": True, "user": USER}
    )
    assert resp.status_code == 409


async def test_historico_de_testes_e_log_tecnico(
    cfg_client: httpx.AsyncClient, cfg_world: ApiWorld
) -> None:
    view = await _view(cfg_client)
    await cfg_client.post(
        "/api/v1/communication/test-read",
        json={"profile": view["profile"], "mapping": view["mapping"]},
    )
    resp = await cfg_client.get(f"/api/v1/communication/{EQ}/read-tests")
    assert resp.status_code == 200
    assert len(resp.json()["tests"]) == 1
    resp = await cfg_client.get(f"/api/v1/communication/{EQ}/log")
    assert resp.status_code == 200
    assert "entries" in resp.json()


async def test_mapping_editavel_e_o_proprio_do_equipamento(
    cfg_client: httpx.AsyncClient, cfg_world: ApiWorld
) -> None:
    view = await _view(cfg_client)
    assert view["mapping_shared"] is True
    assert view["editable_mapping"]["mapping_id"] == OWN_MAPPING
    assert view["editable_mapping_exists"] is True


async def test_sem_mapping_proprio_a_tela_recebe_modelo_todo_unknown(
    cfg_client: httpx.AsyncClient, cfg_world: ApiWorld
) -> None:
    eq = "EXEMPLO_BARRILHA"
    view = await _view(cfg_client, eq)
    editable = view["editable_mapping"]
    assert view["editable_mapping_exists"] is False
    assert editable["mapping_id"] == eq.lower()
    assert editable["equipment_id"] == eq
    assert editable["driver"] == "UNKNOWN"
    assert all(e["protocol_address"] == "UNKNOWN" for e in editable["entries"])
    # o modelo pode ser gravado como mapping novo (base_version nulo)
    editable["driver"] = "modbus_tcp"
    resp = await cfg_client.post(
        f"/api/v1/communication/{eq}/mapping",
        json={"mapping": editable, "base_version": None, "user": USER},
    )
    assert resp.status_code == 200, resp.text
    assert cfg_world.store.mappings[eq.lower()].version == 1


async def test_coleta_bloqueada_na_partida_aparece_e_reativa_depois_do_teste(
    cfg_client: httpx.AsyncClient, cfg_world: ApiWorld
) -> None:
    from forja.service.commcenter import READ_TEST_PENDING_PT

    await _switch_to_modbus(cfg_client, cfg_world)
    # arquivo pede coleta (editado à mão), mas a porteira bloqueou na partida
    profile = cfg_world.store.profiles[EQ]
    cfg_world.store.profiles[EQ] = profile.model_copy(
        update={
            "communication": profile.communication.model_copy(update={"collection_enabled": True})
        }
    )
    cfg_world.manager.set_status(EQ, detail_pt=READ_TEST_PENDING_PT)
    view = await _view(cfg_client)
    assert view["collection"]["blocked"] is True
    assert view["collection"]["label_pt"] == READ_TEST_PENDING_PT

    # sem teste, reativar continua recusado
    resp = await cfg_client.post(
        f"/api/v1/communication/{EQ}/collection", json={"active": True, "user": USER}
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "READ_TEST_REQUIRED"

    resp = await cfg_client.post(
        "/api/v1/communication/test-read",
        json={"profile": view["profile"], "mapping": view["mapping"], "user": USER},
    )
    assert resp.json()["success"] is True
    reloads = len(cfg_world.manager.reloads)
    resp = await cfg_client.post(
        f"/api/v1/communication/{EQ}/collection",
        json={"active": True, "user": USER, "reason_pt": "teste feito"},
    )
    assert resp.status_code == 200, resp.text
    assert len(cfg_world.manager.reloads) == reloads + 1
    assert cfg_world.core.audits[-1]["action"] == "COLLECTION_ON"
    assert cfg_world.core.audits[-1]["before"] == {"collection_enabled": True, "blocked": True}
