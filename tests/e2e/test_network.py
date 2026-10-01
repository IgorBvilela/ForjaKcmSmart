"""Nada sai da máquina: toda requisição da interface fica em 127.0.0.1 e o SSE conecta local."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers import EQ_BARRILHA, EQ_MAIN, open_route

pytestmark = pytest.mark.e2e


def test_every_request_stays_on_localhost(desktop_1920: Page) -> None:
    page = desktop_1920
    seen: list[str] = []
    page.on("request", lambda req: seen.append(req.url))

    open_route(page, "/app/plant", "plant")
    open_route(page, f"/app/eq/{EQ_MAIN}/dashboard", "dashboard")
    open_route(page, f"/app/eq/{EQ_BARRILHA}/events", "events")
    open_route(page, f"/app/eq/{EQ_MAIN}/simulator", "simulator")
    open_route(page, "/app/system/about", "system-about")
    expect(page.get_by_test_id("header-online")).to_have_attribute("data-state", "online")

    http_urls = [u for u in seen if urlsplit(u).scheme in ("http", "https")]
    assert len(http_urls) > 20, "poucas requisições observadas"
    hosts = {urlsplit(u).hostname for u in http_urls}
    assert hosts == {"127.0.0.1"}, hosts
    assert all(urlsplit(u).scheme == "http" for u in http_urls)
    assert any("/api/v1/stream" in u for u in seen), "SSE não conectou em /api/v1/stream"
    assert any("/app/assets/" in u for u in http_urls), "assets do build não foram pedidos"
    assert any("/app/fonts/" in u or ".woff2" in u for u in http_urls), (
        "fontes locais não carregadas"
    )


def test_edge_online_dot_and_clock_are_present(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, "/app/plant", "plant")
    online = page.get_by_test_id("header-online")
    expect(online).to_have_attribute("data-state", "online")
    expect(online).to_contain_text("ONLINE")
    clock = page.get_by_test_id("header-clock")
    expect(clock).to_be_visible()
    expect(clock).to_have_attribute("datetime", re.compile(r"^\d{4}-\d{2}-\d{2}T.*Z$"))
