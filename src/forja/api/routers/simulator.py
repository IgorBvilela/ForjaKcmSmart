"""Controles do simulador. Afetam só o modelo físico simulado; nada chega ao KCM.

Equipamento cujo driver não é `simulator` recebe 409. O registry de controles vem do bloco 1
(`forja.drivers.simulator.controls.SIMULATOR_CONTROLS`), importado dentro da função.
"""

from __future__ import annotations

import math
from typing import Annotated, Any

from fastapi import APIRouter
from fastapi import Path as PathParam
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from forja.api.deps import ContainerDep, jsonable, require_profile
from forja.api.errors import ApiError
from forja.domain import EquipmentProfile

DEFAULT_SCENARIO_CODE = "NORMAL_OPERATION"

router = APIRouter(prefix="/api/v1/simulator", tags=["simulador"])

EquipmentId = Annotated[str, PathParam(max_length=64)]

SLIDER_KEYS: frozenset[str] = frozenset(
    {"setpoint", "mass_flow", "drive_command", "rpm", "belt_load", "net_weight", "int_channel_pct"}
)
"""Sliders aceitos (contrato do bloco 1). Qualquer outra chave é recusada."""

SIMULATOR_NOTE_PT = "Controles afetam apenas o simulador. Nenhum comando chega ao KCM."


class ScenarioBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: str = Field(min_length=1, max_length=64, pattern=r"^[A-Z][A-Z0-9_]*$")


class ControlsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overrides: dict[str, float] = Field(min_length=1, max_length=len(SLIDER_KEYS))

    @field_validator("overrides")
    @classmethod
    def _only_known_sliders(cls, value: dict[str, float]) -> dict[str, float]:
        unknown = sorted(set(value) - SLIDER_KEYS)
        if unknown:
            raise ValueError(f"sliders desconhecidos: {unknown}; aceitos: {sorted(SLIDER_KEYS)}")
        bad = [k for k, v in value.items() if not math.isfinite(v)]
        if bad:
            raise ValueError(f"valores não finitos em: {bad}")
        return value


def _controls_api() -> tuple[Any, Any]:
    """Importa tarde o registry de controles e o enum de cenários do bloco 1."""
    try:
        # INTEGRACAO: bloco 1 (forja.drivers.simulator). Import tardio por desenho.
        from forja.drivers.simulator.controls import SIMULATOR_CONTROLS
        from forja.drivers.simulator.scenarios import Scenario
    except ImportError as exc:
        raise ApiError(
            503,
            "SIMULATOR_UNAVAILABLE",
            "Simulador indisponível neste build.",
            {"module": str(exc)},
        ) from exc
    return SIMULATOR_CONTROLS, Scenario


def require_simulator(container: Any, equipment_id: str) -> EquipmentProfile:
    """Perfil com driver simulator, ou 409."""
    profile = require_profile(container, equipment_id)
    if not profile.is_simulated:
        raise ApiError(
            409,
            "NOT_SIMULATOR",
            "Este equipamento não usa o simulador; controles indisponíveis.",
            {"equipment_id": profile.id, "driver": profile.communication.driver},
        )
    return profile


def _scenario_views(scenario_enum: Any) -> list[dict[str, Any]]:
    return [
        {
            "code": str(getattr(s, "value", s)),
            "title_pt": getattr(s, "title_pt", str(getattr(s, "value", s))),
            "description_pt": getattr(s, "description_pt", ""),
        }
        for s in scenario_enum
    ]


def _view(equipment_id: str, controls_registry: Any, scenario_enum: Any) -> dict[str, Any]:
    return {
        "equipment_id": equipment_id,
        "controls": jsonable(controls_registry.get(equipment_id)),
        "scenarios": _scenario_views(scenario_enum),
        "sliders": sorted(SLIDER_KEYS),
        "note_pt": SIMULATOR_NOTE_PT,
    }


