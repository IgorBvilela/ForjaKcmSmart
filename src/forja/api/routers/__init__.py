"""Roteadores da API v1. Cada arquivo cuida de um recurso; `ALL_ROUTERS` é a ordem de registro."""

from fastapi import APIRouter

from forja.api.routers import (
    communication,
    diagnostics,
    equipments,
    events,
    health,
    history,
    plant,
    simulator,
    stream,
    ui,
)

ALL_ROUTERS: tuple[APIRouter, ...] = (
    health.router,
    plant.router,
    equipments.router,
    history.router,
    events.router,
    diagnostics.router,
    communication.router,
    simulator.router,
    stream.router,
    ui.router,
)

__all__ = ["ALL_ROUTERS"]
