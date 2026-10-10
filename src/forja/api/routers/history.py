"""Histórico: séries por tag com buraco explícito (GAP = null), exportação CSV e análise de
janela ("o que mudou, quando começou, quem mudou primeiro"). Nunca interpola."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query
from fastapi import Path as PathParam
from fastapi.responses import StreamingResponse

from forja.api.deps import ContainerDep, data_source_for, jsonable, require_profile
from forja.api.errors import ApiError
from forja.domain import (
    EquipmentProfile,
    Sample,
    Series,
    TagKind,
    get_tag,
    is_known_tag,
)
from forja.events.window_analysis import analyze_window
from forja.reports.csv_export import CsvDialect, aggregated_csv, export_filename, raw_csv

router = APIRouter(prefix="/api/v1/equipments", tags=["historico"])

MAX_TAGS_PER_QUERY = 32
MAX_WINDOW_DAYS = 366
DEFAULT_WINDOW = timedelta(hours=1)
MAX_EXPORT_ROWS = 250_000
"""Exportação ponto a ponto acima disto pede período menor ou exportação resumida."""
ANALYSIS_POINTS = 2000
"""Orçamento de pontos por variável na análise de janela (contínuas). Limitado pelo
`historian.max_points_per_query`; até ~33 min a análise usa os pontos gravados."""
DISCRETE_ANALYSIS_ROWS = 20_000


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


def _mapped_tags(container: Any, profile: EquipmentProfile) -> list[str]:
    """Tags legíveis do mapping em vigor (padrão quando a consulta não informa `tags`)."""
    mapping = container.store.mapping_for(profile.id)
    return [e.semantic_tag for e in mapping.readable_entries]


def _require_method(container: Any, name: str) -> Any:
    fn = getattr(container.historian, name, None)
    if not callable(fn):
        raise ApiError(503, "HISTORIAN_UNAVAILABLE", "Historiador sem suporte a esta consulta.")
    return fn


@router.get("/{equipment_id}/history.csv")
async def export_history_csv(
    equipment_id: Annotated[str, PathParam(max_length=64)],
    container: ContainerDep,
    tags: Annotated[str | None, Query(max_length=1024)] = None,
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
    dialect: CsvDialect = CsvDialect.BR,
    resolution: Literal["raw", "auto"] = "raw",
) -> StreamingResponse:
    """CSV com instante, valor, unidade e qualidade. `raw` = pontos gravados; `auto` = resumo
    por intervalo (média, mínimo, máximo, leituras, pior qualidade)."""
    profile = require_profile(container, equipment_id)
    tag_list = parse_tags(tags) if tags else _mapped_tags(container, profile)
    if not tag_list:
        raise ApiError(422, "VALIDATION_ERROR", "Nenhuma variável mapeada para exportar.")
    start_utc, end_utc = resolve_window(container.clock.now_utc(), start, end)
    timezone = container.store.config.edge.timezone
    if resolution == "raw":
        export_rows = _require_method(container, "export_rows")
        rows = await export_rows(profile.id, tag_list, start_utc, end_utc, MAX_EXPORT_ROWS + 1)
        if len(rows) > MAX_EXPORT_ROWS:
            raise ApiError(
                422,
                "EXPORT_TOO_LARGE",
                "Período grande demais para exportar ponto a ponto. Reduza o período ou "
                "exporte o resumo por intervalo.",
                {"max_rows": MAX_EXPORT_ROWS},
            )
        body = raw_csv(rows, equipment_id=profile.id, timezone=timezone, dialect=dialect)
    else:
        budget = container.store.config.historian.max_points_per_query
        series: list[Series] = [
            await container.historian.range(profile.id, tag, start_utc, end_utc, budget)
            for tag in tag_list
        ]
        body = aggregated_csv(series, equipment_id=profile.id, timezone=timezone, dialect=dialect)
    filename = export_filename(profile.id, start_utc, end_utc, resolution)
    return StreamingResponse(
        body,
        media_type="text/csv; charset=utf-8",
        headers={
            "content-disposition": f'attachment; filename="{filename}"',
            "cache-control": "no-store",
        },
    )


def _series_samples(series: Series) -> list[Sample]:
    """Pontos da série como amostras para a análise. Buraco (n=0) vira leitura sem valor."""
    return [
        Sample(
            ts_utc=p.ts_utc,
            equipment_id=series.equipment_id,
            tag=series.tag,
            value=p.value,
            quality=p.quality,
            source=f"historian:{series.resolution}",
        )
        for p in series.points
    ]


@router.get("/{equipment_id}/what-changed")
async def what_changed(
    equipment_id: Annotated[str, PathParam(max_length=64)],
    container: ContainerDep,
    tags: Annotated[str | None, Query(max_length=1024)] = None,
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
    together_s: Annotated[float, Query(alias="togetherS", ge=1, le=3600)] = 30.0,
) -> dict[str, Any]:
    """O que mudou na janela, quando começou cada mudança e qual variável mudou primeiro.

    O padrão é o comportamento do início da janela. A resposta descreve ordem e simultaneidade;
    nunca afirma causa.
    """
    profile = require_profile(container, equipment_id)
    tag_list = parse_tags(tags) if tags else _mapped_tags(container, profile)
    start_utc, end_utc = resolve_window(container.clock.now_utc(), start, end)
    samples_by_tag: dict[str, list[Sample]] = {}
    extremes: dict[str, tuple[float | None, float | None]] = {}
    resolution_s = 1
    for tag in tag_list:
        if get_tag(tag).kind is TagKind.CONTINUOUS:
            series = await container.historian.range(
                profile.id, tag, start_utc, end_utc, ANALYSIS_POINTS
            )
            samples_by_tag[tag] = _series_samples(series)
            mins = [p.min for p in series.points if p.min is not None]
            maxs = [p.max for p in series.points if p.max is not None]
            extremes[tag] = (min(mins) if mins else None, max(maxs) if maxs else None)
            resolution_s = max(resolution_s, series.bucket_s or 1)
        else:
            samples_fn = _require_method(container, "samples")
            samples_by_tag[tag] = await samples_fn(
                profile.id, [tag], start_utc, end_utc, DISCRETE_ANALYSIS_ROWS
            )
    analysis = analyze_window(
        samples_by_tag,
        tag_list,
        timezone=container.store.config.edge.timezone,
        resolution_s=resolution_s,
        together_s=together_s,
        extremes=extremes,
    )
    view: dict[str, Any] = jsonable(analysis)
    view.update(
        {
            "equipment_id": profile.id,
            "from_utc": jsonable(start_utc),
            "to_utc": jsonable(end_utc),
            "data_source": data_source_for([profile]),
            "interpolated": False,
        }
    )
    return view
