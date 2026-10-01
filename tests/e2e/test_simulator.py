"""Simulador: trocar cenário pela UI muda o dosador; a página só tem cenário e sliders."""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers import (
    COMMAND_WORDS,
    EQ_MAIN,
    MATERIAL_DROP_TIMEOUT_MS,
    SCENARIOS,
    control_texts,
    input_types,
    open_route,
    set_scenario_via_api,
)

pytestmark = pytest.mark.e2e

LEVEL_NORMAL = re.compile(r"^(0\.9\d|1\.[0-2]\d)$")  # ~1,00 da referência (ruído pequeno)
LEVEL_LOW = re.compile(r"^0\.[0-7]\d$")  # abaixo de 0,80


def test_beltload_low_lowers_material_level_then_normal_restores(desktop_1920: Page) -> None:
    page = desktop_1920
    open_route(page, f"/app/eq/{EQ_MAIN}/simulator", "simulator")
    wbf = page.get_by_test_id("wbf-root")
    low = page.get_by_test_id("sim-scenario-BELTLOAD_LOW")
    normal = page.get_by_test_id("sim-scenario-NORMAL_OPERATION")
    try:
        expect(normal).to_have_attribute("data-state", "active")
        expect(wbf).to_have_attribute("data-state", "run")
        expect(wbf).to_have_attribute("data-material-level", LEVEL_NORMAL)

        low.click()
        expect(low).to_have_attribute("data-state", "active")
        expect(low.get_by_role("radio")).to_be_checked()
        expect(normal).to_have_attribute("data-state", "idle")
        expect(page.get_by_test_id("sim-notice")).to_contain_text("Pouco material na correia")
        expect(page.get_by_test_id("sim-explanation")).to_contain_text("45%")
        # a carga começa a cair ~5 s depois e chega a 45% em ~60 s
        expect(wbf).to_have_attribute(
            "data-material-level", LEVEL_LOW, timeout=MATERIAL_DROP_TIMEOUT_MS
        )
        expect(wbf).to_have_attribute("data-state", "run")

        normal.click()
        expect(normal).to_have_attribute("data-state", "active")
        expect(page.get_by_test_id("sim-notice")).to_contain_text("Operação normal")
        expect(wbf).to_have_attribute("data-material-level", LEVEL_NORMAL, timeout=20_000)
    finally:
        # devolve o estado compartilhado mesmo se a asserção falhar
        set_scenario_via_api(page, EQ_MAIN, "NORMAL_OPERATION")


def test_simulator_offers_exactly_the_nine_scenarios(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, f"/app/eq/{EQ_MAIN}/simulator", "simulator")
    radios = page.get_by_test_id("sim-scenarios").get_by_role("radio")
    expect(radios).to_have_count(9)
    for code in SCENARIOS:
        card = page.get_by_test_id(f"sim-scenario-{code}")
        expect(card).to_be_visible()
        expect(card).to_contain_text(code)  # código técnico visível só aqui, junto do título pt
    expect(page.get_by_test_id("sim-scenario-STOP_NORMAL")).to_contain_text("Parada normal")
    # a faixa permanente do shell marca a origem; a página avisa que nada chega ao KCM
    banner = page.get_by_test_id("banner-data-source")
    expect(banner).to_have_attribute("data-source", "SIMULATED")
    expect(banner).to_contain_text("DADOS SIMULADOS")
    expect(page.get_by_test_id("simulator-page")).to_contain_text("Nenhum comando chega ao KCM")


def test_simulator_page_has_only_scenarios_and_sliders(tablet_768: Page) -> None:
    page = tablet_768
    open_route(page, f"/app/eq/{EQ_MAIN}/simulator", "simulator")
    page.get_by_test_id("sim-advanced").locator("summary").click()
    expect(page.get_by_role("slider")).to_have_count(7)

    types = set(input_types(page, "[data-testid='simulator-page']"))
    assert types <= {"radio", "range", "checkbox"}, types

    texts = control_texts(page, "[data-testid='simulator-page']")
    offenders = [t for t in texts if COMMAND_WORDS.search(t)]
    assert not offenders, offenders
    # botões que AGEM (sem aria-expanded): só os dois do painel de sliders. Os demais botões da
    # página apenas abrem explicação (tooltip/disclosure com aria-expanded) e não comandam nada.
    actions = [t for t in texts if t.startswith("<button>")]
    assert sorted(actions) == ["<button> Aplicar", "<button> Limpar"], actions
    for t in texts:
        if t.startswith("<button expands>"):
            assert re.search(r"Entender esta variável|Qualidade do dado", t), t
    # os dois botões agem só no simulador e nascem desabilitados até haver algo a aplicar/limpar
    expect(page.get_by_role("button", name="Aplicar")).to_be_disabled()
    expect(page.get_by_role("button", name="Limpar")).to_be_disabled()
