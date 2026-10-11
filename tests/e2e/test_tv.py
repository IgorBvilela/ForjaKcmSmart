"""Modo TV (/app/tv): a tela Agora e a Planta juntas, para ler de longe. Sem menu e sem nenhum
controle; relógio, "atualizado há" e o selo de dados simulados; a tela Agora não sai de vista com
problema; as páginas da Planta trocam sozinhas quando não cabem; Edge sem resposta em destaque.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Browser, Page, expect

from tests.e2e.conftest import running_edge, seed_home
from tests.e2e.helpers import EQ_BARRILHA, EVENT_TIMEOUT_MS

pytestmark = pytest.mark.e2e

CONTROLS = "button, a[href], input, select, textarea, [tabindex]:not([tabindex='-1'])"


def open_tv(page: Page, query: str = "") -> None:
    page.goto(f"/app/tv{query}", wait_until="load")
    expect(page.get_by_test_id("tv-headline")).to_be_visible()


def test_tv_has_no_menu_no_header_and_no_controls(desktop_1920: Page) -> None:
    page = desktop_1920
    open_tv(page)
    expect(page).to_have_title("Modo TV · Forja KCM Intelligence")
    expect(page.get_by_test_id("sidebar")).to_have_count(0)
    expect(page.get_by_test_id("header")).to_have_count(0)
    assert page.locator(CONTROLS).count() == 0


def test_tv_shows_clock_update_age_and_simulated_seal(desktop_1920: Page) -> None:
    page = desktop_1920
    open_tv(page)
    expect(page.get_by_test_id("tv-clock")).to_contain_text(re.compile(r"\d{2}:\d{2}"))
    expect(page.get_by_test_id("tv-updated")).to_contain_text("atualizado")
    expect(page.get_by_test_id("tv-simulated")).to_have_text(re.compile("dados simulados", re.I))


def test_tv_keeps_the_agora_side_in_view_with_a_problem(desktop_1920: Page) -> None:
    page = desktop_1920
    open_tv(page)
    problem = page.get_by_test_id(f"tv-problem-{EQ_BARRILHA}")
    expect(problem).to_be_visible(timeout=EVENT_TIMEOUT_MS)
    expect(page.get_by_test_id("tv-headline")).to_contain_text("em atenção")
    box = problem.bounding_box()
    assert box is not None
    assert box["y"] + box["height"] <= 1080, box
    # o cartão do dosador na Planta também aparece, ao lado
    expect(page.get_by_test_id(f"tv-card-{EQ_BARRILHA}")).to_be_visible()


def test_tv_plant_pages_swap_by_themselves(desktop_1920: Page) -> None:
    page = desktop_1920
    page.set_viewport_size({"width": 1920, "height": 420})
    open_tv(page, "?troca=5")
    pages = page.get_by_test_id("tv-pages")
    expect(pages).to_contain_text(re.compile(r"Página 1 de \d"))
    expect(pages).to_contain_text(re.compile(r"Página 2 de \d"), timeout=12_000)
    # a tela Agora continua à vista enquanto a Planta troca de página
    expect(page.get_by_test_id("tv-now")).to_be_visible()


def test_tv_highlights_an_edge_without_response(
    browser: Browser, tmp_path_factory: pytest.TempPathFactory
) -> None:
    home = seed_home(tmp_path_factory.mktemp("forja_e2e_tv_home"))
    with running_edge(home, tmp_path_factory.mktemp("forja_e2e_tv_data")) as edge:
        ctx = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            base_url=edge.base_url,
            locale="pt-BR",
            reduced_motion="reduce",
        )
        page = ctx.new_page()
        open_tv(page)
        expect(page.get_by_test_id("tv-offline")).to_have_count(0)
    # Edge derrubado: sem pulso por mais de 12 s, a TV avisa em destaque
    try:
        offline = page.get_by_test_id("tv-offline")
        expect(offline).to_be_visible(timeout=30_000)
        expect(offline).to_contain_text("Edge sem resposta")
        expect(offline).to_contain_text("os valores na tela são os últimos recebidos")
        expect(page.get_by_test_id("tv-updated")).to_have_attribute("data-offline", "true")
    finally:
        ctx.close()
