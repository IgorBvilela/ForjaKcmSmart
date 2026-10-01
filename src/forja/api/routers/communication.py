"""Comunicação: suporte por driver (nunca AVAILABLE falso) e teste somente leitura."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from forja.api.deps import ContainerDep, jsonable
from forja.api.errors import ApiError
from forja.domain import (
    UNKNOWN,
    ConfigError,
    DriverSupportState,
    EquipmentProfile,
    Mapping,
    NotConfigured,
    UnsupportedDriver,
)

router = APIRouter(prefix="/api/v1/communication", tags=["comunicacao"])

FIELD_CONFIG_PT = "Disponível após configuração de campo"


class TestReadBody(BaseModel):
    """Perfil e mapping candidatos. Validados pelo domínio antes de qualquer tentativa."""

    model_config = ConfigDict(extra="forbid")

    profile: EquipmentProfile
    mapping: Mapping


def _support_state(info: Any) -> DriverSupportState:
    """Estado a partir do DriverSupportInfo do bloco 1 (aceita enum ou string)."""
    state = getattr(info, "state", None)
    if isinstance(state, DriverSupportState):
        return state
    try:
        return DriverSupportState(str(state))
    except ValueError:
        return DriverSupportState.UNSUPPORTED


def driver_support(container: Any) -> dict[str, Any]:
    """{nome: info} do registry, com rótulo em português."""
    support = container.registry.support()  # INTEGRACAO: DriverRegistry.support (bloco 1)
    out: dict[str, Any] = {}
    for name, info in sorted(support.items()):
        state = _support_state(info)
        view = jsonable(info)
        if not isinstance(view, dict):
            view = {"name": name}
        view["state"] = state.value
        view["state_pt"] = state.label_pt
        out[name] = view
    return out


def equipment_comm_state(profile: EquipmentProfile, support: dict[str, Any]) -> dict[str, Any]:
    """Estado de comunicação por equipamento. IP/protocolo UNKNOWN => NEEDS_CONFIGURATION."""
    driver = profile.communication.driver
    info = support.get(driver)
    registry_state = DriverSupportState(info["state"]) if info else DriverSupportState.UNSUPPORTED
    state = (
        DriverSupportState.NEEDS_CONFIGURATION
        if profile.communication.needs_configuration
        else registry_state
    )
    return {
        "equipment_id": profile.id,
        "driver": driver,
        "protocol": profile.communication.protocol,
        "ip_known": profile.communication.ip != UNKNOWN,
        "needs_configuration": profile.communication.needs_configuration,
        "support_state": state.value,
        "support_state_pt": state.label_pt,
        "driver_state": registry_state.value,
        "message_pt": FIELD_CONFIG_PT if state != DriverSupportState.AVAILABLE else "",
    }


@router.get("/drivers")
async def get_drivers(container: ContainerDep) -> dict[str, Any]:
    """Suporte por driver e estado por equipamento."""
    support = driver_support(container)
    statuses = container.manager.statuses()
    equipments = []
    for profile in container.store.profiles.values():
        view = equipment_comm_state(profile, support)
        status = statuses.get(profile.id)
        view["connection"] = status.connection.value if status else None
        view["connection_pt"] = status.connection.label_pt if status else None
        equipments.append(view)
    return {"drivers": support, "equipments": equipments, "read_only": True}


@router.post("/test-read", status_code=200)
async def test_read(body: TestReadBody, container: ContainerDep) -> dict[str, Any]:
    """Teste de leitura com driver descartável. Só lê; nunca escreve."""
    driver = body.profile.communication.driver
    support = driver_support(container)
    info = support.get(driver)
    if info is None or info["state"] == DriverSupportState.UNSUPPORTED.value:
        raise ApiError(
            409,
            "DRIVER_UNSUPPORTED",
            FIELD_CONFIG_PT,
            {"driver": driver, "reason_pt": (info or {}).get("reason_pt", "driver desconhecido")},
        )
    if body.profile.communication.needs_configuration:
        raise ApiError(
            409,
            "NEEDS_CONFIGURATION",
            "Não configurado: informe protocolo e endereço IP antes do teste de leitura.",
            {"driver": driver},
        )
    if body.mapping.equipment_id not in ("*", body.profile.id):
        raise ApiError(
            422,
            "MAPPING_MISMATCH",
            "O mapping informado pertence a outro equipamento.",
            {"mapping_equipment_id": body.mapping.equipment_id, "profile_id": body.profile.id},
        )
    # INTEGRACAO: EquipmentManager.test_read (bloco 3) devolve ReadTestResult; UnsupportedDriver
    # e NotConfigured propagam (não são resultado de leitura); ConfigError vem do plano/mapping.
    try:
        result = await container.manager.test_read(body.profile, body.mapping)
    except UnsupportedDriver as exc:
        raise ApiError(
            409, "DRIVER_UNSUPPORTED", FIELD_CONFIG_PT, {"driver": driver, "reason_pt": str(exc)}
        ) from exc
    except NotConfigured as exc:
        raise ApiError(
            409,
            "NEEDS_CONFIGURATION",
            "Não configurado: informe protocolo e endereço IP antes do teste de leitura.",
            {"driver": driver, "reason_pt": str(exc)},
        ) from exc
    except ConfigError as exc:
        raise ApiError(
            422,
            "CONFIG_INVALID",
            "Perfil ou mapping inválidos para o teste de leitura.",
            {"driver": driver, "detail": str(exc)[:500]},
        ) from exc
    view = jsonable(result)
    if not isinstance(view, dict):
        view = {"result": view}
    final = getattr(result, "final", None)
    view["final_pt"] = getattr(final, "label_pt", None)
    view["success"] = bool(getattr(final, "is_success", False))
    view["read_only"] = True
    return view
