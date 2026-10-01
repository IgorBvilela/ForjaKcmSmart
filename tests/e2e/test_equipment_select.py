"""Seletor de equipamento (<select> nativo): muda a URL, o título e o dashboard."""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers import EQ_BARRILHA, EQ_KCM03, EQ_MAIN, open_route

pytestmark = pytest.mark.e2e

PRODUCT = "Forja KCM Intelligence"


def test_select_changes_url_title_and_dashboard(desktop_1920: Page) -> None:
    page = desktop_1920
    open_route(page, "/app/plant", "plant")
    select = page.get_by_test_id("header-equipment-select")
    expect(select.locator("option")).to_have_count(4)  # Visão da planta + 3 equipamentos
    expect(select).to_have_attribute("data-selected", "")
    # no desktop (≥ 1280 px) o texto da opção carrega o estado: "● Dosador Pó Base · Normal"
    expect(select.locator(f"option[value='{EQ_MAIN}']")).to_contain_text("· Normal")
    expect(select.locator(f"option[value='{EQ_KCM03}']")).to_contain_text("· Sem comunicação")
    expect(select.locator("option", has_text="Barrilha (exemplo)")).to_contain_text("exemplo")

    select.select_option(EQ_BARRILHA)
    expect(page).to_have_url(re.compile(rf"/app/eq/{EQ_BARRILHA}/dashboard$"))
    expect(select).to_have_attribute("data-selected", EQ_BARRILHA)
    expect(select).to_have_value(EQ_BARRILHA)
    expect(page.get_by_role("heading", level=1)).to_have_text("Barrilha (exemplo)")
    expect(page).to_have_title(f"Dashboard · Barrilha (exemplo) · {PRODUCT}")
    expect(page.get_by_test_id("sidebar-link-dashboard")).to_have_attribute("aria-current", "page")

    select.select_option(EQ_MAIN)
    expect(page).to_have_url(re.compile(rf"/app/eq/{EQ_MAIN}/dashboard$"))
    expect(page.get_by_role("heading", level=1)).to_have_text("Dosador Pó Base")
    expect(page).to_have_title(f"Dashboard · Dosador Pó Base · {PRODUCT}")
    expect(page.get_by_test_id("kpi-grid")).to_be_visible()


def test_select_keeps_screen_and_returns_to_plant(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, f"/app/eq/{EQ_MAIN}/events", "events")
    select = page.get_by_test_id("header-equipment-select")
    expect(select).to_have_value(EQ_MAIN)

    select.select_option(EQ_KCM03)
    expect(page).to_have_url(re.compile(rf"/app/eq/{EQ_KCM03}/events$"))
    expect(page.get_by_role("heading", level=1)).to_have_text("Eventos")
    expect(page).to_have_title(f"Eventos · KCM 03 (exemplo) · {PRODUCT}")

    select.select_option("__plant__")
    expect(page).to_have_url(re.compile(r"/app/plant$"))
    expect(page.get_by_test_id("plant-grid")).to_be_visible()
    expect(page).to_have_title(f"Planta · {PRODUCT}")


def test_select_options_on_mobile_keep_name_and_state_word(mobile_375: Page) -> None:
    """Contrato (rodada 3, 2026-10-01, apontamento da Edith): o glifo sozinho não diz nada a
    leitor de tela. Abaixo de 1280 px a opção mantém a PALAVRA do estado ("○ KCM 03 · Sem
    comunicação") e perde só o sufixo "(exemplo)" do nome. O estado nunca é abreviado; o texto
    inteiro cabe no campo a 375 px (medido com a fonte real)."""
    page = mobile_375
    open_route(page, "/app/plant", "plant")
    select = page.get_by_test_id("header-equipment-select")
    expect(select.locator("option")).to_have_count(4)
    kcm03 = select.locator(f"option[value='{EQ_KCM03}']")
    expect(kcm03).to_contain_text("KCM 03 · Sem comunicação")
    expect(select.locator(f"option[value='{EQ_MAIN}']")).to_contain_text("Dosador Pó Base · Normal")
    expect(select.locator(f"option[value='{EQ_BARRILHA}']")).to_contain_text("Barrilha · ")
    expect(kcm03).not_to_contain_text("exemplo")
    glyphs = select.locator("option[value]:not([value='__plant__'])").evaluate_all(
        "els => els.map(e => e.textContent.trim().charAt(0))"
    )
    assert all(g and not g.isalnum() for g in glyphs), glyphs
    # nenhuma opção mais larga que o espaço útil do campo (fonte e padding reais)
    overflow = select.evaluate(
        """(sel) => {
          const cs = getComputedStyle(sel);
          const c = document.createElement('canvas').getContext('2d');
          c.font = `${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
          const inner = sel.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
          const width = (o) => Math.round(c.measureText(o.textContent.trim()).width);
          return [...sel.options]
            .map(o => [o.textContent.trim(), width(o), Math.round(inner)])
            .filter(([, w, inner]) => w > inner);
        }"""
    )
    assert overflow == [], f"opção não cabe no campo: {overflow}"
    expect(select).to_be_visible()


def test_select_touch_target_is_at_least_44px_on_mobile(mobile_375: Page) -> None:
    """Contrato B: toque mínimo 44×44 px. (Falhou com 40 px no build das 10:01; corrigido no
    fonte às 10:22 com `height: var(--touch)`.)"""
    page = mobile_375
    open_route(page, "/app/plant", "plant")
    select = page.get_by_test_id("header-equipment-select")
    expect(select).to_be_visible()
    box = select.bounding_box()
    field = select.locator("xpath=..").bounding_box()  # o campo visível que envolve o select
    assert box is not None
    assert field is not None
    assert max(box["height"], field["height"]) >= 44, {"select": box, "field": field}
