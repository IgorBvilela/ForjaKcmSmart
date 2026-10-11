"""Resumo do turno (/app/tools/shift-summary): a folha para imprimir no fim do turno.

Sem turnos na configuração da planta, a tela pede o período; com turnos, mostra os turnos da
configuração e já escolhe o que está em andamento. A folha traz um cartão por dosador (tempo
dentro do normal, fora do normal e sem dados, e o que aconteceu), observações e assinatura, e
cabe numa página A4. Os turnos do teste são de exemplo; os da planta vêm de `config/forja.yaml`.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from playwright.sync_api import Browser, Page, expect

from tests.e2e.conftest import running_edge, seed_home
from tests.e2e.helpers import ALL_EQUIPMENTS, open_route

pytestmark = pytest.mark.e2e

PATH = "/app/tools/shift-summary"
SLUG = "tools-shift-summary"
PLANT_ZONE = ZoneInfo("America/Sao_Paulo")
TEST_SHIFTS = """  shifts:
    - name: "Turno 1"
      start: "06:00"
      end: "14:00"
    - name: "Turno 2"
      start: "14:00"
      end: "22:00"
    - name: "Turno 3"
      start: "22:00"
      end: "06:00"
"""


def test_without_shifts_the_sheet_asks_for_the_period(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, PATH, SLUG)
    expect(page.get_by_test_id("shift-not-configured")).to_be_visible()
    expect(page.get_by_test_id("shift-from")).not_to_have_value("")
    sheet = page.get_by_test_id("shift-sheet")
    expect(sheet).to_be_visible()
    for eq in ALL_EQUIPMENTS:
        card = sheet.get_by_test_id(f"shift-card-{eq}")
        expect(card).to_be_visible()
        expect(card).to_contain_text("Dentro do normal")
        expect(card.get_by_role("img")).to_have_attribute(
            "aria-label",
            re.compile(r"% dentro do normal, .*% fora do normal e .*% sem dados"),
        )
    expect(sheet).to_contain_text("Observações")
    expect(page.get_by_test_id("shift-signature")).to_contain_text("Responsável pelo turno")
    expect(page.get_by_test_id("shift-source")).to_contain_text("Dados simulados")
    expect(sheet).to_contain_text("A Forja observa o KCM e não comanda nada.")


def test_a_reversed_period_is_refused_before_asking_the_edge(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, PATH, SLUG)
    expect(page.get_by_test_id("shift-sheet")).to_be_visible()
    page.get_by_test_id("shift-to").fill("2020-01-01T00:00")
    expect(page.get_by_test_id("shift-range-error")).to_have_text(
        "O fim precisa ser depois do início."
    )
    expect(page.get_by_test_id("shift-sheet")).to_have_count(0)


def test_the_sheet_fits_on_one_a4_page_without_the_controls(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, PATH, SLUG)
    expect(page.get_by_test_id("shift-sheet")).to_be_visible()
    page.emulate_media(media="print")
    expect(page.get_by_test_id("shift-controls")).to_be_hidden()
    expect(page.get_by_test_id("page-head")).to_be_hidden()
    pdf = page.pdf(prefer_css_page_size=True, print_background=True)
    pages = len(re.findall(rb"/Type\s*/Page\b", pdf))
    assert pages == 1, f"a folha saiu em {pages} páginas"


def test_mobile_sheet_has_no_sideways_scroll(mobile_375: Page) -> None:
    page = mobile_375
    open_route(page, PATH, SLUG)
    expect(page.get_by_test_id("shift-sheet")).to_be_visible()
    width = page.evaluate("document.documentElement.scrollWidth")
    assert width <= 375, width


def test_configured_shifts_come_from_the_plant_and_the_running_one_is_chosen(
    browser: Browser, tmp_path_factory: pytest.TempPathFactory
) -> None:
    home = seed_home(tmp_path_factory.mktemp("forja_e2e_shift_home"))
    config = home / "config" / "forja.yaml"
    text = config.read_text(encoding="utf-8")
    assert text.count("  shifts: []\n") == 1
    config.write_text(text.replace("  shifts: []\n", TEST_SHIFTS), encoding="utf-8")
    with running_edge(home, tmp_path_factory.mktemp("forja_e2e_shift_data")) as edge:
        ctx = browser.new_context(
            viewport={"width": 1366, "height": 900},
            base_url=edge.base_url,
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            color_scheme="dark",
            reduced_motion="reduce",
        )
        try:
            page = ctx.new_page()
            open_route(page, PATH, SLUG)
            expect(page.locator("[data-testid^='shift-chip-']")).to_have_count(3)
            running = page.locator("[data-testid^='shift-chip-'][aria-pressed='true']")
            expect(running).to_have_count(1)
            period = page.get_by_test_id("shift-period")
            expect(period).to_contain_text(re.compile(r"Turno [123] · \d{2}:\d{2} às \d{2}:\d{2}"))
            expect(page.get_by_test_id("shift-in-progress")).to_contain_text("em andamento")
            # o turno 1 de ontem já terminou: folha completa, sem "em andamento"
            yesterday = (datetime.now(PLANT_ZONE) - timedelta(days=1)).date().isoformat()
            page.get_by_test_id("shift-date").fill(yesterday)
            page.get_by_test_id("shift-chip-0").click()
            expect(page.get_by_test_id("shift-chip-0")).to_have_attribute("aria-pressed", "true")
            expect(period).to_contain_text("Turno 1 · 06:00 às 14:00")
            expect(page.get_by_test_id("shift-in-progress")).to_have_count(0)
            expect(page.get_by_test_id("shift-not-configured")).to_have_count(0)
        finally:
            ctx.close()
