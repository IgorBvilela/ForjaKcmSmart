"""Relatório por período e exportação de eventos em CSV. Só leitura."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi import Path as PathParam
from fastapi.responses import StreamingResponse

from forja.api.deps import ContainerDep, require_profile
from forja.api.routers.diagnostics import alarm_key_for
from forja.api.routers.history import _mapped_tags, resolve_window
from forja.domain import EquipmentProfile, Event, Series
from forja.reports.csv_export import CsvDialect, export_filename
from forja.reports.events_csv import events_csv, in_period
from forja.reports.period import build_period_report

router = APIRouter(prefix="/api/v1/equipments", tags=["relatorios"])

EquipmentId = Annotated[str, PathParam(max_length=64)]
REPORT_POINTS = 600
"""Pontos por variável no relatório: o suficiente para cobertura e média no tempo."""
REPORT_EVENTS = 5000
ALARM_SAMPLES = 20_000


async def _events(
    container: Any, profile: EquipmentProfile, start: datetime, end: datetime
) -> list[Event]:
    events: list[Event] = await container.events_repo.list(
        equipment_id=profile.id, until=end, limit=REPORT_EVENTS
    )
    return in_period(events, start, end)


@router.get("/{equipment_id}/report")
async def period_report(
    equipment_id: EquipmentId,
    container: ContainerDep,
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
) -> dict[str, Any]:
    """Relatório do período: qualidade do dado no tempo, eventos, avisos e alarmes do KCM."""
    profile = require_profile(container, equipment_id)
    start_utc, end_utc = resolve_window(container.clock.now_utc(), start, end)
    tags = _mapped_tags(container, profile)
    continuous = [t for t in tags if t not in ("alarm_code", "alarm_active", "stop_by")]
    series: dict[str, Series] = {
        tag: await container.historian.range(profile.id, tag, start_utc, end_utc, REPORT_POINTS)
        for tag in continuous
    }
    alarm_samples = []
    if "alarm_code" in tags:
        alarm_samples = await container.historian.samples(
            profile.id, ["alarm_code"], start_utc, end_utc, ALARM_SAMPLES
        )

    def alarm_title(code: str) -> tuple[str, str]:
        lookup = container.store.alarms.lookup(alarm_key_for(profile, code))
        return lookup.title_pt, lookup.qualifier_pt

    report = build_period_report(
        profile,
        start_utc,
        end_utc,
        series,
        await _events(container, profile, start_utc, end_utc),
        alarm_samples,
        alarm_title,
        generated_at=container.clock.now_utc(),
    )
    report["timezone"] = container.store.config.edge.timezone
    return report


@router.get("/{equipment_id}/events.csv")
async def export_events_csv(
    equipment_id: EquipmentId,
    container: ContainerDep,
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
    dialect: CsvDialect = CsvDialect.BR,
) -> StreamingResponse:
    """Eventos e avisos do período, uma linha por evento, com origem e qualidade."""
    profile = require_profile(container, equipment_id)
    start_utc, end_utc = resolve_window(container.clock.now_utc(), start, end)
    body = events_csv(
        await _events(container, profile, start_utc, end_utc),
        equipment_id=profile.id,
        timezone=container.store.config.edge.timezone,
        dialect=dialect,
    )
    filename = export_filename(profile.id, start_utc, end_utc, "eventos")
    return StreamingResponse(
        body,
        media_type="text/csv; charset=utf-8",
        headers={
            "content-disposition": f'attachment; filename="{filename}"',
            "cache-control": "no-store",
        },
    )


__all__ = ["router"]
