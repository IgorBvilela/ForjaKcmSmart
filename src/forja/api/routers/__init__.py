"""Roteadores da API v1. Cada arquivo cuida de um recurso; `ALL_ROUTERS` é a ordem de registro."""

from fastapi import APIRouter

from forja.api.routers import (
    commissioning,
    communication,
    diagnostics,
    equipments,
    events,
    health,
    history,
    plant,
    simulator,
    stream,
    tags,
    ui,
)

ALL_ROUTERS: tuple[APIRouter, ...] = (
    health.router,
    tags.router,
    plant.router,
    equipments.router,
    history.router,
    events.router,
    diagnostics.router,
    communication.router,
    commissioning.router,
    simulator.router,
    stream.router,
    ui.router,
)

__all__ = ["ALL_ROUTERS"]
