"""Atalhos de teclado de 1 a 4: Agora, Planta, Dashboard e Comunicação.

Não agem enquanto se digita num campo e podem ser desligados na página Mais (WCAG 2.2, critério
2.1.4); a escolha fica no navegador.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers import open_route

pytestmark = pytest.mark.e2e


def test_keys_one_to_four_open_the_four_main_screens(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, "/app/now", "now")
    page.keyboard.press("2")
    expect(page).to_have_url(re.compile(r"/app/plant$"))
    page.keyboard.press("3")
    expect(page).to_have_url(re.compile(r"/app/eq/[^/]+/dashboard$"))
    page.keyboard.press("4")
    expect(page).to_have_url(re.compile(r"/app/eq/[^/]+/kcm/communication$"))
    page.keyboard.press("1")
    expect(page).to_have_url(re.compile(r"/app/now$"))
    # o menu anuncia o atalho para o leitor de tela
    expect(page.get_by_test_id("sidebar-link-plant")).to_have_attribute("aria-keyshortcuts", "2")


def test_keys_do_nothing_while_typing_in_a_field(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, "/app/tools/exports", "tools-exports")
    field = page.locator("input, select, textarea").first
    field.focus()
    page.keyboard.press("2")
    expect(page).to_have_url(re.compile(r"/app/tools/exports$"))


def test_shortcuts_can_be_turned_off_on_the_gear_page(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, "/app/more", "more")
    toggle = page.get_by_role("checkbox", name=re.compile("Atalhos de teclado"))
    expect(toggle).to_be_checked()
    page.get_by_text(re.compile("Atalhos de teclado")).click()
    expect(toggle).not_to_be_checked()
    page.keyboard.press("2")
    expect(page).to_have_url(re.compile(r"/app/more$"))
    plant = page.get_by_test_id("sidebar-link-plant")
    expect(plant).not_to_have_attribute("aria-keyshortcuts", "2")
    # a escolha fica guardada no navegador
    page.reload(wait_until="load")
    expect(page.get_by_role("checkbox", name=re.compile("Atalhos de teclado"))).not_to_be_checked()
