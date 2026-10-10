"""Relatórios, exportações, backup e configuração (fase M) no navegador."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers import EQ_BARRILHA, open_route, overflow_info

pytestmark = pytest.mark.e2e


def test_backup_agora_conferir_e_comando_de_restauracao(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, "/app/system/backup", "system-backup")
    expect(page.get_by_test_id("backup-schedule")).to_contain_text("todo dia às")
    page.get_by_test_id("backup-responsible").fill("Técnico de teste")
    page.get_by_test_id("backup-create-submit").click()
    item = page.locator("[data-testid^='backup-backup_']").first
    expect(item).to_contain_text("com configuração")
    item.locator("[data-testid^='backup-verify-']").click()
    expect(item.get_by_test_id("backup-verify-result")).to_contain_text("Backup íntegro")
    item.get_by_text("Como restaurar este backup").click()
    expect(item).to_contain_text("--sim")
    expect(item).to_contain_text("Pare o serviço")


def test_relatorio_do_periodo(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, "/app/tools/reports", "tools-reports")
    page.get_by_test_id("reports-equipment").select_option(EQ_BARRILHA)
    page.get_by_test_id("reports-generate").click()
    doc = page.get_by_test_id("report-doc")
    expect(doc).to_contain_text("Resumo")
    expect(doc).to_contain_text("Qualidade do dado no período")
    expect(page.get_by_test_id("report-summary")).to_contain_text("Dados simulados")
    expect(page.get_by_role("button", name="Imprimir ou salvar em PDF")).to_be_visible()


def test_exportacoes_baixam_csv_com_qualidade(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, "/app/tools/exports", "tools-exports")
    page.get_by_test_id("exports-equipment").select_option(EQ_BARRILHA)
    link = page.get_by_test_id("exports-events-link")
    href = link.get_attribute("href")
    assert href
    assert "events.csv" in href
    resp = page.request.get(href)
    assert resp.ok
    header = resp.text().lstrip("﻿").splitlines()[0]
    assert header.startswith("inicio_utc;inicio_planta;fim_utc")
    agg = page.get_by_test_id("exports-agg-link").get_attribute("href")
    assert agg
    assert "resolution=auto" in agg
    resp = page.request.get(agg)
    assert resp.ok
    assert "pior_qualidade" in resp.text().splitlines()[0]


def test_configuracao_mostra_o_que_esta_em_uso(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, "/app/system/settings", "system-settings")
    expect(page.get_by_test_id("settings-edge")).to_contain_text("127.0.0.1")
    expect(page.get_by_test_id("settings-users")).to_contain_text("Não há login nesta versão")
    expect(page.get_by_test_id("settings-note")).to_contain_text("Esta tela só mostra")


@pytest.mark.parametrize(
    "path",
    ["/app/system/backup", "/app/tools/reports", "/app/tools/exports", "/app/system/settings"],
)
def test_ferramentas_cabem_no_celular(mobile_375: Page, path: str) -> None:
    page = mobile_375
    page.goto(path, wait_until="load")
    expect(page.get_by_test_id("page")).to_be_visible()
    page.wait_for_timeout(800)
    info = overflow_info(page)
    assert not info["overflow"], info
