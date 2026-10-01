"""Somente leitura na interface: nenhum controle com texto de comando fora do simulador,
rotas de fase futura com estado vazio honesto, Sobre declara somente leitura."""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import NavRoute
from tests.e2e.helpers import (
    EQ_BARRILHA,
    control_texts,
    is_command_control,
    open_route,
    wait_for_event,
)

pytestmark = pytest.mark.e2e


def test_no_command_controls_outside_simulator(
    desktop_1920: Page, nav_routes: list[NavRoute]
) -> None:
    page = desktop_1920
    offenders: list[str] = []
    scanned = 0
    for route in nav_routes:
        if route.slug == "simulator":
            continue
        open_route(page, route.href, route.slug)
        texts = control_texts(page)
        scanned += len(texts)
        offenders += [f"{route.slug}: {t}" for t in texts if is_command_control(t)]

    # detalhe de evento com diagnóstico (botões: voltar, detalhes técnicos)
    event = wait_for_event(page, EQ_BARRILHA)
    page.goto(f"/app/eq/{EQ_BARRILHA}/events/{event['id']}", wait_until="load")
    expect(page.get_by_test_id("event-detail")).to_be_visible()
    page.get_by_test_id("event-technical").click()
    texts = control_texts(page)
    scanned += len(texts)
    offenders += [f"event-detail: {t}" for t in texts if is_command_control(t)]

    assert scanned > 50, "poucos controles varridos; a varredura não cobriu as telas"
    assert not offenders, "controle com texto de comando fora do simulador:\n" + "\n".join(
        offenders
    )


def test_future_phase_routes_show_honest_empty_state(
    desktop_1366: Page, nav_routes: list[NavRoute]
) -> None:
    page = desktop_1366
    future = [r for r in nav_routes if r.phase]
    assert len(future) >= 15, [r.slug for r in future]
    assert {r.phase for r in future} <= {"E", "F", "G", "L", "M"}
    for route in future:
        open_route(page, route.href, route.slug)
        empty = page.get_by_test_id("empty-state")
        expect(empty).to_be_visible()
        expect(empty).to_have_attribute("data-phase", route.phase)
        expect(empty).to_contain_text(f"Disponível na fase {route.phase}")
        expect(empty).to_contain_text("ainda não está disponível")
        expect(empty).to_contain_text("a Forja só lê")
        # sem botão falso dentro do estado vazio
        expect(empty.locator("button, a[href], input")).to_have_count(0)
        expect(page.get_by_test_id(f"sidebar-link-{route.slug}")).to_have_attribute(
            "aria-current", "page"
        )


def test_unknown_route_shows_not_found_without_fake_screen(tablet_768: Page) -> None:
    page = tablet_768
    page.goto("/app/eq/GTEX_PHA_PO_BASE/nao-existe", wait_until="load")
    empty = page.get_by_test_id("empty-state")
    expect(empty).to_be_visible()
    expect(empty).to_contain_text("Página não encontrada")
    expect(empty.get_by_role("link", name="Ir para a planta")).to_be_visible()
    expect(page.get_by_test_id("page")).to_have_attribute("data-route", "notfound")


def test_about_states_read_only(mobile_375: Page) -> None:
    page = mobile_375
    open_route(page, "/app/system/about", "system-about")
    about = page.get_by_test_id("about")
    expect(about).to_contain_text("Somente leitura")
    expect(about).to_contain_text("O KCM controla a dosagem")
    expect(about).to_contain_text("Somente leitura por construção")
    expect(about).to_contain_text("Nenhuma. Driver só lê.")
    expect(about).to_contain_text("DADOS SIMULADOS")
    expect(about).to_contain_text("Equipamentos")
    expect(about.get_by_text("3", exact=True).first).to_be_visible()
    # licenças locais, sem CDN
    for lic in ("OFL 1.1", "ISC", "MIT"):
        expect(about.get_by_role("link", name=lic).first).to_have_attribute(
            "href", re.compile(r"^/app/licenses/")
        )
    expect(page.get_by_test_id("sidebar-link-system-about")).to_have_count(0)  # drawer fechado
