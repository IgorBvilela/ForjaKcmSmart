"""Planta: um card por equipamento com estado em português e vazão atual.

`state_pt` segue a prioridade: conexão (Sem comunicação) > eventos abertos (Crítico, Atenção,
Parado) > dados utilizáveis (Normal) > resto (Desconhecido). Parada não é falha.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from forja.api.deps import ContainerDep, data_source_for, data_source_label_pt, jsonable
from forja.api.routers.equipments import (
    _snapshot_ages,
    _snapshot_samples,
    equipment_summary,
    tag_view,
)
from forja.domain import (
    ConnectionState,
    EquipmentProfile,
    EquipmentRuntimeStatus,
    Event,
    Quality,
    Sample,
    Severity,
)

router = APIRouter(prefix="/api/v1", tags=["planta"])

STOP_EVENT_TYPE = "MACHINE_STOPPED"
"""Código interno da regra Forja R-STOP-001 (contrato). Não é valor do KCM."""

MASS_FLOW_TAG = "mass_flow"

STATE_NORMAL_PT = "Normal"
STATE_ATTENTION_PT = "Atenção"
STATE_CRITICAL_PT = "Crítico"
STATE_NO_COMM_PT = "Sem comunicação"
STATE_STOPPED_PT = "Parado"
STATE_UNKNOWN_PT = "Desconhecido"

_NO_COMM_STATES = frozenset(
    {
        ConnectionState.DISCONNECTED,
        ConnectionState.CONNECTING,
        ConnectionState.HANDSHAKE,
        ConnectionState.ERROR,
        ConnectionState.RECONNECTING,
    }
)


def classify_state(
    status: EquipmentRuntimeStatus,
    samples: dict[str, Sample],
    open_events: list[Event],
) -> str:
    """Estado do card em português."""
    if status.connection == ConnectionState.NOT_CONFIGURED:
        return STATE_UNKNOWN_PT
    if status.connection in _NO_COMM_STATES:
        return STATE_NO_COMM_PT
    severities = {e.severity for e in open_events}
    if Severity.CRITICAL in severities:
        return STATE_CRITICAL_PT
    if Severity.ATTENTION in severities:
        return STATE_ATTENTION_PT
    if any(e.type == STOP_EVENT_TYPE for e in open_events):
        return STATE_STOPPED_PT
    qualities = [s.quality for s in samples.values()]
    if any(q.is_usable_value for q in qualities):
        return STATE_NORMAL_PT
    if qualities and all(q == Quality.COMM_ERROR for q in qualities):
        return STATE_NO_COMM_PT
    return STATE_UNKNOWN_PT


def event_brief(event: Event) -> dict[str, Any]:
    """Resumo curto de um evento para cards e stream."""
    return {
        "id": event.id,
        "type": event.type,
        "title_pt": event.title_pt,
        "severity": event.severity.value,
        "severity_pt": event.severity.label_pt,
        "status": event.status.value,
        "start_utc": jsonable(event.start_utc),
        "end_utc": jsonable(event.end_utc),
        "summary_pt": event.summary_pt,
    }


def _most_severe(events: list[Event]) -> Event | None:
    order = {Severity.CRITICAL: 0, Severity.ATTENTION: 1, Severity.INFO: 2}
    anomalies = [e for e in events if e.severity != Severity.INFO]
    if not anomalies:
        return None
    return sorted(anomalies, key=lambda e: (order[e.severity], e.start_utc))[0]


async def build_plant_card(container: Any, profile: EquipmentProfile) -> dict[str, Any]:
    """Card de um equipamento."""
    manager = container.manager
    status: EquipmentRuntimeStatus = manager.status(profile.id)
    snapshot = manager.live(profile.id)
    samples = _snapshot_samples(snapshot)
    ages = _snapshot_ages(snapshot)
    open_events: list[Event] = await container.events_repo.list(
        equipment_id=profile.id, open_only=True, limit=50
    )
    recent: list[Event] = await container.events_repo.list(equipment_id=profile.id, limit=1)
    recent_sorted = sorted(recent, key=lambda e: e.start_utc, reverse=True)
    anomaly = _most_severe(open_events)
    mass_flow = samples.get(MASS_FLOW_TAG)
    card = equipment_summary(profile)
    card.update(
        {
            "state_pt": classify_state(status, samples, open_events),
            "connection": status.connection.value,
            "connection_pt": status.connection.label_pt,
            "is_stale": status.is_stale,
            "last_read_utc": jsonable(status.last_read_utc),
            "last_event": event_brief(recent_sorted[0]) if recent_sorted else None,
            "open_event_count": len(open_events),
            "active_anomaly_pt": anomaly.title_pt if anomaly else None,
            "mass_flow": (
                tag_view(
                    mass_flow,
                    container.clock.monotonic_ns(),
                    container.clock.now_utc(),
                    ages.get(MASS_FLOW_TAG),
                )
                if mass_flow is not None
                else None
            ),
        }
    )
    return card


async def build_plant_cards(container: Any) -> list[dict[str, Any]]:
    """Cards de todos os equipamentos, na ordem da configuração."""
    return [await build_plant_card(container, p) for p in container.store.profiles.values()]


@router.get("/plant")
async def get_plant(container: ContainerDep) -> dict[str, Any]:
    """Visão de planta: um card por equipamento."""
    profiles = list(container.store.profiles.values())
    data_source = data_source_for(profiles)
    return {
        "data_source": data_source,
        "data_source_pt": data_source_label_pt(data_source),
        "generated_at_utc": jsonable(container.clock.now_utc()),
        "count": len(profiles),
        "cards": await build_plant_cards(container),
    }
