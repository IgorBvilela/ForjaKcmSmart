"""Fase E: Tempo Real, Tendências e Histórico com dados do historiador real.

- Tendências: gráfico por variável (uPlot), faixa de qualidade, "o que mudou nesta janela" com a
  variável que mudou primeiro, seleção de variáveis na URL, zoom por arraste e volta ao período.
- Tempo Real: todas as tags mapeadas com qualidade; equipamento sem comunicação mostra travessão.
- Histórico: tabela de pontos, eventos do período e CSV com instante, valor, unidade e qualidade.
Nenhuma tela some em scroll lateral no celular.
"""

from __future__ import annotations

import csv
import io
import re
import time

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import Edge
from tests.e2e.helpers import (
    EQ_BARRILHA,
    EQ_KCM03,
    EQ_MAIN,
    EVENT_TIMEOUT_MS,
    open_route,
    overflow_info,
)

pytestmark = pytest.mark.e2e

LIVE_WINDOW_LIMIT_S = 12 * 60
"""Até aqui depois do boot, a janela ao vivo de 15 min ainda contém o começo do cenário."""


def test_trends_show_charts_and_what_changed_first(desktop_1920: Page, edge: Edge) -> None:
    page = desktop_1920
    # A Barrilha roda BELTLOAD_LOW desde o boot: material cai e o esforço sobe. A análise compara
    # com o começo da janela, então a janela precisa conter o boot: nos primeiros minutos, os
    # 15 min ao vivo; depois (a bateria inteira leva mais de 20 min), 15 min fixos a partir do boot.
    if time.time() - edge.started_at < LIVE_WINDOW_LIMIT_S:
        period = "p=15m"
    else:
        start_ms = int((edge.started_at - 60) * 1000)
        period = f"from={start_ms}&to={start_ms + 15 * 60_000}"
    open_route(page, f"/app/eq/{EQ_BARRILHA}/trends?{period}", "trends")
    chart = page.get_by_test_id("trend-chart-belt_load")
    expect(chart).to_be_visible()
    expect(chart.locator("canvas").first).to_be_visible()
    expect(chart).to_have_attribute("data-points", re.compile(r"^[1-9]\d*$"))
    card = page.get_by_test_id("trends-what-changed")
    expect(card).to_be_visible()
    # a página se atualiza a cada 15 s; a mudança aparece quando a janela já tem o padrão
    first = card.locator("[data-testid^='trends-change-'][data-first='true']")
    expect(first).to_have_count(1, timeout=EVENT_TIMEOUT_MS)
    expect(card).to_contain_text("não é causa")
    expect(card).to_contain_text("Dados simulados")
    expect(page.get_by_test_id("trends-stats")).to_be_visible()
    expect(page.get_by_text("Qualidade (faixa na base)")).to_be_visible()


def test_trends_tag_selection_lives_in_the_url(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, f"/app/eq/{EQ_MAIN}/trends?p=15m", "trends")
    expect(page.get_by_test_id("trend-chart-mass_flow")).to_be_visible()
    page.get_by_test_id("trends-tag-net_weight").click()
    expect(page.get_by_test_id("trend-chart-net_weight")).to_be_visible()
    expect(page).to_have_url(re.compile(r"tags=[^&]*net_weight"))
    page.get_by_test_id("trends-tag-net_weight").click()
    expect(page.get_by_test_id("trend-chart-net_weight")).to_have_count(0)


def test_trends_drag_zooms_and_reset_returns_to_period(desktop_1920: Page) -> None:
    page = desktop_1920
    # janela fixa: um período ao vivo redesenha o gráfico a cada 15 s e pode cortar o gesto
    now_ms = int(time.time() * 1000)
    open_route(page, f"/app/eq/{EQ_MAIN}/trends?from={now_ms - 600_000}&to={now_ms}", "trends")
    over = page.get_by_test_id("trend-chart-mass_flow").locator(".u-over")
    expect(over).to_be_visible()
    box = over.bounding_box()
    assert box is not None
    y = box["y"] + box["height"] / 2
    page.mouse.move(box["x"] + box["width"] * 0.55, y)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] * 0.95, y, steps=8)
    page.mouse.up()
    reset = page.get_by_test_id("trends-zoom-reset")
    expect(reset).to_be_visible()
    expect(page.get_by_test_id("trends-window")).to_contain_text("Zoom")
    reset.click()
    expect(reset).to_have_count(0)
    expect(page.get_by_test_id("trends-window")).to_contain_text("Intervalo escolhido")


def test_realtime_lists_every_tag_with_quality(tablet_768: Page) -> None:
    page = tablet_768
    open_route(page, f"/app/eq/{EQ_MAIN}/realtime", "realtime")
    row = page.get_by_test_id("realtime-row-mass_flow")
    expect(row).to_be_visible()
    expect(row).to_have_attribute("data-quality", "SIMULATED")
    expect(row).to_contain_text("Simulado")
    expect(page.get_by_test_id("realtime-group-brutos")).to_contain_text("0x")
    assert not overflow_info(page)["overflow"]


def test_realtime_without_communication_never_shows_old_value_as_current(
    desktop_1366: Page,
) -> None:
    page = desktop_1366
    open_route(page, f"/app/eq/{EQ_KCM03}/realtime", "realtime")
    row = page.get_by_test_id("realtime-row-mass_flow")
    expect(row).to_be_visible()
    expect(row).to_have_attribute("data-quality", re.compile(r"^(COMM_ERROR|STALE)$"))
    expect(page.get_by_test_id("realtime-status")).to_contain_text("Erro de comunicação")


def test_history_exports_csv_with_value_unit_and_quality(desktop_1920: Page) -> None:
    page = desktop_1920
    open_route(page, f"/app/eq/{EQ_MAIN}/history?p=15m", "history")
    expect(page.get_by_test_id("history-table")).to_be_visible()
    expect(page.get_by_test_id("history-events")).to_be_visible()
    link = page.get_by_test_id("history-export-raw")
    href = link.get_attribute("href")
    assert href
    assert href.startswith("/api/v1/equipments/")
    resp = page.request.get(href)
    assert resp.ok, resp.status
    assert resp.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(resp.text().lstrip("﻿")), delimiter=";"))
    assert rows, "CSV vazio: o historiador não gravou nada em 15 min?"
    assert {"data_hora_utc", "valor", "unidade", "qualidade"} <= set(rows[0])
    assert {r["qualidade"] for r in rows} <= {"SIMULATED", "COMM_ERROR"}


def test_trends_and_history_fit_the_phone(mobile_375: Page) -> None:
    page = mobile_375
    for slug in ("trends", "history"):
        open_route(page, f"/app/eq/{EQ_MAIN}/{slug}?p=15m", slug)
        toggle = page.get_by_test_id(f"{slug}-tag-toggle")
        expect(toggle).to_be_visible()
        expect(toggle).to_have_attribute("aria-expanded", "false")
        info = overflow_info(page)
        assert not info["overflow"], f"{slug}: rolagem lateral {info}"
