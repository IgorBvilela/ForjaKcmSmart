"""Tela Agora (/app/now): a frase e os números para o gerente; o que verificar para a manutenção.

Usa o Edge compartilhado: a Barrilha nasce em BELTLOAD_LOW (o evento abre cerca de 1 min depois
do boot), o KCM 03 simula falha de comunicação e o Dosador Pó Base opera normal.
"""

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
    overflow_info,
)

pytestmark = pytest.mark.e2e

DIAGNOSIS_TIMEOUT_MS = 30_000


def test_agora_mostra_a_frase_e_o_cartao_com_o_que_verificar(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, "/app/now", "now")
    expect(page).to_have_title("Agora · Forja KCM Intelligence")

    card = page.get_by_test_id(f"now-card-{EQ_BARRILHA}")
    expect(card).to_be_visible(timeout=EVENT_TIMEOUT_MS)
    expect(page.get_by_test_id("now-headline")).to_contain_text("em atenção")
    expect(card.get_by_test_id("now-changed-first")).to_contain_text("Material na correia")
    expect(card.get_by_test_id("now-next-check")).to_be_visible(timeout=DIAGNOSIS_TIMEOUT_MS)
    expect(card.get_by_test_id("now-origin-forja").first).to_contain_text("Evento da Forja")
    expect(card.get_by_role("link", name="Ver diagnóstico")).to_have_attribute(
        "href", re.compile(rf"^/app/eq/{EQ_BARRILHA}/events/[A-Za-z0-9_-]+$")
    )

    expect(page.get_by_test_id(f"now-row-{EQ_KCM03}")).to_contain_text("Sem comunicação")
    expect(page.get_by_test_id(f"now-row-{EQ_MAIN}")).to_contain_text("kg/h")


def test_reconhecer_pede_o_nome_antes_de_registrar(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, "/app/now", "now")
    card = page.get_by_test_id(f"now-card-{EQ_BARRILHA}")
    expect(card).to_be_visible(timeout=EVENT_TIMEOUT_MS)
    card.get_by_test_id("ack-start").click()
    card.get_by_test_id("ack-user").fill("")
    card.get_by_test_id("ack-confirm").click()
    expect(card.get_by_role("alert")).to_contain_text("Informe seu nome")
    card.get_by_role("button", name="Cancelar").click()
    expect(card.get_by_test_id("ack-start")).to_be_visible()


def test_frase_pronta_vai_para_a_area_de_transferencia(desktop_1366: Page) -> None:
    page = desktop_1366
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    open_route(page, "/app/now", "now")
    card = page.get_by_test_id(f"now-card-{EQ_BARRILHA}")
    expect(card).to_be_visible(timeout=EVENT_TIMEOUT_MS)
    card.get_by_test_id("now-copy").click()
    expect(card.get_by_test_id("now-copy")).to_contain_text("Frase copiada")
    copied = page.evaluate("navigator.clipboard.readText()")
    assert copied.startswith("Barrilha"), copied
    assert "Primeira verificação" in copied or "saiu do padrão primeiro" in copied, copied


def test_agora_cabe_no_celular(mobile_375: Page) -> None:
    page = mobile_375
    open_route(page, "/app/now", "now")
    expect(page.get_by_test_id("now-headline")).to_be_visible()
    info = overflow_info(page)
    assert not info["overflow"], info
