"""Eventos: lista por equipamento, detalhe e reconhecimento (ack) auditado."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi import Path as PathParam
from pydantic import BaseModel, ConfigDict, Field

from forja.api.deps import ContainerDep, jsonable, require_profile
from forja.api.errors import ApiError
from forja.domain import Event, EventStatus

logger = logging.getLogger("forja.api")

router = APIRouter(prefix="/api/v1", tags=["eventos"])

EventId = Annotated[str, PathParam(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")]

STATUS_PT: dict[EventStatus, str] = {
    EventStatus.OPEN: "Aberto",
    EventStatus.ACKNOWLEDGED: "Reconhecido",
    EventStatus.RESOLVED: "Resolvido",
    EventStatus.EXPIRED: "Expirado",
}

_SAMPLE_FIELDS = ("pre_samples", "during_samples", "post_samples")


class AckBody(BaseModel):
    """Quem reconheceu e por quê. Fica na trilha de auditoria."""

    model_config = ConfigDict(extra="forbid")

    user: str = Field(min_length=1, max_length=64, pattern=r"^[\w .@\-]+$")
    note_pt: str = Field(default="", max_length=2000)


def event_view(event: Event, *, include_samples: bool) -> dict[str, Any]:
    """Evento serializado. Sem `include_samples`, as janelas de amostras viram contagens."""
    data: dict[str, Any] = jsonable(event)
    data["severity_pt"] = event.severity.label_pt
    data["status_pt"] = STATUS_PT[event.status]
    data["quality_pt"] = event.quality.label_pt
    data["is_open"] = event.is_open
    data["duration_s"] = event.duration_s
    context = data.get("context", {})
    for field in _SAMPLE_FIELDS:
        context[f"{field[:-8]}_sample_count"] = len(getattr(event.context, field))
        if not include_samples:
            context.pop(field, None)
    return data


async def require_event(container: Any, event_id: str) -> Event:
    """Evento ou 404."""
    event: Event | None = await container.events_repo.get(event_id)
    if event is None:
        raise ApiError(404, "EVENT_NOT_FOUND", "Evento não encontrado.", {"event_id": event_id})
    return event


@router.get("/equipments/{equipment_id}/events")
async def list_events(
    equipment_id: Annotated[str, PathParam(max_length=64)],
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    open_only: Annotated[bool, Query()] = False,
    since: Annotated[datetime | None, Query()] = None,
    until: Annotated[datetime | None, Query()] = None,
) -> dict[str, Any]:
    """Eventos do equipamento, mais recentes primeiro."""
    profile = require_profile(container, equipment_id)
    events: list[Event] = await container.events_repo.list(
        equipment_id=profile.id, since=since, until=until, open_only=open_only, limit=limit
    )
    ordered = sorted(events, key=lambda e: e.start_utc, reverse=True)[:limit]
    return {
        "equipment_id": profile.id,
        "count": len(ordered),
        "events": [event_view(e, include_samples=False) for e in ordered],
    }


@router.get("/events/{event_id}")
async def get_event(event_id: EventId, container: ContainerDep) -> dict[str, Any]:
    """Evento completo, com janelas de amostras (pré, durante, pós)."""
    event = await require_event(container, event_id)
    return event_view(event, include_samples=True)


@router.post("/events/{event_id}/ack", status_code=200)
async def ack_event(event_id: EventId, body: AckBody, container: ContainerDep) -> dict[str, Any]:
    """Reconhece um evento aberto. Não altera o KCM; grava quem e quando, com auditoria."""
    event = await require_event(container, event_id)
    if event.status != EventStatus.OPEN:
        raise ApiError(
            409,
            "EVENT_NOT_OPEN",
            f"Evento já está em estado '{STATUS_PT[event.status]}'.",
            {"status": event.status.value},
        )
    audit = getattr(container.events_repo, "audit", None)
    # INTEGRACAO: SqliteCoreStore.audit (bloco 2). Sem trilha de auditoria, o ack é recusado.
    if not callable(audit):
        raise ApiError(
            501,
            "AUDIT_UNAVAILABLE",
            "Reconhecimento indisponível: trilha de auditoria não configurada.",
        )
    now = container.clock.now_utc()
    updated = event.model_copy(
        update={"status": EventStatus.ACKNOWLEDGED, "acked_by": body.user, "acked_at_utc": now}
    )
    await container.events_repo.save(updated)
    await audit(
        user=body.user,
        action="EVENT_ACK",
        entity_type="event",
        entity_id=updated.id,
        before={"status": event.status.value, "acked_by": event.acked_by},
        after={
            "status": updated.status.value,
            "acked_by": body.user,
            "acked_at_utc": now.isoformat(),
        },
        reason_pt=body.note_pt,
    )
    logger.info("evento %s reconhecido por %s", updated.id, body.user)
    return event_view(updated, include_samples=False)
