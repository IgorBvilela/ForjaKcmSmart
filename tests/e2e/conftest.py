"""Fixtures do bloco E2E (contrato B, seção final): Playwright em Python contra o Edge real.

- `edge`: sobe `forja run --port <livre>` com FORJA_DATA_DIR em pasta temporária e FORJA_HOME na
  raiz do repositório, espera `/health` e derruba no fim (terminate + wait; kill se preciso).
- `browser`: Edge local (`channel="msedge"`, sem download) headless; se não houver, o Chromium do
  Playwright já instalado. Sem navegador nenhum, os testes são pulados com motivo.
- Páginas por viewport: `desktop_1920`, `desktop_1366`, `tablet_768`, `mobile_375`.
  Toda página nasce com movimento reduzido (`emulate_media(reduced_motion="reduce")`), locale
  pt-BR, fuso da máquina e um interceptor que FALHA o teste se qualquer requisição sair de
  127.0.0.1/localhost.
- Sem build em `src/forja/ui/dist`, tudo em tests/e2e é pulado com motivo claro.

Nada aqui usa rede fora de 127.0.0.1. Nada sai da máquina.
"""

from __future__ import annotations

import http.client
import os
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
UI_INDEX = REPO_ROOT / "src" / "forja" / "ui" / "dist" / "index.html"
E2E_DIR = Path(__file__).resolve().parent
SCREENSHOT_DIR = REPO_ROOT / "reports" / "e2e"

HEALTH_TIMEOUT_S = 60.0
STOP_TIMEOUT_S = 15.0
DEFAULT_TIMEOUT_MS = 15_000

LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
LOCAL_SCHEMES = frozenset({"data", "blob", "about", "chrome", "chrome-extension", "devtools"})

VIEWPORTS: dict[str, dict[str, Any]] = {
    "desktop_1920": {"viewport": {"width": 1920, "height": 1080}},
    "desktop_1366": {"viewport": {"width": 1366, "height": 768}},
    "tablet_768": {
        "viewport": {"width": 768, "height": 1024},
        "is_mobile": True,
        "has_touch": True,
        "device_scale_factor": 2,
    },
    "mobile_375": {
        "viewport": {"width": 375, "height": 812},
        "is_mobile": True,
        "has_touch": True,
        "device_scale_factor": 2,
    },
}
VIEWPORT_NAMES = tuple(VIEWPORTS)

try:
    from playwright.sync_api import (
        Browser,
        BrowserContext,
        Page,
        Playwright,
        Request,
        Route,
        expect,
        sync_playwright,
    )
    from playwright.sync_api import (
        Error as PlaywrightError,
    )

    PLAYWRIGHT_IMPORT_ERROR: str | None = None
except ImportError as exc:  # pragma: no cover - ambiente sem Playwright
    PLAYWRIGHT_IMPORT_ERROR = str(exc)


def ui_build_available() -> bool:
    return UI_INDEX.is_file()


