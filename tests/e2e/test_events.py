"""Eventos: BELTLOAD_LOW abre um evento com badge Diagnóstico; o detalhe tem as 7 seções na
ordem do contrato; a impressão esconde a sidebar."""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers import (
    DIAGNOSIS_SECTIONS,
    EQ_BARRILHA,
    EVENT_TIMEOUT_MS,
    open_route,
    wait_for_event,
)

pytestmark = pytest.mark.e2e

BELTLOAD_TITLE_PT = "Pouco material sobre a correia"  # config/rules/R-BELTLOAD-001.yaml


def test_beltload_low_event_has_diagnosis_badge_and_seven_sections(desktop_1920: Page) -> None:
    page = desktop_1920
    # A Barrilha roda BELTLOAD_LOW desde o boot: a regra abre o evento ~1 min depois.
    open_route(page, f"/app/eq/{EQ_BARRILHA}/events", "events")
    row = (
        page.locator("[data-testid^='event-row-'][data-severity='ATTENTION']")
        .filter(has_text=BELTLOAD_TITLE_PT)
        .first
    )
    expect(row).to_be_visible(timeout=EVENT_TIMEOUT_MS)
    expect(row).to_have_attribute("data-status", "OPEN")
    expect(row.get_by_text("Diagnóstico", exact=True)).to_be_visible(timeout=30_000)
    expect(row.get_by_text("Simulado", exact=True)).to_be_visible()
    expect(page.get_by_test_id("events-list")).to_have_attribute(
        "data-count", re.compile(r"^[1-9]")
    )

    row.click()
    expect(page).to_have_url(re.compile(rf"/app/eq/{EQ_BARRILHA}/events/[A-Za-z0-9_-]+$"))
    detail = page.get_by_test_id("event-detail")
    expect(detail).to_be_visible()
    expect(detail.get_by_role("heading", level=1)).to_have_text(BELTLOAD_TITLE_PT)

    panel = page.get_by_test_id("diagnosis-panel")
    expect(panel).to_be_visible()
    expect(panel).to_have_attribute("data-schema", "1.0")
    for code in DIAGNOSIS_SECTIONS:
        expect(page.get_by_test_id(f"diagnosis-section-{code}")).to_be_visible()
    order = panel.locator("[data-testid^='diagnosis-section-']").evaluate_all(
        "els => els.map(e => e.dataset.testid)"
    )
    assert order == [f"diagnosis-section-{c}" for c in DIAGNOSIS_SECTIONS], order

    # hipótese é "comportamento compatível com", nunca causa
    hypotheses = page.get_by_test_id("diagnosis-section-HIPOTESES")
    expect(hypotheses).to_contain_text(re.compile(r"compatível", re.IGNORECASE))
    # código interno só em "Detalhes técnicos" (fechado por padrão)
    tech = page.get_by_test_id("event-technical")
    expect(tech).to_have_attribute("aria-expanded", "false")
    expect(detail.get_by_text("BELT_LOAD_LOW", exact=True)).to_have_count(0)
    tech.click()
    expect(detail.get_by_text("BELT_LOAD_LOW", exact=True).first).to_be_visible()


def test_diagnostics_screen_lists_only_events_with_diagnosis(desktop_1366: Page) -> None:
    page = desktop_1366
    wait_for_event(page, EQ_BARRILHA, title_pt=BELTLOAD_TITLE_PT)
    open_route(page, f"/app/eq/{EQ_BARRILHA}/diagnostics", "diagnostics")
    expect(page.get_by_role("heading", level=1)).to_have_text("Diagnósticos")
    rows = page.locator("[data-testid^='event-row-']")
    expect(rows.first).to_be_visible()
    for i in range(rows.count()):
        expect(rows.nth(i).get_by_text("Diagnóstico", exact=True)).to_be_visible(timeout=30_000)


def test_print_hides_shell_and_keeps_event_detail(desktop_1920: Page) -> None:
    page = desktop_1920
    event = wait_for_event(page, EQ_BARRILHA, title_pt=BELTLOAD_TITLE_PT)
    page.goto(f"/app/eq/{EQ_BARRILHA}/events/{event['id']}", wait_until="load")
    detail = page.get_by_test_id("event-detail")
    expect(detail).to_be_visible()
    expect(page.get_by_test_id("diagnosis-panel")).to_be_visible()
    expect(page.get_by_test_id("sidebar")).to_be_visible()

    page.emulate_media(media="print")
    expect(page.get_by_test_id("sidebar")).to_be_hidden()
    expect(page.get_by_test_id("header")).to_be_hidden()
    expect(page.get_by_test_id("banner-data-source")).to_be_hidden()
    expect(detail).to_be_visible()
    expect(page.get_by_test_id("diagnosis-panel")).to_be_visible()

    page.emulate_media(media="screen")
    expect(page.get_by_test_id("sidebar")).to_be_visible()
