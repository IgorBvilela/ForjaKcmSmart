"""Modelo fisico simplificado de dosador de correia (WBF) para o simulador.

Mass Flow ≈ Belt Load × Belt Speed (Documento Mestre §8.1). Nao reproduz o algoritmo do KCM.
TUDO aqui e SIMULADO: codigos, status brutos, limiares e tempos sao do simulador, nunca do KCM
real. O estado e funcao pura de (cenario, tempo decorrido, seed, referencias, overrides):
sem relogio, sem sleep, sem estado mutavel. Determinismo por seed via hash inteiro (sem random).

Codificacoes do SIMULADOR (documentadas aqui porque o mapping do simulador e identidade):
- machine_state: 0 STOP, 1 RUN, 2 ALARM. Nenhum cenario semente usa 2: alarme com a maquina
  rodando mantem RUN com alarm_active=1. O KCM real pode codificar de outro jeito: UNKNOWN.
- control_mode: 0 volumetrico, 1 gravimetrico.
- alarm_code: 56 (BELTLOAD LOW, observado em campo na GTEX para WBF; nao e universal) e
  8 (BAD SFT STATUS, catalogo marca HYPOTHESIS). Sao valores de cenario, nao verdade do KCM.
- stop_by: inteiro simulado; 1 = "Stop Input" (ver SIM_STOP_BY_LABELS). O KCM real: UNKNOWN.
- sft_status / mdu_status: inteiros brutos simulados, sem significado de bit.
"""

from __future__ import annotations

import math
import zlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from enum import IntEnum

from forja.drivers.simulator.scenarios import Scenario


class SimMachineState(IntEnum):
    """Codificacao do SIMULADOR para machine_state."""

    STOP = 0
    RUN = 1
    ALARM = 2


class SimControlMode(IntEnum):
    """Codificacao do SIMULADOR para control_mode."""

    VOLUMETRIC = 0
    GRAVIMETRIC = 1


SIM_ALARM_NONE = 0
SIM_ALARM_BELTLOAD_LOW = 56
SIM_ALARM_BAD_SFT_STATUS = 8
SIM_STOP_BY_NONE = 0
SIM_STOP_BY_STOP_INPUT = 1
SIM_STOP_BY_LABELS: dict[int, str] = {
    SIM_STOP_BY_NONE: "",
    SIM_STOP_BY_STOP_INPUT: "Stop Input",
}
"""Rotulo do codigo inteiro SIMULADO de stop_by. O catalogo de STOP BY classifica o rotulo."""
SIM_SFT_STATUS_NORMAL = 0x0000_0181
SIM_SFT_STATUS_FAULT = 0x0000_0183
SIM_MDU_STATUS_RUN = 0x0101
SIM_MDU_STATUS_STOP = 0x0100

DRIVE_REF_PCT = 40.0
"""Esforco do acionamento quando o dosador esta na referencia (constante do simulador)."""
DRIVE_CEILING_PCT = 100.0
INT_CHANNEL_NORMAL_PCT = 95.0
INT_CHANNEL_DEGRADED_PCT = 40.0
WEIGH_LENGTH_M = 0.5
"""Comprimento pesado da correia (m) usado so para derivar net_weight a partir de belt_load."""

DEFAULT_REFS: dict[str, float] = {"setpoint_ref": 1000.0, "belt_load_ref": 1.0, "rpm_ref": 50.0}
"""Referencias genericas do simulador quando o perfil nao traz reference_values."""

SIM_TAGS: tuple[str, ...] = (
    "machine_state",
    "setpoint",
    "mass_flow",
    "drive_command",
    "rpm",
    "belt_load",
    "net_weight",
    "alarm_code",
    "alarm_active",
    "stop_by",
    "sft_status",
    "mdu_status",
    "int_channel_pct",
    "control_mode",
)

_MASK64 = (1 << 64) - 1


def _mix64(*parts: int) -> int:
    """Mistura inteira estilo splitmix64. Deterministica, sem modulo random."""
    x = 0x9E3779B97F4A7C15
    for p in parts:
        x = (x ^ (p & _MASK64)) & _MASK64
        x = (x * 0xBF58476D1CE4E5B9) & _MASK64
        x ^= x >> 31
        x = (x * 0x94D049BB133111EB) & _MASK64
        x ^= x >> 29
    return x


def noise(seed: int, tag: str, t_s: float, tick_s: float = 0.5) -> float:
    """Ruido deterministico em [-1, 1], estavel dentro de cada tick de `tick_s`."""
    tick = math.floor(t_s / tick_s) if t_s > 0 else 0
    h = _mix64(seed, zlib.crc32(tag.encode("utf-8")), tick)
    return (h / _MASK64) * 2.0 - 1.0


