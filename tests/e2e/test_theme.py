"""Tema claro opcional (opção C da prévia dos extras): a interface segue o tema do Windows; a
página Mais fixa escuro ou claro, com a escolha guardada no navegador; o Modo TV segue o tema; a
impressão continua sempre clara. O tema vale desde a primeira pintura, antes do app montar.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, expect

from tests.e2e.conftest import Edge
from tests.e2e.helpers import open_route

pytestmark = pytest.mark.e2e

LIGHT_BG = "rgb(243, 243, 242)"
DARK_BG = "rgb(20, 21, 22)"
WHITE = "rgb(255, 255, 255)"


@pytest.fixture
def windows_light(browser: Browser, edge: Edge) -> Iterator[Page]:
    """Página com o Windows (o navegador) no tema claro."""
    ctx: BrowserContext = browser.new_context(
        viewport={"width": 1366, "height": 900},
        base_url=edge.base_url,
        locale="pt-BR",
        timezone_id="America/Sao_Paulo",
        color_scheme="light",
        reduced_motion="reduce",
    )
    try:
        yield ctx.new_page()
    finally:
        ctx.close()


def theme_of(page: Page) -> str | None:
    return page.evaluate("document.documentElement.dataset.theme")


def background_of(page: Page) -> str:
    return page.evaluate("getComputedStyle(document.body).backgroundColor")


def test_follows_the_light_windows_theme_by_default(windows_light: Page) -> None:
    page = windows_light
    open_route(page, "/app/now", "now")
    assert theme_of(page) == "light"
    assert background_of(page) == LIGHT_BG
    expect(page.locator("meta[name='theme-color']")).to_have_attribute("content", "#FFFFFF")


def test_follows_the_dark_windows_theme_by_default(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, "/app/now", "now")
    assert theme_of(page) == "dark"
    assert background_of(page) == DARK_BG


def test_choice_on_the_gear_page_overrides_windows_and_is_remembered(
    windows_light: Page,
) -> None:
    page = windows_light
    open_route(page, "/app/more", "more")
    group = page.get_by_role("radiogroup", name="Aparência")
    expect(
        group.get_by_role("radio", name=re.compile(r"^Igual ao Windows \(agora claro\)"))
    ).to_be_checked()
    group.get_by_text("Escuro", exact=True).click()
    expect(group.get_by_role("radio", name="Escuro", exact=True)).to_be_checked()
    assert theme_of(page) == "dark"
    # a escolha volta na próxima abertura, antes mesmo do app montar
    open_route(page, "/app/plant", "plant")
    assert theme_of(page) == "dark"
    assert background_of(page) == DARK_BG
    open_route(page, "/app/more", "more")
    group = page.get_by_role("radiogroup", name="Aparência")
    group.get_by_text("Igual ao Windows").click()
    assert theme_of(page) == "light"
    assert page.evaluate("localStorage.getItem('forja.tema')") is None


def test_the_saved_choice_is_painted_before_the_app_mounts(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, "/app/now", "now")
    page.evaluate("localStorage.setItem('forja.tema', 'light')")
    # sem o app (scripts do bundle bloqueados), só o script de tema roda
    page.route("**/app/assets/*.js", lambda route: route.abort())
    page.goto("/app/now", wait_until="load")
    assert theme_of(page) == "light"
    assert background_of(page) == LIGHT_BG


def test_tv_follows_the_theme(windows_light: Page) -> None:
    page = windows_light
    page.goto("/app/tv", wait_until="load")
    expect(page.get_by_test_id("tv-headline")).to_be_visible()
    assert theme_of(page) == "light"
    tv_bg = page.get_by_test_id("tv").evaluate("el => getComputedStyle(el).backgroundColor")
    assert tv_bg == LIGHT_BG


def test_print_is_always_light(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, "/app/now", "now")
    assert theme_of(page) == "dark"
    page.emulate_media(media="print")
    assert background_of(page) == WHITE
