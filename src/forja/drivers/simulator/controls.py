"""Controles do simulador: cenario, escala de tempo, seed e sliders, por equipamento.

Vivem FORA do driver de proposito: o driver so tem connect/disconnect/read/health/capabilities.
A API fala com SIMULATOR_CONTROLS; o driver apenas le daqui. Nada aqui toca em dispositivo real.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field, field_validator

from forja.domain.ports import Clock
from forja.drivers.simulator.scenarios import Scenario

SLIDER_TAGS: tuple[str, ...] = (
    "setpoint",
    "mass_flow",
    "drive_command",
    "rpm",
    "belt_load",
    "net_weight",
    "int_channel_pct",
)
"""Tags que o modo avancado pode fixar manualmente (Documento Mestre §25)."""


class SimulatorControls(BaseModel):
    """Estado de controle de um simulador. Imutavel: o registro troca a instancia inteira."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    equipment_id: str
    scenario: Scenario = Scenario.NORMAL_OPERATION
    time_scale: float = Field(default=1.0, gt=0.0, le=1000.0)
    seed: int = 0
    overrides: dict[str, float] = Field(default_factory=dict)
    """Sliders: fixam o valor da tag na saida; nao recalculam a fisica."""
    scenario_started_mono_ns: int | None = None
    """Instante (relogio monotonico) em que o cenario atual comecou."""

    @field_validator("overrides")
    @classmethod
    def _check_overrides(cls, value: dict[str, float]) -> dict[str, float]:
        unknown = sorted(set(value) - set(SLIDER_TAGS))
        if unknown:
            raise ValueError(f"sliders desconhecidos: {unknown}; válidos: {list(SLIDER_TAGS)}")
        bad = sorted(tag for tag, v in value.items() if not math.isfinite(v))
        if bad:
            raise ValueError(f"valor não numérico nos sliders: {bad}")
        return dict(value)

    def elapsed_s(self, clock: Clock) -> float:
        """Tempo decorrido do cenario, ja multiplicado por time_scale. Nunca negativo."""
        if self.scenario_started_mono_ns is None:
            return 0.0
        real = (clock.monotonic_ns() - self.scenario_started_mono_ns) / 1_000_000_000
        return max(0.0, real) * self.time_scale


class SimulatorControlRegistry:
    """Guarda SimulatorControls por equipment_id. Um por processo (SIMULATOR_CONTROLS)."""

    def __init__(self) -> None:
        self._by_id: dict[str, SimulatorControls] = {}

    def ids(self) -> list[str]:
        return sorted(self._by_id)

    def has(self, equipment_id: str) -> bool:
        return equipment_id in self._by_id

    def get(self, equipment_id: str) -> SimulatorControls:
        try:
            return self._by_id[equipment_id]
        except KeyError as exc:
            raise KeyError(f"simulador sem controles registrados: {equipment_id!r}") from exc

    def ensure(
        self,
        equipment_id: str,
        clock: Clock,
        *,
        scenario: Scenario = Scenario.NORMAL_OPERATION,
        seed: int = 0,
        time_scale: float = 1.0,
    ) -> SimulatorControls:
        """Cria os controles se nao existirem. Nunca sobrescreve os existentes."""
        existing = self._by_id.get(equipment_id)
        if existing is not None:
            return existing
        controls = SimulatorControls(
            equipment_id=equipment_id,
            scenario=scenario,
            seed=seed,
            time_scale=time_scale,
            scenario_started_mono_ns=clock.monotonic_ns(),
        )
        self._by_id[equipment_id] = controls
        return controls

    def set_scenario(
        self, equipment_id: str, scenario: Scenario, clock: Clock
    ) -> SimulatorControls:
        """Troca o cenario e reinicia o tempo decorrido (t = 0). Cria se nao existir."""
        current = self._by_id.get(equipment_id) or SimulatorControls(equipment_id=equipment_id)
        updated = SimulatorControls.model_validate(
            {
                **current.model_dump(),
                "scenario": scenario,
                "scenario_started_mono_ns": clock.monotonic_ns(),
            }
        )
        self._by_id[equipment_id] = updated
        return updated

    def set_overrides(self, equipment_id: str, overrides: dict[str, float]) -> SimulatorControls:
        """Funde os sliders informados aos existentes. Valida chaves e valores."""
        current = self.get(equipment_id)
        merged = {**current.overrides, **overrides}
        updated = SimulatorControls.model_validate({**current.model_dump(), "overrides": merged})
        self._by_id[equipment_id] = updated
        return updated

    def clear_overrides(self, equipment_id: str) -> SimulatorControls:
        current = self.get(equipment_id)
        updated = SimulatorControls.model_validate({**current.model_dump(), "overrides": {}})
        self._by_id[equipment_id] = updated
        return updated

    def forget(self, equipment_id: str) -> None:
        """Remove os controles (equipamento apagado ou isolamento em teste)."""
        self._by_id.pop(equipment_id, None)

    def elapsed_s(self, equipment_id: str, clock: Clock) -> float:
        return self.get(equipment_id).elapsed_s(clock)


SIMULATOR_CONTROLS = SimulatorControlRegistry()
"""Singleton de processo. A API usa isto; o driver so le."""
