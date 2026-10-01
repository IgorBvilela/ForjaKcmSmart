"""Contrato: nenhuma rota comanda o KCM.

Nenhum caminho contém verbo de comando (command|write|setpoint|run|stop|reset|tare|span|calib|feed)
e toda rota que não é GET está numa allowlist explícita. Quem adicionar rota mutante precisa
mexer aqui, de propósito.
"""

from __future__ import annotations

import re

import pytest
from starlette.routing import Mount, Route

from tests.integration.api_testkit import build_world

pytestmark = pytest.mark.contract

FORBIDDEN_PATH_TOKENS = re.compile(
    r"(command|write|setpoint|run|stop|reset|tare|span|calib|feed)", re.IGNORECASE
)

MUTATING_ALLOWLIST: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/api/v1/events/{event_id}/ack"),
        ("POST", "/api/v1/communication/test-read"),
        ("POST", "/api/v1/simulator/{equipment_id}/scenario"),
        ("POST", "/api/v1/simulator/{equipment_id}/controls"),
        ("DELETE", "/api/v1/simulator/{equipment_id}/controls"),
    }
)
"""Tudo que muta estado. Nada aqui chega ao equipamento: ack é auditoria, test-read só lê,
simulador só muda o modelo físico simulado."""

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def _walk(routes: list[object]) -> list[tuple[str, frozenset[str]]]:
    """Achata rotas; o FastAPI 0.142 embrulha routers incluídos em `_IncludedRouter`."""
    out: list[tuple[str, frozenset[str]]] = []
    for route in routes:
        inner = getattr(route, "original_router", None)
        if inner is not None:
            out.extend(_walk(list(inner.routes)))
        elif isinstance(route, Route):
            out.append((route.path, frozenset(route.methods or ())))
        elif isinstance(route, Mount):
            out.append((route.path, frozenset()))
            out.extend(_walk(list(getattr(route, "routes", []))))
    return out


def _routes() -> list[tuple[str, frozenset[str]]]:
    app = build_world(dev_mode=True).app
    found = _walk(list(app.routes))
    assert len(found) >= 20, "varredura de rotas incompleta; o wrapper do FastAPI mudou?"
    return found


def _openapi_paths() -> dict[str, dict[str, object]]:
    app = build_world(dev_mode=True).app
    return dict(app.openapi()["paths"])


def test_no_path_contains_command_token() -> None:
    offenders = [path for path, _ in _routes() if FORBIDDEN_PATH_TOKENS.search(path)]
    assert offenders == []


def test_openapi_paths_have_no_command_token() -> None:
    offenders = [p for p in _openapi_paths() if FORBIDDEN_PATH_TOKENS.search(p)]
    assert offenders == []


def test_every_mutating_route_is_allowlisted() -> None:
    mutating = {
        (method, path)
        for path, methods in _routes()
        for method in methods
        if method not in SAFE_METHODS
    }
    assert mutating == set(MUTATING_ALLOWLIST)


def test_allowlist_matches_openapi_operations() -> None:
    operations = {
        (method.upper(), path)
        for path, ops in _openapi_paths().items()
        for method in ops
        if method.upper() not in SAFE_METHODS
    }
    assert operations == set(MUTATING_ALLOWLIST)


def test_openapi_declares_read_only_product() -> None:
    app = build_world(dev_mode=True).app
    schema = app.openapi()
    assert schema["info"]["title"] == "Forja KCM Intelligence"
    assert "Não comanda nada" in schema["info"]["description"]


def test_no_route_accepts_put_or_patch() -> None:
    methods = {m for _, ms in _routes() for m in ms}
    assert "PUT" not in methods
    assert "PATCH" not in methods
