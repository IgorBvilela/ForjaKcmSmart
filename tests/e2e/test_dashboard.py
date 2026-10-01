"""Dashboard: 6 tiles com qualidade SIMULATED e número; sem comunicação mostra "—" e máquina
DESCONHECIDA; movimento reduzido respeitado."""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers import (
    EQ_KCM03,
    EQ_MAIN,
    PT_NUMBER,
    RAW_NUMBER,
    TILE_TAGS,
    css_ms,
    open_route,
)

pytestmark = pytest.mark.e2e


def test_dashboard_has_six_simulated_tiles_with_numeric_values(desktop_1920: Page) -> None:
    page = desktop_1920
    open_route(page, f"/app/eq/{EQ_MAIN}/dashboard", "dashboard")
    grid = page.get_by_test_id("kpi-grid")
    expect(grid.locator("[data-tag]")).to_have_count(6)

    for tag in TILE_TAGS:
        tile = page.get_by_test_id(f"kpi-{tag}")
        expect(tile).to_be_visible()
        expect(tile).to_have_attribute("data-quality", "SIMULATED")
        value = page.get_by_test_id(f"kpi-{tag}-value")
        expect(value).to_have_attribute("data-value", RAW_NUMBER)
        expect(value).to_have_text(PT_NUMBER)
        quality = page.get_by_test_id(f"kpi-{tag}-quality")
        expect(quality).to_have_attribute("data-quality", "SIMULATED")
        expect(quality).to_contain_text("Simulado")
        # explicação sob demanda (explanation_pt da API), nunca um comando
        explain = page.get_by_test_id(f"kpi-{tag}-explain")
        expect(explain).to_have_accessible_name(re.compile(r"^Entender esta variável"))
        expect(explain).to_have_attribute("aria-expanded", "false")

    explain = page.get_by_test_id("kpi-mass_flow-explain")
    explain.click()
    expect(explain).to_have_attribute("aria-expanded", "true")
    expect(page.locator("[role='note'], .disc-body").first).to_contain_text(re.compile(r"\w{4,}"))

    expect(page.get_by_test_id("system-view-chip")).to_have_attribute("data-state", "NORMAL")
    expect(page.get_by_test_id("system-view-text")).to_contain_text("Nenhum evento aberto")
    wbf = page.get_by_test_id("wbf-root")
    expect(wbf).to_have_attribute("data-state", "run")
    expect(wbf).to_have_attribute("data-encoder", "ok")
    expect(page.locator(f"[data-equipment='{EQ_MAIN}']")).to_have_attribute("data-state", "Normal")


def test_dashboard_comm_failure_shows_dashes_and_unknown_machine(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, f"/app/eq/{EQ_KCM03}/dashboard", "dashboard")
    expect(page.locator(f"[data-equipment='{EQ_KCM03}']")).to_have_attribute(
        "data-state", "Sem comunicação"
    )
    for tag in TILE_TAGS:
        tile = page.get_by_test_id(f"kpi-{tag}")
        expect(tile).to_have_attribute("data-quality", "COMM_ERROR")
        expect(page.get_by_test_id(f"kpi-{tag}-value")).to_have_text("—")
        expect(page.get_by_test_id(f"kpi-{tag}-value")).to_have_attribute("data-value", "")
        expect(tile).to_contain_text("Sem comunicação")

    expect(page.get_by_test_id("system-view-chip")).to_have_attribute(
        "data-state", "SEM COMUNICAÇÃO"
    )
    expect(page.get_by_test_id("system-view-text")).to_contain_text(
        "Estado da máquina: desconhecido"
    )
    wbf = page.get_by_test_id("wbf-root")
    expect(wbf).to_have_attribute("data-state", "unknown")
    expect(wbf).to_contain_text("SEM COMUNICAÇÃO")
    expect(wbf).to_contain_text("DESCONHECIDO")
    # sem comunicação, nenhum badge "exemplo" falta: é perfil de exemplo
    expect(page.get_by_text("exemplo", exact=True).first).to_be_visible()


def test_dashboard_respects_reduced_motion(desktop_1920: Page) -> None:
    page = desktop_1920
    open_route(page, f"/app/eq/{EQ_MAIN}/dashboard", "dashboard")
    assert page.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches") is True
    tokens = page.evaluate(
        """() => {
          const s = getComputedStyle(document.documentElement);
          const get = (n) => s.getPropertyValue(n).trim();
          return { num: get('--dur-num'), draw: get('--dur-draw'), scenario: get('--dur-scenario'),
                   stagger: get('--stagger'), screen: get('--dur-screen') };
        }"""
    )
    # o navegador pode devolver "0s" para "0ms": comparar em milissegundos
    assert {k: css_ms(v) for k, v in tokens.items()} == {
        "num": 0,
        "draw": 0,
        "scenario": 0,
        "stagger": 0,
        "screen": 80,
    }, tokens
    wbf = page.get_by_test_id("wbf-root")
    expect(wbf).to_have_attribute("data-reduced", "true")
    expect(wbf).to_have_attribute("data-state", "run")
    expect(wbf).to_contain_text("Correia em movimento")
