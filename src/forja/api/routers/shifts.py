"""Turnos da planta e resumo do turno para imprimir. Somente leitura.

Os horários dos turnos vêm da configuração da planta (`config/forja.yaml`, seção `plant.shifts`),
no fuso da planta (`edge.timezone`); sem turno configurado, a tela pede o período. O resumo usa a
medida de tempo (FORJA_RULE, `forja.reports.time_split`) e lista, por dosador, os eventos da Forja
e os alarmes que o KCM informou no período. O aviso antecipado só é contado, à parte.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query

from forja.api.deps import ContainerDep
from forja.api.errors import ApiError
from forja.api.routers.diagnostics import alarm_key_for
from forja.api.routers.history import _mapped_tags, resolve_window
from forja.api.routers.timesplit import _envelope, equipment_split
from forja.domain import EquipmentProfile, Event
from forja.events.plant_time import resolve_zone
from forja.reports.events_csv import in_period
from forja.reports.period import alarm_episodes
from forja.reports.shifts import current_shift, local_day, shift_window

router = APIRouter(prefix="/api/v1", tags=["turnos"])

EVENTS_LIMIT = 5000
EVENTS_LISTED = 50
"""Eventos por dosador na resposta; `events_total` diz quantos houve."""
ALARM_SAMPLES = 20_000
WARNING_ORIGIN = "EARLY_WARNING"


def _event_row(event: Event) -> dict[str, Any]:
    return {
        "id": event.id,
        "start_utc": event.start_utc.isoformat(),
        "end_utc": event.end_utc.isoformat() if event.end_utc else None,
        "title_pt": event.title_pt,
        "severity": event.severity.value,
        "severity_pt": event.severity.label_pt,
        "status": event.status.value,
        "origin": event.origin,
    }


async def _equipment_summary(
    container: Any, profile: EquipmentProfile, start: datetime, end: datetime
) -> dict[str, Any]:
    split = await equipment_split(container, profile, start, end)
    stored: list[Event] = await container.events_repo.list(
        equipment_id=profile.id, until=end, limit=EVENTS_LIMIT
    )
    events = sorted(in_period(stored, start, end), key=lambda e: e.start_utc)
    forja = [e for e in events if e.origin != WARNING_ORIGIN]

    alarms: list[dict[str, Any]] = []
    if "alarm_code" in _mapped_tags(container, profile):
        samples = await container.historian.samples(
            profile.id, ["alarm_code"], start, end, ALARM_SAMPLES
        )

        def title(code: str) -> tuple[str, str]:
            found = container.store.alarms.lookup(alarm_key_for(profile, code))
            return found.title_pt, found.qualifier_pt

        alarms = alarm_episodes(samples, title)

    return {
        **split,
        "data_source": "SIMULATED" if profile.is_simulated else "EQUIPMENT",
        "events": [_event_row(e) for e in forja[:EVENTS_LISTED]],
        "events_total": len(forja),
        "early_warnings": len(events) - len(forja),
        "kcm_alarms": alarms,
    }


@router.get("/shifts")
async def list_shifts(container: ContainerDep) -> dict[str, Any]:
    """Os turnos da configuração da planta e o turno em andamento (nenhum, sem configuração)."""
    config = container.store.config
    zone = resolve_zone(config.edge.timezone)
    now = container.clock.now_utc()
    shifts = config.plant.shifts
    running = current_shift(shifts, now, zone)
    return {
        "timezone": config.edge.timezone,
        "today": local_day(now, zone).isoformat(),
        "shifts": [
            {
                "index": i,
                "name": s.name,
                "start": s.start,
                "end": s.end,
                "crosses_midnight": s.end < s.start,
            }
            for i, s in enumerate(shifts)
        ],
        "current": {"index": running[0], "date": running[1].isoformat()} if running else None,
    }


@router.get("/shift-summary")
async def shift_summary(
    container: ContainerDep,
    shift: Annotated[int | None, Query(ge=0)] = None,
    day: Annotated[date | None, Query(alias="date")] = None,
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
) -> dict[str, Any]:
    """Resumo de um turno (`shift` e `date`, a data em que ele começa) ou de um período livre
    (`from` e `to`). Turno em andamento vai até agora e volta com `in_progress`."""
    config = container.store.config
    zone = resolve_zone(config.edge.timezone)
    now = container.clock.now_utc()
    shifts = config.plant.shifts
    chosen: dict[str, Any] | None = None
    if shift is not None:
        if day is None:
            raise ApiError(422, "VALIDATION_ERROR", "Informe a data do turno (`date`).")
        if shift >= len(shifts):
            raise ApiError(
                404, "SHIFT_NOT_FOUND", "Turno não encontrado na configuração da planta."
            )
        config_shift = shifts[shift]
        start_utc, end_utc = shift_window(config_shift, day, zone)
        chosen = {
            "index": shift,
            "name": config_shift.name,
            "start": config_shift.start,
            "end": config_shift.end,
        }
    elif start is not None and end is not None:
        start_utc, end_utc = resolve_window(now, start, end)
    else:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "Escolha um turno (`shift` e `date`) ou o período (`from` e `to`).",
        )
    if start_utc >= now:
        raise ApiError(422, "VALIDATION_ERROR", "O período escolhido ainda não começou.")

    until = min(end_utc, now)
    profiles = list(container.store.profiles.values())
    items = [await _equipment_summary(container, p, start_utc, until) for p in profiles]
    sources = {item["data_source"] for item in items}
    return {
        **_envelope(start_utc, until),
        "timezone": config.edge.timezone,
        "generated_at_utc": now.isoformat(),
        "in_progress": end_utc > now,
        "shift": chosen,
        "date": day.isoformat() if chosen and day else None,
        "data_source": (sources.pop() if len(sources) == 1 else "MIXED") if sources else None,
        "equipments": items,
    }


__all__ = ["router"]
