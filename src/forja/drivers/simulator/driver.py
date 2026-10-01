"""Driver do simulador WBF. Mesma porta dos drivers reais: so le.

Superficie publica: name, connect, disconnect, read, health, capabilities. Nada mais.
Cenario e sliders vivem em SimulatorControlRegistry. O tempo vem do Clock injetado.
"""

from __future__ import annotations

from datetime import datetime

from forja.domain.assets import EquipmentProfile
from forja.domain.errors import ConfigError, DriverReadError, DriverTimeout
from forja.domain.mapping import Mapping
from forja.domain.ports import (
    Clock,
    DriverCapabilities,
    DriverHealth,
    DriverSupportState,
    ReadOnlyDriverBase,
)
from forja.domain.samples import RawBlock, RawFrame, ReadPlan
from forja.drivers.simulator.controls import SIMULATOR_CONTROLS, SimulatorControlRegistry
from forja.drivers.simulator.physics_wbf import WbfModel, noise
from forja.drivers.simulator.scenarios import Scenario, scenario_from_text
from forja.version import __version__

SIM_READ_AREA = "sim"
_TIMEOUT_DETAIL_PT = "Tempo esgotado na leitura (cenário simulado de falha de comunicação)"


def _options(profile: EquipmentProfile) -> tuple[Scenario, int, float]:
    """Le scenario/seed/time_scale de communication.options com validacao."""
    opts = profile.communication.options
    scenario = scenario_from_text(opts.get("scenario", Scenario.NORMAL_OPERATION.value))
    seed = opts.get("seed", 0)
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ConfigError(f"{profile.id}: options.seed deve ser inteiro (recebido {seed!r})")
    time_scale_raw = opts.get("time_scale", 1.0)
    if isinstance(time_scale_raw, bool) or not isinstance(time_scale_raw, int | float):
        raise ConfigError(f"{profile.id}: options.time_scale deve ser número")
    time_scale = float(time_scale_raw)
    if not 0.0 < time_scale <= 1000.0:
        raise ConfigError(f"{profile.id}: options.time_scale deve estar em (0, 1000]")
    return scenario, seed, time_scale


class SimulatorDriver(ReadOnlyDriverBase):
    """Entrega RawFrame com um RawBlock por bloco do plano; payload = {tag: valor}."""

    name = "simulator"

    def __init__(
        self,
        profile: EquipmentProfile,
        mapping: Mapping,
        clock: Clock,
        controls: SimulatorControlRegistry | None = None,
    ) -> None:
        self._profile = profile
        self._mapping = mapping
        self._clock = clock
        self._controls = controls if controls is not None else SIMULATOR_CONTROLS
        scenario, seed, time_scale = _options(profile)
        self._controls.ensure(
            profile.id, clock, scenario=scenario, seed=seed, time_scale=time_scale
        )
        try:
            self._model = WbfModel(profile.reference_values)
        except ValueError as exc:
            raise ConfigError(f"{profile.id}: {exc}") from exc
        self._connected = False
        self._last_ok_utc: datetime | None = None
        self._last_latency_ms: float | None = None
        self._consecutive_errors = 0
        self._detail_pt = "Simulador não conectado"

    async def connect(self) -> None:
        self._connected = True
        self._detail_pt = "Simulador conectado"

    async def disconnect(self) -> None:
        self._connected = False
        self._detail_pt = "Simulador desconectado"

    async def read(self, plan: ReadPlan) -> RawFrame:
        if not self._connected:
            raise DriverReadError(f"{self._profile.id}: leitura sem conexão aberta")
        controls = self._controls.get(self._profile.id)
        if controls.scenario is Scenario.COMMUNICATION_FAILURE:
            self._consecutive_errors += 1
            self._detail_pt = _TIMEOUT_DETAIL_PT
            raise DriverTimeout(f"{self._profile.id}: {_TIMEOUT_DETAIL_PT}")
        t = controls.elapsed_s(self._clock)
        values = self._model.values(controls.scenario, t, controls.seed, controls.overrides)
        ts_utc = self._clock.now_utc()
        ts_mono_ns = self._clock.monotonic_ns()
        latency_ms = round(0.5 + 1.0 * (noise(controls.seed, "latency", t) + 1.0), 3)
        blocks = {
            block.block_id: RawBlock(
                block_id=block.block_id,
                payload={tag: values[tag] for tag in block.tags if tag in values},
                ts_utc=ts_utc,
                ts_mono_ns=ts_mono_ns,
                latency_ms=latency_ms,
            )
            for block in plan.blocks
        }
        self._last_ok_utc = ts_utc
        self._last_latency_ms = latency_ms
        self._consecutive_errors = 0
        self._detail_pt = f"Simulador em {controls.scenario.title_pt}"
        return RawFrame(
            equipment_id=self._profile.id, ts_utc=ts_utc, blocks=blocks, latency_ms=latency_ms
        )

    async def health(self) -> DriverHealth:
        return DriverHealth(
            connected=self._connected,
            last_ok_utc=self._last_ok_utc,
            latency_ms=self._last_latency_ms,
            consecutive_errors=self._consecutive_errors,
            detail_pt=self._detail_pt,
        )

    def capabilities(self) -> DriverCapabilities:
        return DriverCapabilities(
            protocol="simulator",
            support_state=DriverSupportState.AVAILABLE,
            library="forja",
            library_version=__version__,
            read_areas=(SIM_READ_AREA,),
            max_block_size=None,
            supports_device_identification=False,
            note_pt="Dados simulados. Nenhum valor representa um KCM real.",
        )
