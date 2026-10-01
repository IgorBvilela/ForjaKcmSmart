"""Saúde do Edge: /health (liveness), /system/about e /system/health."""

from __future__ import annotations

import platform
import sqlite3
from collections.abc import Sized
from typing import Any

from fastapi import APIRouter, Request

from forja.api.deps import (
    ContainerDep,
    data_source_for,
    data_source_label_pt,
    jsonable,
    uptime_s,
)
from forja.api.routers.equipments import status_view
from forja.version import DIAGNOSIS_SCHEMA_VERSION, __version__

router = APIRouter(tags=["sistema"])

PRODUCT_NAME = "Forja KCM Intelligence"


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness: o processo responde."""
    return {"status": "ok", "version": __version__}


@router.get("/api/v1/system/about")
async def about(request: Request, container: ContainerDep) -> dict[str, Any]:
    """Quem sou, de onde vêm os dados e o que posso fazer (nada de escrita)."""
    profiles = list(container.store.profiles.values())
    data_source = data_source_for(profiles)
    dev_mode = bool(getattr(request.app.state, "dev_mode", False))
    return {
        "name": PRODUCT_NAME,
        "edge_name": container.store.config.edge.name,
        "version": __version__,
        "diagnosis_schema_version": DIAGNOSIS_SCHEMA_VERSION,
        "read_only": True,
        "data_source": data_source,
        "data_source_pt": data_source_label_pt(data_source),
        "uptime_s": uptime_s(container),
        "started_at_utc": jsonable(getattr(container, "started_at_utc", None)),
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
        "equipment_count": len(profiles),
        "dev_mode": dev_mode,
        "docs_url": request.app.docs_url if dev_mode else None,
        "timezone": container.store.config.edge.timezone,
    }


async def _historian_stats(container: Any) -> dict[str, Any]:
    """stats() quando o historian oferece; senão só a contagem (porta mínima)."""
    stats = getattr(
        container.historian, "stats", None
    )  # INTEGRACAO: SqliteHistorian.stats (bloco 2)
    if callable(stats):
        view: dict[str, Any] = jsonable(await stats())
        return view
    return {"samples": await container.historian.count()}


def _rules_loaded(container: Any) -> int | None:
    rules = getattr(getattr(container, "rule_engine", None), "rules", None)
    return len(rules) if isinstance(rules, Sized) else None


@router.get("/api/v1/system/health")
async def system_health(container: ContainerDep) -> dict[str, Any]:
    """Saúde detalhada: equipamentos, historian, bus e motor de eventos."""
    statuses = container.manager.statuses()
    open_events = await container.events_repo.list(open_only=True, limit=500)
    return {
        "status": "ok",
        "version": __version__,
        "uptime_s": uptime_s(container),
        "now_utc": jsonable(container.clock.now_utc()),
        "equipments": {eq: status_view(st) for eq, st in sorted(statuses.items())},
        "historian": await _historian_stats(container),
        "bus": {"dropped": getattr(container.bus, "dropped", None)},
        "events": {
            "rules_loaded": _rules_loaded(container),
            "open_events": len(open_events),
        },
    }
