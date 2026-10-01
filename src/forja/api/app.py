"""Fábrica da aplicação FastAPI.

`create_app(container)` só serve: recebe um Container pronto (bloco 3) e NÃO inicia aquisição.
Cabeçalhos de segurança em toda resposta, envelope único de erro, sem CORS (a UI é servida
pela mesma origem), /docs só em modo desenvolvimento.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI
from starlette.datastructures import Headers, MutableHeaders
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from forja.api.deps import is_dev_mode
from forja.api.errors import error_response, install_error_handlers, internal_error_response

if TYPE_CHECKING:
    from forja.service.container import Container
from forja.api.routers import ALL_ROUTERS
from forja.api.routers.ui import STATIC_DIR
from forja.api.sse import StreamHub
from forja.version import __version__

logger = logging.getLogger("forja.api")

APP_TITLE = "Forja KCM Intelligence"
APP_DESCRIPTION_PT = (
    "Observador somente leitura de controladores Coperion K-Tron KCM. "
    "Historiza, detecta o que mudou e ajuda a manutenção a diagnosticar. Não comanda nada."
)

CSP_DEFAULT = "default-src 'self'; frame-ancestors 'none'"
CSP_DEV_DOCS = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "frame-ancestors 'none'"
)
"""Só para o Swagger UI em modo dev: a página do FastAPI carrega assets externos."""

SECURITY_HEADERS: tuple[tuple[str, str], ...] = (
    ("x-content-type-options", "nosniff"),
    ("x-frame-options", "DENY"),
    ("referrer-policy", "no-referrer"),
)

MAX_BODY_BYTES = 1_048_576
"""Nenhum corpo legítimo (perfil + mapping) passa de 1 MiB."""

DEV_DOCS_PATHS = frozenset({"/docs", "/docs/oauth2-redirect"})


class SecurityHeadersMiddleware:
    """Middleware ASGI puro (funciona com streaming/SSE): cabeçalhos, limite de corpo e 500.

    O 500 é tratado aqui, e não só no handler do FastAPI, porque o `ServerErrorMiddleware` do
    Starlette fica FORA dos middlewares do usuário: uma resposta de erro montada lá sairia sem
    CSP e sem os demais cabeçalhos. Aqui toda resposta, inclusive a de erro interno, leva todos.
    """

    def __init__(self, app: ASGIApp, *, dev_docs_paths: frozenset[str] = frozenset()) -> None:
        self.app = app
        self.dev_docs_paths = dev_docs_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        csp = CSP_DEV_DOCS if scope.get("path") in self.dev_docs_paths else CSP_DEFAULT
        response_started = False

        async def send_with_headers(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                headers = MutableHeaders(scope=message)
                headers["content-security-policy"] = csp
                for name, value in SECURITY_HEADERS:
                    headers[name] = value
            await send(message)

        if self._too_large(scope):
            response = error_response(
                413, "PAYLOAD_TOO_LARGE", "Corpo da requisição acima do limite permitido."
            )
            await response(scope, receive, send_with_headers)
            return
        try:
            await self.app(scope, receive, send_with_headers)
        except Exception:
            if response_started:
                raise
            logger.exception(
                "erro não tratado em %s %s", scope.get("method", "?"), scope.get("path", "?")
            )
            await internal_error_response()(scope, receive, send_with_headers)

    @staticmethod
    def _too_large(scope: Scope) -> bool:
        raw = Headers(scope=scope).get("content-length")
        if raw is None:
            return False
        try:
            return int(raw) > MAX_BODY_BYTES
        except ValueError:
            return True


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Liga só o fan-out do SSE. A aquisição é do runner (bloco 3), nunca da API."""
    hub: StreamHub = app.state.stream_hub
    hub.ensure_started()
    try:
        yield
    finally:
        await hub.stop()


def create_app(container: Container) -> FastAPI:
    """Monta a API em cima de um Container pronto."""
    dev_mode = is_dev_mode(container.store.config.edge.name)
    app = FastAPI(
        title=APP_TITLE,
        version=__version__,
        description=APP_DESCRIPTION_PT,
        docs_url="/docs" if dev_mode else None,
        redoc_url=None,
        openapi_url="/openapi.json" if dev_mode else None,
        lifespan=_lifespan,
    )
    app.state.container = container
    app.state.dev_mode = dev_mode
    app.state.stream_hub = StreamHub(container)
    install_error_handlers(app)
    app.add_middleware(
        SecurityHeadersMiddleware,
        dev_docs_paths=DEV_DOCS_PATHS if dev_mode else frozenset(),
    )
    for router in ALL_ROUTERS:
        app.include_router(router)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    return app


def app_container(app: FastAPI) -> Any:
    """Container guardado na app (útil para testes e para o runner)."""
    return app.state.container
