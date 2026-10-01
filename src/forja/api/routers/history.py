"""Histórico: séries por tag com buraco explícito (GAP = null). Nunca interpola."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi import Path as PathParam

from forja.api.deps import ContainerDep, jsonable, require_profile
from forja.api.errors import ApiError
from forja.domain import is_known_tag

router = APIRouter(prefix="/api/v1/equipments", tags=["historico"])

MAX_TAGS_PER_QUERY = 32
MAX_WINDOW_DAYS = 366
DEFAULT_WINDOW = timedelta(hours=1)


def parse_tags(raw: str) -> list[str]:
    """`a,b,c` -> lista sem repetição; 422 se vazia, grande demais ou com tag desconhecida."""
    tags = list(dict.fromkeys(t.strip() for t in raw.split(",") if t.strip()))
    if not tags:
        raise ApiError(422, "VALIDATION_ERROR", "Informe ao menos uma tag em `tags`.")
    if len(tags) > MAX_TAGS_PER_QUERY:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            f"Máximo de {MAX_TAGS_PER_QUERY} tags por consulta.",
            {"count": len(tags)},
        )
    unknown = [t for t in tags if not is_known_tag(t)]
    if unknown:
        raise ApiError(
            422,
            "UNKNOWN_TAG",
            "Tag semântica desconhecida.",
            {"unknown": unknown[:MAX_TAGS_PER_QUERY]},
        )
    return tags


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def resolve_window(
    now: datetime, start: datetime | None, end: datetime | None
) -> tuple[datetime, datetime]:
    """Janela [from, to]: padrão última hora; 422 se invertida ou acima do limite."""
    end_utc = _as_utc(end) if end is not None else now
    start_utc = _as_utc(start) if start is not None else end_utc - DEFAULT_WINDOW
    if start_utc >= end_utc:
        raise ApiError(422, "VALIDATION_ERROR", "`from` deve ser anterior a `to`.")
    if end_utc - start_utc > timedelta(days=MAX_WINDOW_DAYS):
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            f"Janela acima de {MAX_WINDOW_DAYS} dias. Reduza o intervalo.",
        )
    return start_utc, end_utc


@router.get("/{equipment_id}/history")
async def get_history(
    equipment_id: Annotated[str, PathParam(max_length=64)],
    container: ContainerDep,
    tags: Annotated[
        str, Query(min_length=1, max_length=1024, description="Tags separadas por vírgula")
    ],
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
    max_points: Annotated[int, Query(alias="maxPoints", ge=1, le=50_000)] = 2000,
) -> dict[str, Any]:
    """Séries históricas. Bucket vazio vem como `value: null`; `gap_count` conta os buracos."""
    profile = require_profile(container, equipment_id)
    tag_list = parse_tags(tags)
    start_utc, end_utc = resolve_window(container.clock.now_utc(), start, end)
    budget = min(max_points, container.store.config.historian.max_points_per_query)
    series = [
        jsonable(await container.historian.range(profile.id, tag, start_utc, end_utc, budget))
        for tag in tag_list
    ]
    return {
        "equipment_id": profile.id,
        "from_utc": jsonable(start_utc),
        "to_utc": jsonable(end_utc),
        "max_points": budget,
        "interpolated": False,
        "series": series,
    }
