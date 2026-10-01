"""Planta: 3 cards com Normal / Atenção / Sem comunicação, badge "exemplo" e clique → dashboard."""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers import (
    EQ_BARRILHA,
    EQ_KCM03,
    EQ_MAIN,
    EVENT_TIMEOUT_MS,
    open_route,
)

pytestmark = pytest.mark.e2e


def test_plant_shows_three_cards_with_the_three_states(desktop_1920: Page) -> None:
    page = desktop_1920
    open_route(page, "/app/plant", "plant")
    grid = page.get_by_test_id("plant-grid")
    expect(grid.locator("[data-testid^='plant-card-']")).to_have_count(3)

    expect(page.get_by_test_id(f"plant-card-{EQ_MAIN}")).to_have_attribute("data-state", "Normal")
    expect(page.get_by_test_id(f"plant-card-{EQ_KCM03}")).to_have_attribute(
        "data-state", "Sem comunicação"
    )
    # A Barrilha nasce em BELTLOAD_LOW: a regra abre o evento ~1 min depois do boot do Edge.
    expect(page.get_by_test_id(f"plant-card-{EQ_BARRILHA}")).to_have_attribute(
        "data-state", "Atenção", timeout=EVENT_TIMEOUT_MS
    )

    summary = page.get_by_test_id("plant-summary")
    expect(summary).to_contain_text("3 equipamentos")
    expect(summary).to_contain_text("1 atenção")
    expect(summary).to_contain_text("1 sem comunicação")
    expect(page.get_by_test_id("plant-title")).to_have_text("GTEX — PHA")


def test_plant_example_badge_only_on_example_profiles(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, "/app/plant", "plant")
    # Marcação visível de perfil de exemplo (contrato: badge "exemplo"; build atual: texto
    # "· perfil de exemplo" na linha da aplicação). O teste exige a marcação, não a forma.
    for eq in (EQ_BARRILHA, EQ_KCM03):
        card = page.get_by_test_id(f"plant-card-{eq}")
        expect(card.get_by_text(re.compile(r"\bexemplo\b"), exact=False).first).to_be_visible()
        expect(card.locator("[data-tone='sim']", has_text="Simulado")).to_be_visible()
    main = page.get_by_test_id(f"plant-card-{EQ_MAIN}")
    expect(main).not_to_contain_text(re.compile(r"exemplo", re.IGNORECASE))
    expect(main.locator("[data-tone='sim']", has_text="Simulado")).to_be_visible()
    expect(main).to_have_attribute("data-quality", "SIMULATED")
    expect(main).to_have_attribute("data-conn", "CONNECTED")


def test_plant_comm_failure_card_shows_dash_and_reason(tablet_768: Page) -> None:
    page = tablet_768
    open_route(page, "/app/plant", "plant")
    card = page.get_by_test_id(f"plant-card-{EQ_KCM03}")
    expect(card).to_have_attribute("data-state", "Sem comunicação")
    expect(card).to_have_attribute("data-quality", "COMM_ERROR")
    expect(card).to_have_attribute("data-conn", re.compile(r"^(ERROR|RECONNECTING)$"))
    # antes de 15 s: frase derivada; depois a regra R-COMM-001 abre "Comunicação degradada"
    expect(card).to_contain_text(re.compile(r"Sem leitura do KCM|Comunicação degradada"))
    expect(card).to_contain_text("Sem comunicação")
    expect(card.locator(".num.big")).to_have_text("—")


def test_plant_card_click_opens_dashboard(mobile_375: Page) -> None:
    page = mobile_375
    open_route(page, "/app/plant", "plant")
    card = page.get_by_test_id(f"plant-card-{EQ_MAIN}")
    expect(card).to_have_attribute("aria-label", re.compile(r"Dosador Pó Base: .*Abrir dashboard"))
    card.click()
    expect(page).to_have_url(re.compile(rf"/app/eq/{EQ_MAIN}/dashboard$"))
    expect(page.get_by_role("heading", level=1)).to_have_text("Dosador Pó Base")
    expect(page.get_by_test_id("header-equipment-select")).to_have_attribute(
        "data-selected", EQ_MAIN
    )