def _skip_reason() -> str | None:
    if PLAYWRIGHT_IMPORT_ERROR:
        return f"E2E pulado: playwright não instalado no .venv ({PLAYWRIGHT_IMPORT_ERROR})."
    if not ui_build_available():
        return (
            "E2E pulado: interface não compilada. Rode `npm run build` em frontend/ "
            f"(esperado: {UI_INDEX})."
        )
    return None


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Marca tudo em tests/e2e com `e2e` e pula o bloco inteiro quando não dá para rodar."""
    reason = _skip_reason()
    skip = pytest.mark.skip(reason=reason) if reason else None
    for item in items:
        if E2E_DIR not in item.path.resolve().parents:
            continue
        item.add_marker(pytest.mark.e2e)
        if skip is not None:
            item.add_marker(skip)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[None]) -> Iterator[None]:
    """Guarda o resultado de cada fase em `item.rep_<fase>` para a captura de tela em falha."""
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


# ----------------------------------------------------------------------------------------------
# Edge real
# ----------------------------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _health_ok(port: int) -> bool:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=1.0)
    try:
        conn.request("GET", "/health")
        resp = conn.getresponse()
        body = resp.read()
        return resp.status == 200 and b'"ok"' in body
    except OSError:
        return False
    finally:
        conn.close()


@dataclass(frozen=True)
class Edge:
    port: int
    data_dir: Path
    log_path: Path

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def log_tail(self, lines: int = 40) -> str:
        try:
            text = self.log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return "(sem log)"
        return "\n".join(text.splitlines()[-lines:])


@pytest.fixture(scope="package")
def edge(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Edge]:
    """`forja run` numa porta livre, dados em pasta temporária, derrubado no fim da sessão."""
    data_dir = tmp_path_factory.mktemp("forja_e2e_data")
    log_path = data_dir / "edge.log"
    port = _free_port()
    env = dict(os.environ)
    env.update(
        {
            "FORJA_DATA_DIR": str(data_dir),
            "FORJA_HOME": str(REPO_ROOT),
            "PYTHONUTF8": "1",
            "PYTHONPATH": str(REPO_ROOT / "src")
            + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""),
        }
    )
    cmd = [
        sys.executable,
        "-c",
        "import sys; from forja.tools.cli import main; sys.exit(main())",
        "run",
        "--port",
        str(port),
        "--home",
        str(REPO_ROOT),
    ]
    with log_path.open("wb") as log:
        proc = subprocess.Popen(  # noqa: S603  # comando fixo, sem shell, só 127.0.0.1
            cmd, cwd=str(REPO_ROOT), env=env, stdout=log, stderr=subprocess.STDOUT
        )
    edge = Edge(port=port, data_dir=data_dir, log_path=log_path)
    deadline = time.monotonic() + HEALTH_TIMEOUT_S
    try:
        while True:
            if proc.poll() is not None:
                pytest.fail(
                    f"forja run terminou cedo (código {proc.returncode}).\n{edge.log_tail()}"
                )
            if _health_ok(port):
                break
            if time.monotonic() > deadline:
                pytest.fail(
                    f"/health não respondeu em {HEALTH_TIMEOUT_S:.0f} s.\n{edge.log_tail()}"
                )
            time.sleep(0.2)
        yield edge
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=STOP_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=STOP_TIMEOUT_S)


# ----------------------------------------------------------------------------------------------
# Navegador
# ----------------------------------------------------------------------------------------------


@pytest.fixture(scope="package")
def pw() -> Iterator[Playwright]:
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="package")
def browser(pw: Playwright) -> Iterator[Browser]:
    """Edge local (sem download). Fallback: Chromium do Playwright. Sem nenhum, pula."""
    errors: list[str] = []
    launched: Browser | None = None
    for kwargs in ({"channel": "msedge"}, {}):
        try:
            launched = pw.chromium.launch(headless=True, **kwargs)
            break
        except PlaywrightError as exc:
            errors.append(f"{kwargs or 'chromium'}: {str(exc).splitlines()[0]}")
    if launched is None:
        pytest.skip("E2E pulado: nenhum navegador disponível. " + " | ".join(errors))
    expect.set_options(timeout=DEFAULT_TIMEOUT_MS)
    yield launched
    launched.close()


def is_local_url(url: str) -> bool:
    parts = urlsplit(url)
    if parts.scheme in LOCAL_SCHEMES:
        return True
    return parts.hostname in LOCAL_HOSTS


def _context_kwargs(name: str, base_url: str) -> dict[str, Any]:
    return {
        **VIEWPORTS[name],
        "base_url": base_url,
        "locale": "pt-BR",
        "timezone_id": "America/Sao_Paulo",
        "color_scheme": "dark",
        "reduced_motion": "reduce",
    }


PageFactory = Callable[[str], "Page"]


@pytest.fixture
def make_page(
    browser: Browser, edge: Edge, request: pytest.FixtureRequest
) -> Iterator[PageFactory]:
    """Fábrica de páginas por viewport. Teardown: captura de tela em falha, fecha contextos e
    FALHA o teste se alguma requisição tentou sair de 127.0.0.1/localhost ou se houve erro de JS."""
    contexts: list[BrowserContext] = []
    violations: list[str] = []
    page_errors: list[str] = []

    def guard(route: Route, req: Request) -> None:
        if is_local_url(req.url):
            route.continue_()
            return
        violations.append(f"{req.method} {req.url}")
        route.abort("blockedbyclient")

    def _make(name: str) -> Page:
        ctx = browser.new_context(**_context_kwargs(name, edge.base_url))
        ctx.set_default_timeout(DEFAULT_TIMEOUT_MS)
        ctx.set_default_navigation_timeout(DEFAULT_TIMEOUT_MS * 2)
        page = ctx.new_page()
        page.emulate_media(reduced_motion="reduce")
        page.route("**/*", guard)
        page.on("pageerror", lambda err: page_errors.append(str(err)))
        contexts.append(ctx)
        return page

    yield _make

    rep = getattr(request.node, "rep_call", None)
    if rep is not None and rep.failed:
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        for i, ctx in enumerate(contexts):
            for j, page in enumerate(ctx.pages):
                try:
                    page.screenshot(
                        path=str(SCREENSHOT_DIR / f"{request.node.name}-{i}{j}.png"),
                        full_page=True,
                    )
                except PlaywrightError:
                    pass
    for ctx in contexts:
        ctx.close()
    assert not violations, "Requisição fora de 127.0.0.1/localhost: " + "; ".join(violations)
    assert not page_errors, "Erro de JavaScript não tratado na página: " + " | ".join(page_errors)


@pytest.fixture
def desktop_1920(make_page: PageFactory) -> Page:
    return make_page("desktop_1920")


@pytest.fixture
def desktop_1366(make_page: PageFactory) -> Page:
    return make_page("desktop_1366")


@pytest.fixture
def tablet_768(make_page: PageFactory) -> Page:
    return make_page("tablet_768")


@pytest.fixture
def mobile_375(make_page: PageFactory) -> Page:
    return make_page("mobile_375")


@dataclass(frozen=True)
class NavRoute:
    slug: str
    href: str
    phase: str  # '' quando a tela já funciona nesta fase


@pytest.fixture(scope="package")
def nav_routes(browser: Browser, edge: Edge) -> list[NavRoute]:
    """Rotas da sidebar lidas do próprio app (frontend/src/lib/nav.ts) com equipamento escolhido."""
    ctx = browser.new_context(**_context_kwargs("desktop_1920", edge.base_url))
    try:
        page = ctx.new_page()
        page.goto("/app/eq/GTEX_PHA_PO_BASE/dashboard", wait_until="load")
        links = page.locator("[data-testid^='sidebar-link-']")
        expect(links.first).to_be_visible()
        raw = links.evaluate_all(
            "els => els.map(e => ({slug: e.dataset.testid.slice('sidebar-link-'.length),"
            " href: e.getAttribute('href'), phase: e.dataset.phase || ''}))"
        )
    finally:
        ctx.close()
    routes = [NavRoute(r["slug"], r["href"], r["phase"]) for r in raw]
    assert routes, "sidebar sem links: nav.ts vazio ou equipamento não selecionado"
    return routes