def _parse_scenario(scenario_enum: Any, code: str) -> Any:
    valid = {str(getattr(s, "value", s)): s for s in scenario_enum}
    if code not in valid:
        raise ApiError(
            422,
            "UNKNOWN_SCENARIO",
            "Cenário desconhecido.",
            {"scenario": code, "valid": sorted(valid)},
        )
    return valid[code]


def _ensure_controls(
    controls_registry: Any, scenario_enum: Any, profile: EquipmentProfile, clock: Any
) -> None:
    """Garante que o equipamento tem controles, mesmo antes do driver criá-los.

    O driver chama `ensure()` ao nascer; a API pode chegar antes do loop (ou sem loop, em
    teste). `ensure()` nunca sobrescreve controles existentes, então é seguro nos dois casos.
    """
    # INTEGRACAO: espelha SimulatorDriver._options (bloco 1): scenario/seed/time_scale em
    # communication.options do perfil.
    if controls_registry.has(profile.id):
        return
    opts = profile.communication.options
    scenario_code = str(opts.get("scenario", DEFAULT_SCENARIO_CODE)).strip().upper()
    scenario = _parse_scenario(scenario_enum, scenario_code)
    seed = opts.get("seed", 0)
    time_scale = opts.get("time_scale", 1.0)
    try:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError(f"options.seed deve ser inteiro (recebido {seed!r})")
        if isinstance(time_scale, bool) or not isinstance(time_scale, int | float):
            raise ValueError("options.time_scale deve ser número")
        controls_registry.ensure(
            profile.id, clock, scenario=scenario, seed=seed, time_scale=float(time_scale)
        )
    except (ValueError, ValidationError) as exc:
        raise ApiError(
            422,
            "SIMULATOR_OPTIONS_INVALID",
            "Opções do simulador inválidas no perfil do equipamento.",
            {"equipment_id": profile.id, "detail": str(exc)[:300]},
        ) from exc


def _prepare(container: Any, equipment_id: str) -> tuple[EquipmentProfile, Any, Any]:
    """Perfil simulado + registry de controles pronto + enum de cenários."""
    profile = require_simulator(container, equipment_id)
    controls, scenario_enum = _controls_api()
    _ensure_controls(controls, scenario_enum, profile, container.clock)
    return profile, controls, scenario_enum


@router.get("/{equipment_id}")
async def get_simulator(equipment_id: EquipmentId, container: ContainerDep) -> dict[str, Any]:
    """Controles atuais, cenários disponíveis e sliders aceitos."""
    profile, controls, scenario_enum = _prepare(container, equipment_id)
    return _view(profile.id, controls, scenario_enum)


@router.post("/{equipment_id}/scenario", status_code=200)
async def set_scenario(
    equipment_id: EquipmentId, body: ScenarioBody, container: ContainerDep
) -> dict[str, Any]:
    """Troca o cenário do simulador deste equipamento."""
    profile, controls, scenario_enum = _prepare(container, equipment_id)
    scenario = _parse_scenario(scenario_enum, body.scenario)
    controls.set_scenario(profile.id, scenario, container.clock)
    return _view(profile.id, controls, scenario_enum)


@router.post("/{equipment_id}/controls", status_code=200)
async def set_controls(
    equipment_id: EquipmentId, body: ControlsBody, container: ContainerDep
) -> dict[str, Any]:
    """Aplica sliders (overrides) ao simulador."""
    profile, controls, scenario_enum = _prepare(container, equipment_id)
    controls.set_overrides(profile.id, dict(body.overrides))
    return _view(profile.id, controls, scenario_enum)


@router.delete("/{equipment_id}/controls", status_code=200)
async def clear_controls(equipment_id: EquipmentId, container: ContainerDep) -> dict[str, Any]:
    """Remove todos os sliders; o cenário continua."""
    profile, controls, scenario_enum = _prepare(container, equipment_id)
    controls.clear_overrides(profile.id)
    return _view(profile.id, controls, scenario_enum)
