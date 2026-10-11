"""Modo TV (/app/tv): a tela Agora e a Planta juntas, para ler de longe. Sem menu e sem nenhum
controle; relógio, "atualizado há" e o selo de dados simulados; a tela Agora não sai de vista com
problema; as páginas da Planta trocam sozinhas quando não cabem; Edge sem resposta em destaque;
placar do dia (tempo dentro do normal desde a meia-noite) do pior para o melhor.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Browser, Page, expect

from tests.e2e.conftest import running_edge, seed_home
from tests.e2e.helpers import ALL_EQUIPMENTS, EQ_BARRILHA, EQ_KCM03, EVENT_TIMEOUT_MS

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


def test_tv_day_scoreboard_lists_every_doser_worst_first(desktop_1920: Page) -> None:
    page = desktop_1920
    open_tv(page)
    board = page.get_by_test_id("tv-today")
    expect(board).to_be_visible()
    expect(board).to_have_attribute("data-visible", "true")
    expect(board).to_contain_text("Hoje, dentro do normal")
    rows = board.locator("[data-testid^='tv-today-']")
    expect(rows).to_have_count(len(ALL_EQUIPMENTS))
    pcts = [float(row.get_attribute("data-normal-pct") or "nan") for row in rows.all()]
    assert pcts == sorted(pcts), f"placar fora da ordem do pior para o melhor: {pcts}"
    for i in range(rows.count()):
        row = rows.nth(i)
        expect(row).to_contain_text(re.compile(r"(\d{1,3}|<1)%"))
        expect(row).to_contain_text(re.compile(r"(\d+ h \d{2} min|\d+ min|<1 min)"))
        expect(row.get_by_role("img")).to_have_attribute(
            "aria-label",
            re.compile(r"% do dia dentro do normal, .*% fora do normal e .*% sem dados"),
        )
    # o dosador sem comunicação desde o boot tem a parte "sem dados" na barra
    no_data = page.get_by_test_id(f"tv-today-{EQ_KCM03}").get_by_role("img")
    assert float(no_data.get_attribute("data-no-data") or "0") > 0
    # fica do lado Agora, embaixo da frase do gerente
    headline = page.get_by_test_id("tv-headline").bounding_box()
    box = board.bounding_box()
    assert headline is not None
    assert box is not None
    assert box["y"] > headline["y"], box
    assert box["x"] < 960, box
    assert box["y"] + box["height"] <= 1080, box


def test_tv_day_scoreboard_gives_way_to_problems_on_a_short_screen(desktop_1920: Page) -> None:
    page = desktop_1920
    page.set_viewport_size({"width": 1920, "height": 420})
    open_tv(page)
    expect(page.get_by_test_id(f"tv-problem-{EQ_BARRILHA}")).to_be_visible(timeout=EVENT_TIMEOUT_MS)
    board = page.get_by_test_id("tv-today")
    expect(board).to_have_attribute("data-visible", "false")
    expect(board).to_have_attribute("aria-hidden", "true")
    expect(board).to_be_hidden()


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
