"""Shell: sidebar/drawer nos 4 viewports, sem scroll horizontal, selo e faixa sempre visíveis."""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import VIEWPORT_NAMES, NavRoute
from tests.e2e.helpers import open_route, overflow_info

pytestmark = pytest.mark.e2e


def test_sidebar_open_by_default_and_collapses_at_1920(desktop_1920: Page) -> None:
    page = desktop_1920
    open_route(page, "/app/plant", "plant")
    sidebar = page.get_by_test_id("sidebar")
    expect(sidebar).to_have_attribute("data-mode", "rail")
    expect(sidebar).to_have_attribute("data-state", "open")
    toggle = page.get_by_test_id("header-menu-toggle")
    expect(toggle).to_have_attribute("aria-expanded", "true")
    expect(toggle).to_have_attribute("aria-controls", "sidebar")
    # no desktop não há botão dentro da sidebar: recolher/expandir é só pelo header
    expect(page.get_by_test_id("sidebar-toggle")).to_have_count(0)

    toggle.click()
    expect(sidebar).to_have_attribute("data-state", "collapsed")
    expect(toggle).to_have_attribute("aria-expanded", "false")
    expect(toggle).to_have_accessible_name("Expandir menu")

    toggle.click()
    expect(sidebar).to_have_attribute("data-state", "open")
    expect(toggle).to_have_attribute("aria-expanded", "true")
    expect(toggle).to_have_accessible_name("Recolher menu")


def test_sidebar_collapsed_by_default_at_1366(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, "/app/plant", "plant")
    sidebar = page.get_by_test_id("sidebar")
    expect(sidebar).to_have_attribute("data-mode", "rail")
    expect(sidebar).to_have_attribute("data-state", "collapsed")
    # recolhida, os rótulos somem mas cada link continua com nome acessível
    link = page.get_by_test_id("sidebar-link-plant")
    expect(link).to_be_visible()
    expect(link).to_have_accessible_name(re.compile(r"Planta"))
    expect(link).to_have_attribute("aria-current", "page")

    page.get_by_test_id("header-menu-toggle").click()
    expect(sidebar).to_have_attribute("data-state", "open")
    expect(page.get_by_test_id("sidebar-link-plant")).to_have_attribute("aria-current", "page")


@pytest.mark.parametrize("viewport", ["tablet_768", "mobile_375"])
def test_drawer_opens_closes_with_escape_and_restores_focus(
    request: pytest.FixtureRequest, viewport: str
) -> None:
    page: Page = request.getfixturevalue(viewport)
    open_route(page, "/app/plant", "plant")
    # abaixo de 1024 px a sidebar só existe dentro do drawer
    expect(page.get_by_test_id("sidebar")).to_have_count(0)
    toggle = page.get_by_test_id("header-menu-toggle")
    expect(toggle).to_have_attribute("aria-expanded", "false")

    toggle.click()
    dialog = page.get_by_role("dialog", name="Menu de navegação")
    expect(dialog).to_be_visible()
    expect(page.get_by_test_id("drawer-scrim")).to_be_visible()
    expect(page.get_by_test_id("sidebar")).to_have_attribute("data-mode", "drawer")
    expect(toggle).to_have_attribute("aria-expanded", "true")
    # o foco entra no painel (primeiro link ou botão)
    expect(dialog.locator(":focus")).to_have_count(1)

    page.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    expect(page.get_by_test_id("drawer-scrim")).to_have_count(0)
    expect(toggle).to_be_focused()
    expect(toggle).to_have_attribute("aria-expanded", "false")


def test_drawer_closes_on_scrim_and_on_navigation(mobile_375: Page) -> None:
    page = mobile_375
    open_route(page, "/app/plant", "plant")
    page.get_by_test_id("header-menu-toggle").click()
    expect(page.get_by_role("dialog")).to_be_visible()
    page.get_by_test_id("drawer-scrim").click(position={"x": 370, "y": 400})
    expect(page.get_by_role("dialog")).to_have_count(0)

    # botão "Fechar menu" dentro do drawer (único lugar onde sidebar-toggle existe)
    page.get_by_test_id("header-menu-toggle").click()
    close = page.get_by_test_id("sidebar-toggle")
    expect(close).to_have_accessible_name("Fechar menu")
    close.click()
    expect(page.get_by_role("dialog")).to_have_count(0)

    page.get_by_test_id("header-menu-toggle").click()
    page.get_by_test_id("sidebar-link-system-about").click()
    expect(page).to_have_url(re.compile(r"/app/system/about$"))
    expect(page.get_by_role("dialog")).to_have_count(0)
    expect(page.get_by_test_id("about")).to_be_visible()


@pytest.mark.parametrize("viewport", VIEWPORT_NAMES)
def test_no_horizontal_overflow_on_every_route(
    request: pytest.FixtureRequest, viewport: str, nav_routes: list[NavRoute]
) -> None:
    page: Page = request.getfixturevalue(viewport)
    problems: list[str] = []
    for route in nav_routes:
        open_route(page, route.href, route.slug)
        info = overflow_info(page)
        if info["overflow"]:
            problems.append(
                f"{route.slug}: scrollWidth={info['scrollWidth']} > "
                f"clientWidth={info['clientWidth']} (innerWidth={info['innerWidth']}); "
                f"largos: {info['wide']}"
            )
    assert not problems, f"scroll horizontal em {viewport}:\n" + "\n".join(problems)


def test_no_horizontal_overflow_with_drawer_open(mobile_375: Page) -> None:
    page = mobile_375
    open_route(page, "/app/eq/GTEX_PHA_PO_BASE/dashboard", "dashboard")
    page.get_by_test_id("header-menu-toggle").click()
    expect(page.get_by_role("dialog")).to_be_visible()
    info = overflow_info(page)
    assert not info["overflow"], info


@pytest.mark.parametrize("viewport", VIEWPORT_NAMES)
def test_readonly_badge_and_simulated_banner_always_visible(
    request: pytest.FixtureRequest, viewport: str
) -> None:
    page: Page = request.getfixturevalue(viewport)
    open_route(page, "/app/plant", "plant")

    badge = page.get_by_test_id("header-readonly-badge")
    expect(badge).to_have_count(1)
    expect(badge).to_be_visible()
    expect(badge).to_have_attribute("data-state", "read-only")
    expect(badge).to_contain_text("Somente leitura")

    banner = page.get_by_test_id("banner-data-source")
    expect(banner).to_be_visible()
    expect(banner).to_have_attribute("data-source", "SIMULATED")
    expect(banner).to_contain_text("DADOS SIMULADOS")

    if viewport == "mobile_375":
        # abaixo de 768 px o selo migra para a faixa de fonte de dados e nunca some
        expect(banner.get_by_test_id("header-readonly-badge")).to_be_visible()
    else:
        expect(
            page.get_by_test_id("header").get_by_test_id("header-readonly-badge")
        ).to_be_visible()


def test_readonly_badge_explains_itself_on_click(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, "/app/plant", "plant")
    button = page.get_by_test_id("header-readonly-badge").get_by_role("button")
    expect(button).to_have_attribute("aria-expanded", "false")
    button.click()
    expect(button).to_have_attribute("aria-expanded", "true")
    expect(page.get_by_role("note")).to_contain_text("Nenhuma rota, comando ou botão")
    page.keyboard.press("Escape")
    expect(page.get_by_role("note")).to_have_count(0)
