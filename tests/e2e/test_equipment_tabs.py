"""Abas do dosador: Visão, Variáveis, Gráficos (Gráfico e Tabela) e Ocorrências.

Cada aba leva a uma rota que já existe; nenhuma tela some. A aba ativa fica marcada com
aria-current e, no celular, a faixa de abas rola sozinha sem rolar a página.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers import EQ_MAIN, open_route, overflow_info

pytestmark = pytest.mark.e2e


def test_abas_levam_as_telas_do_dosador(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, f"/app/eq/{EQ_MAIN}/dashboard", "dashboard")
    tabs = page.get_by_test_id("eq-tabs")
    expect(tabs.locator("[data-testid^='eq-tab-']")).to_have_text(
        ["Visão", "Variáveis", "Gráficos", "Ocorrências"]
    )
    expect(page.get_by_test_id("eq-tab-visao")).to_have_attribute("aria-current", "page")

    page.get_by_test_id("eq-tab-variaveis").click()
    expect(page).to_have_url(re.compile(rf"/app/eq/{EQ_MAIN}/realtime(\?.*)?$"))
    expect(page.get_by_test_id("realtime")).to_be_visible()

    page.get_by_test_id("eq-tab-graficos").click()
    expect(page).to_have_url(re.compile(rf"/app/eq/{EQ_MAIN}/trends(\?.*)?$"))
    page.get_by_test_id("eq-subtab-history").click()
    expect(page).to_have_url(re.compile(rf"/app/eq/{EQ_MAIN}/history(\?.*)?$"))
    expect(page.get_by_test_id("eq-tab-graficos")).to_have_attribute("aria-current", "page")
    expect(page.get_by_test_id("eq-subtab-history")).to_have_attribute("aria-current", "page")

    page.get_by_test_id("eq-tab-ocorrencias").click()
    expect(page).to_have_url(re.compile(rf"/app/eq/{EQ_MAIN}/alerts(\?.*)?$"))
    expect(tabs.locator("[data-testid^='eq-subtab-']")).to_have_text(
        ["Alertas", "Eventos", "Diagnósticos", "Aviso antecipado", "Casos anteriores"]
    )
    page.get_by_test_id("eq-subtab-cases").click()
    expect(page).to_have_url(re.compile(rf"/app/eq/{EQ_MAIN}/cases(\?.*)?$"))
    expect(page.get_by_test_id("eq-tab-ocorrencias")).to_have_attribute("aria-current", "page")


def test_abas_nao_aparecem_nas_telas_de_configuracao(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, f"/app/eq/{EQ_MAIN}/kcm/communication", "kcm-communication")
    expect(page.get_by_test_id("eq-tabs")).to_have_count(0)


def test_abas_cabem_no_celular(mobile_375: Page) -> None:
    page = mobile_375
    open_route(page, f"/app/eq/{EQ_MAIN}/alerts", "alerts")
    expect(page.get_by_test_id("eq-tabs")).to_be_visible()
    info = overflow_info(page)
    assert not info["overflow"], info
