"""Medida de tempo por dosador e período: dentro do normal, fora do normal e sem dados.

Classificação FORJA_RULE; definição em `forja.reports.time_split` e em `CONTRATOS_Q.md`. Somente
leitura: lê o historiador e os eventos guardados. A variável de referência para "com dado" é a
vazão (`mass_flow`); sem ela no mapping, a primeira variável contínua legível.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi import Path as PathParam

from forja.api.deps import ContainerDep, require_profile
from forja.api.routers.history import _mapped_tags, resolve_window
from forja.api.routers.situation import GAP_FACTOR
from forja.domain import EquipmentProfile, Event
from forja.events.early_warning import build_grid
from forja.events.kcm_alarm import ALARM_TAGS, USABLE
from forja.reports.events_csv import in_period
from forja.reports.time_split import (
    DEFINITION_PT,
    alarm_intervals,
    event_intervals,
    split_time,
)

router = APIRouter(prefix="/api/v1", tags=["medida"])

EquipmentId = Annotated[str, PathParam(max_length=64)]
REFERENCE_TAG = "mass_flow"
NOT_CONTINUOUS = frozenset({*ALARM_TAGS, "stop_by", "machine_state", "control_mode"})
SPLIT_POINTS = 2000
"""Pontos da variável de referência: resolução da cobertura no período."""
ALARM_SAMPLES = 50_000
EVENTS_LIMIT = 5000


def reference_tag(tags: list[str]) -> str | None:
    """Vazão quando mapeada; senão a primeira variável contínua legível; senão nenhuma."""
    if REFERENCE_TAG in tags:
        return REFERENCE_TAG
    return next((t for t in tags if t not in NOT_CONTINUOUS), None)


async def equipment_split(
    container: Any, profile: EquipmentProfile, start: datetime, end: datetime
) -> dict[str, Any]:
    """A medida de um dosador em [start, end]. A leitura de logo antes do início vale no começo."""
    span = (end - start).total_seconds()
    hold_s = GAP_FACTOR * container.store.config.historian.forced_sample_every_s
    lookback = start - timedelta(seconds=hold_s)
    tags = _mapped_tags(container, profile)
    ref = reference_tag(tags)

    data: list[tuple[float, float]] = []
    if ref is not None:
        series = await container.historian.range(profile.id, ref, lookback, end, SPLIT_POINTS)
        grid = build_grid(series, lookback, end, USABLE, cells=1, max_hold_s=hold_s)
        data = [(seg.start_s - hold_s, seg.end_s - hold_s) for seg in grid.segments]

    out: list[tuple[float, float]] = []
    events: list[Event] = await container.events_repo.list(
        equipment_id=profile.id, until=end, limit=EVENTS_LIMIT
    )
    out += event_intervals(in_period(events, start, end), start, end)
    alarm_tags = [t for t in ALARM_TAGS if t in tags]
    if alarm_tags:
        samples = await container.historian.samples(
            profile.id, alarm_tags, lookback, end, ALARM_SAMPLES
        )
        out += [
            (lo - hold_s, hi - hold_s)
            for lo, hi in alarm_intervals(samples, lookback, end, hold_s=hold_s)
        ]

    split = split_time(span, data=data, out=out)
    return {"id": profile.id, "name": profile.name, "reference_tag": ref, **split.as_dict()}


def _window(
    container: Any, start: datetime | None, end: datetime | None
) -> tuple[datetime, datetime]:
    """Janela pedida, sem passar de agora: o futuro não vira "sem dados"."""
    now = container.clock.now_utc()
    start_utc, end_utc = resolve_window(now, start, end)
    return start_utc, min(end_utc, now) if start_utc < now else end_utc


def _envelope(start: datetime, end: datetime) -> dict[str, Any]:
    return {
        "from_utc": start.isoformat(),
        "to_utc": end.isoformat(),
        "definition_pt": DEFINITION_PT,
        "evidence_level": "FORJA_RULE",
    }


@router.get("/time-split")
async def plant_time_split(
    container: ContainerDep,
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
) -> dict[str, Any]:
    """A medida de todos os dosadores, na ordem da configuração."""
    start_utc, end_utc = _window(container, start, end)
    profiles = list(container.store.profiles.values())
    items = [await equipment_split(container, p, start_utc, end_utc) for p in profiles]
    return {**_envelope(start_utc, end_utc), "equipments": items}


@router.get("/equipments/{equipment_id}/time-split")
async def equipment_time_split(
    equipment_id: EquipmentId,
    container: ContainerDep,
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
) -> dict[str, Any]:
    """A medida de um dosador."""
    profile = require_profile(container, equipment_id)
    start_utc, end_utc = _window(container, start, end)
    return {
        **_envelope(start_utc, end_utc),
        **await equipment_split(container, profile, start_utc, end_utc),
    }
