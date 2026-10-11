"""Roteadores da API v1. Cada arquivo cuida de um recurso; `ALL_ROUTERS` é a ordem de registro."""

from fastapi import APIRouter

from forja.api.routers import (
    backups,
    commissioning,
    communication,
    diagnostics,
    equipment_admin,
    equipments,
    events,
    health,
    history,
    intelligence,
    plant,
    reports,
    simulator,
    situation,
    stream,
    system,
    tags,
    timesplit,
    ui,
)

ALL_ROUTERS: tuple[APIRouter, ...] = (
    health.router,
    system.router,
    backups.router,
    tags.router,
    plant.router,
    situation.router,
    timesplit.router,
    equipments.router,
    equipment_admin.router,
    history.router,
    reports.router,
    events.router,
    diagnostics.router,
    intelligence.router,
    communication.router,
    commissioning.router,
    simulator.router,
    stream.router,
    ui.router,
)

__all__ = ["ALL_ROUTERS"]
