"""Modo de comissionamento: sessão da visita, conferências valor Forja x tela do KCM, encerramento
e relatório CSV. Nada afirma que a validação aconteceu: é o registro do que o técnico conferiu."""

from __future__ import annotations

import csv
import io
from typing import Any

import httpx
import pytest

from tests.integration.api_testkit import ApiWorld

pytestmark = pytest.mark.integration

EQ = "GTEX_PHA_PO_BASE"


async def _open(client: httpx.AsyncClient, **header: Any) -> dict[str, Any]:
    body = {"header": {"technician": "tecnico", "visit_date": "2026-10-20", **header}}
    resp = await client.post(f"/api/v1/equipments/{EQ}/commissioning", json=body)
    assert resp.status_code == 200, resp.text
    return dict(resp.json())


async def test_lista_vazia_traz_sugestoes_e_cabecalho_preenchido_do_perfil(
    client: httpx.AsyncClient,
) -> None:
    resp = await client.get(f"/api/v1/equipments/{EQ}/commissioning")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sessions"] == []
    assert {"setpoint", "mass_flow", "drive_command", "rpm", "belt_load"} <= set(
        body["suggested_tags"]
    )
    prefill = body["prefill"]
    assert prefill["protocol_found"] == "UNKNOWN"  # perfil ainda não sabe: nada é suposto
    assert prefill["kcm_software_version"] == "UNKNOWN"


async def test_sessao_conferencias_encerramento_e_csv(
    client: httpx.AsyncClient, world: ApiWorld
) -> None:
    session = await _open(
        client, authorized_by="responsável da planta", protocol_found="em apuração"
    )
    sid = session["session"]["id"]
    assert session["session"]["status"] == "OPEN"
    assert world.core.audits[-1]["action"] == "COMMISSIONING_OPEN"

    check = {
        "tag": "mass_flow",
        "address_text": "Holding register (função 03), endereço 0",
        "forja_value": 1290.0,
        "forja_quality": "UNCERTAIN",
        "kcm_value": 1291.5,
        "result": "MATCH",
        "note_pt": "lido na tela principal",
        "technician": "tecnico",
    }
    resp = await client.post(f"/api/v1/commissioning/{sid}/checks", json=check)
    assert resp.status_code == 200, resp.text
    assert resp.json()["check"]["difference"] == pytest.approx(1.5)
    resp = await client.post(
        f"/api/v1/commissioning/{sid}/checks",
        json={"tag": "rpm", "result": "NOT_EXPOSED", "technician": "tecnico"},
    )
    assert resp.status_code == 200

    resp = await client.get(f"/api/v1/commissioning/{sid}")
    detail = resp.json()
    assert [c["tag"] for c in detail["checks"]] == ["mass_flow", "rpm"]
    assert detail["summary"]["MATCH"] == 1
    assert detail["summary"]["NOT_EXPOSED"] == 1

    resp = await client.post(
        f"/api/v1/commissioning/{sid}/close",
        json={"conclusion_pt": "Vazão confere; velocidade não exposta.", "technician": "tecnico"},
    )
    assert resp.status_code == 200
    assert resp.json()["session"]["status"] == "CLOSED"
    assert world.core.audits[-1]["action"] == "COMMISSIONING_CLOSE"

    # encerrada é final
    resp = await client.post(f"/api/v1/commissioning/{sid}/checks", json=check)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "SESSION_CLOSED"

    resp = await client.get(f"/api/v1/commissioning/{sid}/report.csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    text = resp.text.lstrip("﻿")
    assert "Técnico;tecnico" in text
    assert "Conclusão;Vazão confere; velocidade não exposta." not in text  # ; escapado pelo CSV
    rows = list(csv.reader(io.StringIO(text), delimiter=";"))
    table_start = next(i for i, r in enumerate(rows) if r and r[0] == "data_hora_utc")
    header = rows[table_start]
    first = dict(zip(header, rows[table_start + 1], strict=True))
    assert first["variavel"] == "Vazão"
    assert first["valor_forja"] == "1290,0"
    assert first["valor_kcm"] == "1291,5"
    assert first["resultado"] == "Confere"


async def test_cabecalho_so_muda_com_sessao_aberta(client: httpx.AsyncClient) -> None:
    sid = (await _open(client))["session"]["id"]
    resp = await client.post(
        f"/api/v1/commissioning/{sid}/header",
        json={
            "header": {"technician": "tecnico", "visit_date": "2026-10-20", "ip": "[IP do módulo]"},
            "user": "tecnico",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["session"]["header"]["ip"] == "[IP do módulo]"
    await client.post(
        f"/api/v1/commissioning/{sid}/close", json={"conclusion_pt": "ok", "technician": "tecnico"}
    )
    resp = await client.post(
        f"/api/v1/commissioning/{sid}/header",
        json={"header": {"technician": "tecnico", "visit_date": "2026-10-20"}, "user": "tecnico"},
    )
    assert resp.status_code == 409


async def test_conferencia_com_tag_desconhecida_e_recusada(client: httpx.AsyncClient) -> None:
    sid = (await _open(client))["session"]["id"]
    resp = await client.post(
        f"/api/v1/commissioning/{sid}/checks",
        json={"tag": "nao_existe", "result": "MATCH", "technician": "tecnico"},
    )
    assert resp.status_code == 422


async def test_sessao_inexistente_404(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/commissioning/naoexiste0001")
    assert resp.status_code == 404
