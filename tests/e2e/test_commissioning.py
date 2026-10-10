"""Modo de comissionamento no navegador: abrir a visita, ler valores (somente leitura), registrar
conferências (inclusive "não exposta pelo KCM"), exportar o CSV e encerrar a sessão."""

from __future__ import annotations

import csv
import io

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers import EQ_MAIN, overflow_info

pytestmark = pytest.mark.e2e


def test_visita_completa_com_conferencias_csv_e_encerramento(desktop_1920: Page) -> None:
    page = desktop_1920
    page.goto(f"/app/eq/{EQ_MAIN}/kcm/commissioning", wait_until="load")
    expect(page.get_by_test_id("cm-header")).to_be_visible()
    page.get_by_test_id("cm-technician").fill("tecnico de teste")
    page.get_by_test_id("cm-authorized_by").fill("responsável de teste")
    page.get_by_test_id("cm-open").click()
    expect(page.get_by_test_id("cm-notice")).to_contain_text("Sessão aberta")

    page.get_by_test_id("cm-read").click()
    item = page.get_by_test_id("cm-item-mass_flow")
    expect(item).to_contain_text("kg/h")
    expect(item).to_contain_text("coleta")
    page.get_by_test_id("cm-kcm-mass_flow").fill("1.300,0")
    page.get_by_test_id("cm-result-mass_flow").select_option("MATCH")
    page.get_by_test_id("cm-register-mass_flow").click()
    expect(page.get_by_test_id("cm-notice")).to_contain_text("registrada")

    page.get_by_test_id("cm-result-rpm").select_option("NOT_EXPOSED")
    page.get_by_test_id("cm-register-rpm").click()
    table = page.get_by_test_id("cm-table")
    expect(table.locator("tbody tr")).to_have_count(2)
    expect(table).to_contain_text("Confere")
    expect(table).to_contain_text("Não exposta pelo KCM")

    href = page.get_by_test_id("cm-export").get_attribute("href")
    assert href
    resp = page.request.get(href)
    assert resp.ok
    text = resp.text().lstrip("﻿")
    assert "Técnico;tecnico de teste" in text
    rows = list(csv.reader(io.StringIO(text), delimiter=";"))
    assert any(r and r[-3:-2] == ["Confere"] for r in rows)

    page.get_by_test_id("cm-conclusion").fill("Vazão confere com a tela do KCM.")
    page.get_by_test_id("cm-finish").click()
    expect(page.get_by_test_id("cm-notice")).to_contain_text("encerrada")
    expect(page.get_by_test_id("cm-register-mass_flow")).to_have_count(0)
    expect(page.get_by_test_id("cm-close")).to_contain_text("Vazão confere")


def test_comissionamento_cabe_no_celular(mobile_375: Page) -> None:
    page = mobile_375
    page.goto(f"/app/eq/{EQ_MAIN}/kcm/commissioning", wait_until="load")
    expect(page.get_by_test_id("cm-header")).to_be_visible()
    info = overflow_info(page)
    assert not info["overflow"], info