def smoothstep(t: float, start: float, duration: float) -> float:
    """Rampa suave de 0 a 1 entre `start` e `start + duration`."""
    if duration <= 0:
        return 1.0 if t >= start else 0.0
    x = min(max((t - start) / duration, 0.0), 1.0)
    return x * x * (3.0 - 2.0 * x)


def _clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


@dataclass(frozen=True)
class _Phys:
    """Estado fisico sem ruido, em unidade de engenharia."""

    machine_state: SimMachineState
    belt_load: float
    drive: float
    rpm: float
    mass_flow: float
    alarm_code: int = SIM_ALARM_NONE
    stop_by: int = SIM_STOP_BY_NONE
    sft_status: int = SIM_SFT_STATUS_NORMAL
    mdu_status: int = SIM_MDU_STATUS_RUN
    int_channel: float = INT_CHANNEL_NORMAL_PCT
    weight_noise_gain: float = 1.0
    flow_noise_gain: float = 1.0


def _positive(value: float, name: str) -> float:
    v = float(value)
    if not math.isfinite(v) or v <= 0:
        raise ValueError(f"reference_values.{name} deve ser > 0 (recebido {value!r})")
    return v


class WbfModel:
    """Dosador WBF simulado. `values()` e funcao pura do tempo decorrido."""

    def __init__(self, refs: Mapping[str, float] | None = None) -> None:
        merged = {**DEFAULT_REFS, **dict(refs or {})}
        self.setpoint_ref = _positive(merged["setpoint_ref"], "setpoint_ref")
        self.belt_load_ref = _positive(merged["belt_load_ref"], "belt_load_ref")
        self.rpm_ref = _positive(merged["rpm_ref"], "rpm_ref")
        self._by_scenario: dict[Scenario, Callable[[float], _Phys]] = {
            Scenario.NORMAL_OPERATION: self._normal,
            Scenario.BELTLOAD_LOW: self._beltload_low,
            Scenario.RATE_LOW: self._rate_low,
            Scenario.ENCODER_FAILURE: self._encoder_failure,
            Scenario.SFT_FAILURE: self._sft_failure,
            Scenario.DRIVE_COMMAND_HIGH: self._drive_command_high,
            Scenario.INT_CHANNEL_DEGRADED: self._int_channel_degraded,
            Scenario.COMMUNICATION_FAILURE: self._normal,
            Scenario.STOP_NORMAL: self._stop_normal,
        }

    def values(
        self,
        scenario: Scenario,
        t_elapsed_s: float,
        seed: int,
        overrides: Mapping[str, float] | None = None,
    ) -> dict[str, float | int]:
        """Valores de todas as SIM_TAGS no instante `t_elapsed_s`. Overrides fixam a tag."""
        t = max(0.0, float(t_elapsed_s))
        phys = self._by_scenario[scenario](t)
        out = self._emit(phys, t, seed)
        for tag, value in (overrides or {}).items():
            if tag in out:
                out[tag] = float(value)
        return out

    # --- cinematica -------------------------------------------------------------------------

    def _run(
        self,
        load_factor: float,
        drive: float,
        *,
        alarm_code: int = SIM_ALARM_NONE,
    ) -> _Phys:
        """Maquina em RUN: velocidade proporcional ao drive; vazao = carga × velocidade."""
        drive = _clamp(drive, 0.0, DRIVE_CEILING_PCT)
        speed_factor = drive / DRIVE_REF_PCT
        return _Phys(
            machine_state=SimMachineState.RUN,
            belt_load=self.belt_load_ref * load_factor,
            drive=drive,
            rpm=self.rpm_ref * speed_factor,
            mass_flow=self.setpoint_ref * load_factor * speed_factor,
            alarm_code=alarm_code,
        )

    # --- cenarios ---------------------------------------------------------------------------

    def _normal(self, _t: float) -> _Phys:
        return self._run(1.0, DRIVE_REF_PCT)

    def _beltload_low(self, t: float) -> _Phys:
        """Carga cai a 45% entre 5 s e 65 s; drive sobe (controlador com leve folga);
        alarme simulado 56 apos 10 s de persistencia (t >= 75 s)."""
        load_factor = 1.0 - 0.55 * smoothstep(t, 5.0, 60.0)
        required = DRIVE_REF_PCT / load_factor
        drive = DRIVE_REF_PCT + 0.97 * (required - DRIVE_REF_PCT)
        alarm = SIM_ALARM_BELTLOAD_LOW if t >= 75.0 else SIM_ALARM_NONE
        return self._run(load_factor, drive, alarm_code=alarm)

    def _rate_low(self, t: float) -> _Phys:
        """Drive vai ao teto em 20 s e a vazao assenta 20% abaixo do setpoint."""
        x = smoothstep(t, 0.0, 20.0)
        drive = DRIVE_REF_PCT + (DRIVE_CEILING_PCT - DRIVE_REF_PCT) * x
        flow_factor = 1.0 - 0.20 * x
        load_factor = flow_factor / (drive / DRIVE_REF_PCT)
        return self._run(load_factor, drive)

    def _encoder_failure(self, t: float) -> _Phys:
        """A partir de 20 s a velocidade indicada cai a zero; o resto segue em RUN."""
        phys = self._normal(t)
        if t >= 20.0:
            phys = replace(phys, rpm=0.0)
        return phys

    def _sft_failure(self, t: float) -> _Phys:
        """A partir de 30 s o status bruto da SFT muda e o peso fica ruidoso; alarme 8 em 40 s."""
        phys = self._normal(t)
        if t >= 30.0:
            phys = replace(
                phys, sft_status=SIM_SFT_STATUS_FAULT, weight_noise_gain=60.0, flow_noise_gain=8.0
            )
        if t >= 40.0:
            phys = replace(phys, alarm_code=SIM_ALARM_BAD_SFT_STATUS)
        return phys

    def _drive_command_high(self, t: float) -> _Phys:
        """Drive oscila entre 88% e 96% (apos 15 s) com a vazao no setpoint."""
        x = smoothstep(t, 0.0, 15.0)
        target = 92.0 + 3.0 * math.sin(2.0 * math.pi * t / 45.0)
        drive = DRIVE_REF_PCT + (target - DRIVE_REF_PCT) * x
        load_factor = DRIVE_REF_PCT / drive
        return self._run(load_factor, drive)

    def _int_channel_degraded(self, t: float) -> _Phys:
        """Canal de integracao cai de 95% para 40% entre 5 s e 65 s (limiar SIMULADO)."""
        phys = self._normal(t)
        drop_pct = INT_CHANNEL_NORMAL_PCT - INT_CHANNEL_DEGRADED_PCT
        return replace(
            phys, int_channel=INT_CHANNEL_NORMAL_PCT - drop_pct * smoothstep(t, 5.0, 60.0)
        )

    def _stop_normal(self, _t: float) -> _Phys:
        """Parada por entrada de parada. Material fica na correia."""
        return _Phys(
            machine_state=SimMachineState.STOP,
            belt_load=self.belt_load_ref,
            drive=0.0,
            rpm=0.0,
            mass_flow=0.0,
            stop_by=SIM_STOP_BY_STOP_INPUT,
            mdu_status=SIM_MDU_STATUS_STOP,
        )

    # --- saida ------------------------------------------------------------------------------

    def _emit(self, phys: _Phys, t: float, seed: int) -> dict[str, float | int]:
        running = phys.machine_state != SimMachineState.STOP

        def n(tag: str) -> float:
            return noise(seed, tag, t) if running else 0.0

        mass_flow = max(0.0, phys.mass_flow * (1.0 + 0.003 * phys.flow_noise_gain * n("mass_flow")))
        belt_load = max(0.0, phys.belt_load * (1.0 + 0.005 * n("belt_load")))
        drive = (
            _clamp(phys.drive + 0.2 * n("drive_command"), 0.0, DRIVE_CEILING_PCT)
            if running
            else 0.0
        )
        rpm = max(0.0, phys.rpm + 0.3 * n("rpm")) if phys.rpm > 0 else 0.0
        net_weight = max(
            0.0,
            belt_load * WEIGH_LENGTH_M * (1.0 + 0.002 * phys.weight_noise_gain * n("net_weight")),
        )
        int_channel = _clamp(phys.int_channel + 0.2 * n("int_channel_pct"), 0.0, 100.0)
        return {
            "machine_state": int(phys.machine_state),
            "setpoint": round(self.setpoint_ref, 2),
            "mass_flow": round(mass_flow, 2),
            "drive_command": round(drive, 2),
            "rpm": round(rpm, 2),
            "belt_load": round(belt_load, 4),
            "net_weight": round(net_weight, 4),
            "alarm_code": int(phys.alarm_code),
            "alarm_active": 1 if phys.alarm_code != SIM_ALARM_NONE else 0,
            "stop_by": int(phys.stop_by),
            "sft_status": int(phys.sft_status),
            "mdu_status": int(phys.mdu_status),
            "int_channel_pct": round(int_channel, 2),
            "control_mode": int(SimControlMode.GRAVIMETRIC),
        }
