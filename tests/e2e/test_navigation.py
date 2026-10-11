"""Navegação da interface enxuta: a primeira tela é Agora, o menu tem quatro entradas e a
engrenagem (Mais), e toda tela de hoje fica a até 2 cliques: 1 pelo menu, Mais + atalho pela
engrenagem, aba + sub-aba pelas abas do dosador. O contador do menu repete o número da tela Agora.

Documentos e Manuais (fase P) ficam fora da navegação até existirem (`test_readonly.py`).
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import slug_from_href
from tests.e2e.helpers import EQ_BARRILHA, EQ_MAIN, EVENT_TIMEOUT_MS, open_route, wait_for_event

pytestmark = pytest.mark.e2e

MENU = [
    ("now", "Agora"),
    ("plant", "Planta"),
    ("dashboard", "Dashboard"),
    ("kcm-communication", "Comunicação"),
    ("more", "Mais"),
]

EXPECTED_SCREENS = {
    "now",
    "plant",
    "dashboard",
    "kcm-communication",
    "more",
    "realtime",
    "trends",
    "history",
    "alerts",
    "events",
    "diagnostics",
    "early-warning",
    "cases",
    "kcm-datasheet",
    "kcm-components",
    "kcm-alarms",
    "kcm-commissioning",
    "tools-reports",
    "tools-exports",
    "system-equipments",
    "system-backup",
    "system-logs",
    "system-settings",
    "system-about",
    "simulator",
    "knowledge-cases",
}

MENU_LINKS = "[data-testid^='sidebar-link-'][href]"
GEAR_LINKS = "[data-testid^='more-link-'][href]"
TAB_LINKS = "[data-testid^='eq-tab-'][href], [data-testid^='eq-subtab-'][href]"


def hrefs(page: Page, selector: str) -> list[str]:
    return page.locator(selector).evaluate_all("els => els.map(e => e.getAttribute('href'))")


@pytest.mark.parametrize("path", ["/", "/app", "/app/"])
def test_root_opens_the_now_screen(desktop_1366: Page, path: str) -> None:
    page = desktop_1366
    page.goto(path, wait_until="load")
    expect(page).to_have_url(re.compile(r"/app/now$"))
    expect(page.locator("[data-testid='page'][data-route='now']")).to_be_visible()
    expect(page.get_by_test_id("sidebar-link-now")).to_have_attribute("aria-current", "page")


def test_menu_names_follow_the_approved_order(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, "/app/now", "now")
    for slug, label in MENU:
        expect(page.get_by_test_id(f"sidebar-link-{slug}")).to_have_accessible_name(
            re.compile(rf"^{label}")
        )


def test_every_screen_is_at_most_two_clicks_away(desktop_1366: Page) -> None:
    page = desktop_1366
    reached: set[str] = set()

    open_route(page, "/app/now", "now")
    reached |= {slug_from_href(h) for h in hrefs(page, MENU_LINKS)}

    open_route(page, "/app/more", "more")
    # os atalhos do dosador ganham endereço quando a lista da planta chega
    expect(page.locator("[data-testid='more-link-kcm-datasheet'][href]")).to_be_visible()
    reached |= {slug_from_href(h) for h in hrefs(page, GEAR_LINKS)}

    open_route(page, f"/app/eq/{EQ_MAIN}/dashboard", "dashboard")
    for tab in hrefs(page, "[data-testid^='eq-tab-'][href]"):
        slug = slug_from_href(tab)
        reached.add(slug)
        open_route(page, tab, slug)
        reached |= {slug_from_href(h) for h in hrefs(page, TAB_LINKS)}

    missing = sorted(EXPECTED_SCREENS - reached)
    extra = sorted(reached - EXPECTED_SCREENS)
    assert reached == EXPECTED_SCREENS, f"faltam: {missing}; sobram: {extra}"


def test_gear_and_tab_links_open_their_screens_by_click(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, "/app/now", "now")

    page.get_by_test_id("sidebar-link-more").click()
    expect(page).to_have_url(re.compile(r"/app/more$"))
    page.get_by_test_id("more-link-system-about").click()
    expect(page.get_by_test_id("about")).to_be_visible()
    # telas da engrenagem acendem a entrada Mais
    expect(page.get_by_test_id("sidebar-link-more")).to_have_attribute("aria-current", "page")

    page.get_by_test_id("sidebar-link-dashboard").click()
    expect(page.get_by_test_id("eq-tabs")).to_be_visible()
    page.get_by_test_id("eq-tab-graficos").click()
    page.get_by_test_id("eq-subtab-history").click()
    expect(page).to_have_url(re.compile(r"/app/eq/[^/]+/history(\?.*)?$"))
    expect(page.get_by_test_id("history")).to_be_visible()
    # as abas do dosador continuam sob a entrada Dashboard
    expect(page.get_by_test_id("sidebar-link-dashboard")).to_have_attribute("aria-current", "page")


def test_gear_shows_the_selected_equipment_for_its_screens(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, f"/app/eq/{EQ_BARRILHA}/dashboard", "dashboard")
    page.get_by_test_id("sidebar-link-more").click()
    expect(page.get_by_test_id("more-equipment")).to_contain_text("Barrilha")
    expect(page.get_by_test_id("more-link-kcm-datasheet")).to_have_attribute(
        "href", f"/app/eq/{EQ_BARRILHA}/kcm/datasheet"
    )


def test_menu_counter_matches_the_now_screen(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, "/app/now", "now")
    expect(page.get_by_test_id(f"now-card-{EQ_BARRILHA}")).to_be_visible(timeout=EVENT_TIMEOUT_MS)

    counter = page.get_by_test_id("menu-attention-count")
    attention = page.get_by_test_id("now-count-attention").locator("dd")
    expect(counter).to_be_visible()
    expect(counter).to_have_text(attention.inner_text())
    expect(page.get_by_test_id("sidebar-link-now")).to_have_accessible_name(
        re.compile(r"dosador(es)? em atenção")
    )


def test_menu_counter_does_not_flood_the_edge(desktop_1366: Page) -> None:
    """Com evento aberto o SSE manda uma atualização por segundo. O contador do menu (e a tela
    Agora) consultam a situação no máximo uma vez a cada 5 s, em qualquer tela."""
    page = desktop_1366
    wait_for_event(page, EQ_BARRILHA)
    calls: list[str] = []
    page.on("request", lambda r: calls.append(r.url) if "/api/v1/situation" in r.url else None)
    open_route(page, f"/app/eq/{EQ_MAIN}/dashboard", "dashboard")
    page.wait_for_timeout(10_000)
    # carga inicial + no máximo uma a cada 5 s
    assert len(calls) <= 3, f"{len(calls)} consultas em 10 s"


def test_drawer_lists_the_same_entries_and_keeps_focus_inside(mobile_375: Page) -> None:
    page = mobile_375
    open_route(page, "/app/now", "now")
    page.get_by_test_id("header-menu-toggle").click()
    dialog = page.get_by_role("dialog", name="Menu de navegação")
    expect(dialog).to_be_visible()

    slugs = dialog.locator("[data-testid^='sidebar-link-']").evaluate_all(
        "els => els.map(e => e.dataset.testid.slice('sidebar-link-'.length))"
    )
    assert slugs == [slug for slug, _ in MENU]

    for _ in range(10):
        page.keyboard.press("Tab")
        expect(dialog.locator(":focus")).to_have_count(1)
    for _ in range(4):
        page.keyboard.press("Shift+Tab")
        expect(dialog.locator(":focus")).to_have_count(1)


# Telas com o cabeçalho padrão (regra de texto da especificação, §5): título de até 3 palavras e
# no máximo uma frase de apoio visível ao abrir, com até ~100 caracteres. O resto vai em
# "Saiba mais", fechado. A lista cresce a cada grupo de telas revisto.
LEAN_SCREENS = [
    (f"/app/eq/{EQ_MAIN}/realtime", "realtime"),
    (f"/app/eq/{EQ_MAIN}/trends", "trends"),
    (f"/app/eq/{EQ_MAIN}/history", "history"),
    ("/app/tools/exports", "tools-exports"),
    ("/app/tools/reports", "tools-reports"),
    ("/app/system/equipments", "system-equipments"),
    ("/app/system/backup", "system-backup"),
    ("/app/system/logs", "system-logs"),
    ("/app/system/settings", "system-settings"),
    ("/app/system/about", "system-about"),
]


@pytest.mark.parametrize(("path", "slug"), LEAN_SCREENS)
def test_screen_opens_with_short_title_and_one_support_sentence(
    desktop_1366: Page, path: str, slug: str
) -> None:
    page = desktop_1366
    open_route(page, path, slug)
    head = page.get_by_test_id("page-head")
    expect(head).to_be_visible()
    title = head.get_by_role("heading", level=1).inner_text().strip()
    assert len(title.split()) <= 3, title

    leads = head.get_by_test_id("page-lead")
    assert leads.count() <= 1
    if leads.count():
        lead = leads.inner_text().strip()
        assert len(lead) <= 100, lead
        assert lead.endswith("."), lead
        assert ". " not in lead, f"mais de uma frase: {lead}"
    # no cabeçalho, ao abrir: só o rótulo, o título e a frase de apoio
    assert head.locator("p:visible").count() <= 2
    more = head.get_by_test_id("page-more")
    if more.count():
        expect(more).to_have_attribute("aria-expanded", "false")


def test_long_explanation_waits_in_learn_more(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, f"/app/eq/{EQ_MAIN}/trends", "trends")
    head = page.get_by_test_id("page-head")
    expect(head).not_to_contain_text("Arraste sobre um gráfico")
    head.get_by_test_id("page-more").click()
    expect(head).to_contain_text("Arraste sobre um gráfico para ampliar um trecho.")
