"""Inteligência (fase F): alertas com as três vozes separadas, aviso antecipado com limites e
evidência, casos anteriores e o bloco "Antes do evento" no detalhe."""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers import (
    EQ_BARRILHA,
    EQ_MAIN,
    control_texts,
    is_command_control,
    open_route,
    overflow_info,
    wait_for_event,
)

pytestmark = pytest.mark.e2e


def test_alertas_separam_kcm_eventos_e_avisos_e_reconhecem(desktop_1366: Page) -> None:
    page = desktop_1366
    wait_for_event(page, EQ_BARRILHA)
    open_route(page, f"/app/eq/{EQ_BARRILHA}/alerts", "alerts")
    kcm = page.get_by_test_id("alerts-kcm")
    expect(kcm).to_contain_text("informado pelo KCM")
    expect(kcm).to_contain_text("feito no próprio controlador")
    expect(page.get_by_test_id("alerts-ew")).to_contain_text("Não é previsão de falha")
    forja = page.get_by_test_id("alerts-forja")
    item = forja.locator("article[data-status='OPEN']").first
    expect(item).to_be_visible()

    item.get_by_test_id("ack-start").click()
    item.get_by_test_id("ack-user").fill("")
    item.get_by_test_id("ack-confirm").click()
    expect(item.get_by_role("alert")).to_contain_text("Informe seu nome")

    item.get_by_test_id("ack-user").fill("Técnico de turno")
    item.get_by_test_id("ack-note").fill("visto no painel")
    item.get_by_test_id("ack-confirm").click()
    expect(forja.get_by_test_id("ack-done").first).to_contain_text(
        "Reconhecido por Técnico de turno"
    )

    offenders = [t for t in control_texts(page) if is_command_control(t)]
    assert not offenders, offenders


def test_aviso_antecipado_mostra_limites_evidencia_e_aviso(desktop_1920: Page) -> None:
    page = desktop_1920
    open_route(page, f"/app/eq/{EQ_BARRILHA}/early-warning", "early-warning")
    expect(page.get_by_test_id("ew-disclaimer")).to_contain_text("Não é previsão de falha")
    expect(page.get_by_test_id("ew-disclaimer")).to_contain_text("não é alarme do KCM")
    rule = page.get_by_test_id("ew-rule-EW-BELTLOAD-001")
    expect(rule).to_be_visible()
    expect(rule).to_contain_text("Limite configurado")
    expect(rule).to_contain_text("Não são limites do KCM")
    expect(rule.get_by_test_id("ew-signal-EW-BELTLOAD-001-drive_command")).to_contain_text(
        re.compile(r"pelo menos 8 pontos")
    )
    expect(page.get_by_test_id("ew-recent")).to_be_visible()


def test_casos_mostram_causa_nao_confirmada_e_biblioteca_filtra(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, f"/app/eq/{EQ_MAIN}/cases", "cases")
    case = page.get_by_test_id("case-CASE-2026-09-GTEX-PHA-PO-BASE-VELOCIDADE")
    expect(case).to_contain_text("Causa não confirmada")
    expect(case).to_contain_text("O que foi observado")
    case.get_by_text("Medições e calibração relatadas").click()
    expect(case).to_contain_text("Não é limite nem valor nominal")

    open_route(page, "/app/knowledge/cases", "knowledge-cases")
    search = page.get_by_test_id("knowledge-cases-search")
    search.fill("encoder")
    expect(page.get_by_test_id("case-CASE-2026-09-GTEX-PHA-PO-BASE-VELOCIDADE")).to_be_visible()
    search.fill("nada parecido com isso")
    expect(page.get_by_test_id("case-CASE-2026-09-GTEX-PHA-PO-BASE-VELOCIDADE")).to_have_count(0)


def test_detalhe_do_evento_conta_o_que_aconteceu_antes(desktop_1366: Page) -> None:
    page = desktop_1366
    event = wait_for_event(page, EQ_BARRILHA)
    page.goto(f"/app/eq/{EQ_BARRILHA}/events/{event['id']}", wait_until="load")
    before = page.get_by_test_id("event-before")
    expect(before).to_be_visible()
    expect(before).to_contain_text("Antes do evento")
    expect(before).to_contain_text(re.compile(r"saiu do padrão primeiro|saíram do padrão primeiro"))
    expect(before).to_contain_text("não causa")


@pytest.mark.parametrize("screen", ["alerts", "early-warning", "cases"])
def test_telas_da_inteligencia_cabem_no_celular(mobile_375: Page, screen: str) -> None:
    page = mobile_375
    open_route(page, f"/app/eq/{EQ_BARRILHA}/{screen}", screen)
    info = overflow_info(page)
    assert not info["overflow"], info
