"""SSE: um stream por aba com snapshot inicial, amostras coalescidas, eventos e heartbeat."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request
from sse_starlette import EventSourceResponse

from forja.api.deps import ContainerDep, require_profile

router = APIRouter(prefix="/api/v1", tags=["stream"])


@router.get("/stream")
async def stream(
    request: Request,
    container: ContainerDep,
    eq: Annotated[str | None, Query(max_length=64, description="Filtra por equipamento")] = None,
) -> EventSourceResponse:
    """Eventos: `snapshot`, `sample`, `event`, `status`, `heartbeat`. Suporta Last-Event-ID."""
    if eq is not None:
        require_profile(container, eq)
    hub = request.app.state.stream_hub
    last_event_id = request.headers.get("last-event-id")
    return EventSourceResponse(
        hub.stream(eq, last_event_id),
        ping=0,  # heartbeat é nosso (5 s pelo relógio do container); sem ping da biblioteca
        headers={"X-Accel-Buffering": "no"},
    )
