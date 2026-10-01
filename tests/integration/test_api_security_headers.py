"""Cabeçalhos de segurança em toda resposta, sem CORS, /docs só em dev, página estática honesta."""

from __future__ import annotations

import re

import httpx
import pytest

from forja.api.app import MAX_BODY_BYTES
from tests.integration.api_testkit import (
    ApiWorld,
    build_world,
    shutdown_world,
)

pytestmark = pytest.mark.integration

EXPECTED_HEADERS = {
    "content-security-policy": "default-src 'self'; frame-ancestors 'none'",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
}


def _assert_headers(resp: httpx.Response) -> None:
    for name, value in EXPECTED_HEADERS.items():
        assert resp.headers.get(name) == value, name


@pytest.mark.parametrize(
    "path", ["/health", "/api/v1/system/about", "/api/v1/plant", "/api/v1/equipments", "/"]
)
async def test_headers_on_success(client: httpx.AsyncClient, path: str) -> None:
    resp = await client.get(path)
    assert resp.status_code == 200
    _assert_headers(resp)


async def test_headers_on_404_envelope(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/equipments/NAO_EXISTE")
    assert resp.status_code == 404
    _assert_headers(resp)
    assert resp.json()["error"]["code"] == "EQUIPMENT_NOT_FOUND"


async def test_headers_on_422_envelope(client: httpx.AsyncClient) -> None:
    resp = await client.post("/api/v1/communication/test-read", json={"profile": {}})
    assert resp.status_code == 422
    _assert_headers(resp)
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_headers_on_500_without_traceback(client: httpx.AsyncClient, world: ApiWorld) -> None:
    async def boom() -> dict[str, str]:
        raise RuntimeError("segredo interno: não pode vazar")

    world.app.add_api_route("/_teste/erro", boom, methods=["GET"])
    resp = await client.get("/_teste/erro")
    assert resp.status_code == 500
    _assert_headers(resp)
    body = resp.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["details"] is None
    assert "segredo interno" not in resp.text
    assert "Traceback" not in resp.text


async def test_no_cors_headers_even_with_origin(client: httpx.AsyncClient) -> None:
    resp = await client.get("/api/v1/plant", headers={"Origin": "http://malicioso.exemplo"})
    assert resp.status_code == 200
    assert "access-control-allow-origin" not in resp.headers
    preflight = await client.options(
        "/api/v1/events/x/ack",
        headers={"Origin": "http://malicioso.exemplo", "Access-Control-Request-Method": "POST"},
    )
    assert preflight.status_code == 405
    assert "access-control-allow-origin" not in preflight.headers
    _assert_headers(preflight)


async def test_oversized_body_is_refused_before_parsing(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/communication/test-read",
        content=b"{}",
        headers={"content-length": str(MAX_BODY_BYTES + 1), "content-type": "application/json"},
    )
    assert resp.status_code == 413
    _assert_headers(resp)
    assert resp.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


async def test_docs_hidden_outside_dev_mode(client: httpx.AsyncClient) -> None:
    for path in ("/docs", "/openapi.json", "/redoc"):
        resp = await client.get(path)
        assert resp.status_code == 404, path
        _assert_headers(resp)


async def test_docs_available_only_in_dev_mode() -> None:
    w = build_world(dev_mode=True)
    try:
        transport = httpx.ASGITransport(app=w.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            about = (await c.get("/api/v1/system/about")).json()
            assert about["dev_mode"] is True
            assert about["docs_url"] == "/docs"
            docs = await c.get("/docs")
            assert docs.status_code == 200
            csp = docs.headers["content-security-policy"]
            assert "frame-ancestors 'none'" in csp
            assert docs.headers["x-frame-options"] == "DENY"
            spec = await c.get("/openapi.json")
            assert spec.status_code == 200
            _assert_headers(spec)
            redoc = await c.get("/redoc")
            assert redoc.status_code == 404
    finally:
        await shutdown_world(w)


async def test_index_page_is_honest_and_offline(client: httpx.AsyncClient) -> None:
    resp = await client.get("/")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    html = resp.text
    assert "Somente leitura" in html
    assert "<button" not in html.lower()
    assert "onclick" not in html.lower()
    assert "<style" not in html.lower()  # CSP default-src 'self' não permite inline
    inline_scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", html, flags=re.IGNORECASE)
    assert inline_scripts == []
    remote = re.findall(r"""(?:src|href)=["'](https?:)?//""", html, flags=re.IGNORECASE)
    assert remote == []
    for asset in re.findall(r"""(?:src|href)=["'](/static/[^"']+)""", html):
        a = await client.get(asset)
        assert a.status_code == 200, asset
        _assert_headers(a)
        # xmlns do SVG é identificador de namespace, não busca na rede
        text = re.sub(r"""xmlns(:\w+)?=["']http://www\.w3\.org/[^"']*["']""", "", a.text)
        assert "https://" not in text, asset
        assert "http://" not in text, asset


async def test_static_assets_do_not_reach_the_network(client: httpx.AsyncClient) -> None:
    js = (await client.get("/static/app.js")).text
    assert "fetch(API" in js
    assert re.search(r"\.innerHTML\s*=", js) is None  # só textContent
    assert re.search(r"\beval\s*\(", js) is None
    assert "document.write" not in js
    css = (await client.get("/static/app.css")).text
    assert "@import" not in css
    assert "url(http" not in css
