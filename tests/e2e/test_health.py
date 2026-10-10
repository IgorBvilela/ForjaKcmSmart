"""Sistema › Saúde e logs: estado de cada parte em português, equipamento sem comunicação
apontado, registros do serviço, da comunicação e da auditoria, exportação CSV."""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers import overflow_info

pytestmark = pytest.mark.e2e


def test_saude_aponta_equipamento_sem_comunicacao(desktop_1920: Page) -> None:
    page = desktop_1920
    page.goto("/app/system/logs", wait_until="load")
    expect(page.get_by_test_id("health-status")).to_be_visible()
    table = page.get_by_test_id("health-equipment")
    expect(table).to_contain_text("KCM 03 (exemplo)")
    expect(table).to_contain_text("Erro de comunicação")
    expect(page.get_by_test_id("health-findings")).to_contain_text("sem leitura válida")
    expect(page.get_by_test_id("health-storage")).to_contain_text("Historiador")


def test_registros_por_fonte_e_exportacao(desktop_1366: Page) -> None:
    page = desktop_1366
    page.goto("/app/system/logs", wait_until="load")
    expect(page.get_by_test_id("health-status")).to_be_visible()
    page.get_by_test_id("logs-tab-comm").click()
    expect(page.get_by_test_id("logs-list")).to_have_attribute("data-count", re.compile(r"^[1-9]"))
    expect(page.get_by_test_id("logs-list")).to_contain_text("Erro de comunicação")
    page.get_by_test_id("logs-tab-app").click()
    expect(page.get_by_test_id("logs-list")).to_have_attribute("data-count", re.compile(r"^[1-9]"))
    href = page.get_by_test_id("logs-export").get_attribute("href")
    assert href
    resp = page.request.get(href)
    assert resp.ok
    assert resp.text().lstrip("﻿").startswith("instante;nivel;origem;mensagem;detalhe")


def test_saude_cabe_no_celular(mobile_375: Page) -> None:
    page = mobile_375
    page.goto("/app/system/logs", wait_until="load")
    expect(page.get_by_test_id("health-status")).to_be_visible()
    info = overflow_info(page)
    assert not info["overflow"], info


def test_conferir_cadeia_da_auditoria(desktop_1366: Page) -> None:
    page = desktop_1366
    page.goto("/app/system/logs", wait_until="load")
    expect(page.get_by_test_id("health-status")).to_be_visible()
    page.get_by_test_id("logs-tab-audit").click()
    page.get_by_test_id("audit-chain-verify").click()
    expect(page.get_by_test_id("audit-chain-result")).to_contain_text("íntegra")
