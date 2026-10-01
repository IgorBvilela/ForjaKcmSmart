"""Regras determinísticas do motor de eventos.

DETERMINÍSTICO significa, aqui, três coisas concretas:

1. Mesma entrada produz sempre a mesma saída. Nenhuma regra sorteia, aprende
   ou consulta relógio próprio: o tempo vem do timestamp das amostras.
2. Toda regra é identificada por `rule_id` + `version`. Quando o limiar muda,
   a versão muda, e o evento gravado registra com qual versão foi reconhecido.
3. Toda regra devolve as EVIDÊNCIAS que a sustentam. Um evento sem evidência
   não é aberto.

REGRA DE OURO — DADO VELHO NÃO DISPARA EVENTO
---------------------------------------------
`_num` e `_txt` só enxergam valores de agora (GOOD, SIMULATED, UNCERTAIN).
Valor STALE ou COMM_ERROR devolve None, e a regra se abstém.

Sem isso, uma queda de comunicação congelaria o último RPM e o motor
começaria a inventar anomalias a partir de números que não são mais reais.
Perda de comunicação tem eventos próprios (COMMUNICATION_LOSS e DATA_STALE);
as demais regras ficam caladas enquanto o dado não voltar.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Sequence

from forja.acquisition.scheduler import CycleResult
from forja.domain.equipment import EquipmentCard
from forja.domain.models import (Application, MachineState, Quality, Sample, StopByClass,
                                 TAG_CATALOG, classify_stop_by)

from . import alarms
from .models import Event, EventType, Evidence, Severity

# qualidades que representam "este valor é de agora"
FRESH = {Quality.GOOD, Quality.SIMULATED, Quality.UNCERTAIN}


# ---------------------------------------------------------------------------
# Contexto de avaliação
# ---------------------------------------------------------------------------
@dataclass
class RuleContext:
    equipment: EquipmentCard
    now: datetime
    samples: dict[str, Sample]          # último valor de cada tag
    cycle: CycleResult                  # o ciclo de aquisição que acabou
    history: Sequence[dict[str, Sample]] = field(default_factory=list)

    @property
    def application(self) -> Application:
        return self.equipment.controller.application

    @property
    def controller_model(self) -> str:
        m = self.equipment.controller.model
        return m if m and m != "UNKNOWN" else "KCM"


@dataclass
class RuleHit:
    """O que a regra viu. `active=False` significa condição ausente."""
    active: bool
    evidences: list[Evidence] = field(default_factory=list)
    summary: str = ""
    severity: Optional[Severity] = None      # sobrepõe a severidade padrão da regra
    extra: dict[str, Any] = field(default_factory=dict)


def _evidence(ctx: RuleContext, tag: str, note: str = "") -> Optional[Evidence]:
    s = ctx.samples.get(tag)
    if s is None:
        return None
    cat = TAG_CATALOG.get(tag)
    return Evidence(tag=tag, label=cat.display_name if cat else tag, value=s.value,
                    unit=cat.unit if cat else "", ts=s.ts, quality=s.quality.value, note=note)


def _num(ctx: RuleContext, tag: str) -> Optional[float]:
    """Valor numérico ATUAL da tag. None se ausente, não numérico ou não fresco."""
    s = ctx.samples.get(tag)
    if s is None or s.quality not in FRESH or not s.is_numeric:
        return None
    return float(s.value)


def _txt(ctx: RuleContext, tag: str) -> Optional[str]:
    s = ctx.samples.get(tag)
    if s is None or s.quality not in FRESH:
        return None
    return str(s.value)


# ---------------------------------------------------------------------------
# Contrato da regra
# ---------------------------------------------------------------------------
@dataclass
class Rule:
    rule_id: str
    version: str
    event_type: EventType
    severity: Severity
    description: str
    for_cycles: int = 3        # ciclos consecutivos com condição ativa para ABRIR
    clear_cycles: int = 3      # ciclos consecutivos sem condição para FECHAR
    params: dict[str, Any] = field(default_factory=dict)

    def evaluate(self, ctx: RuleContext) -> RuleHit:      # pragma: no cover - abstrato
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Regras
# ---------------------------------------------------------------------------
@dataclass
class SpeedFeedbackAnomaly(Rule):
    """Motor comandado e realimentação de velocidade em zero.

    Reconhece o SINTOMA. Não afirma encoder, cabo nem interface: a separação
    de causas é trabalho da biblioteca de diagnóstico.
    """
    rule_id: str = "R-SPEED-001"
    version: str = "1.0"
    event_type: EventType = EventType.SPEED_FEEDBACK_ANOMALY
    severity: Severity = Severity.ALARM
    description: str = "Drive Command acionando e RPM realimentada em zero"
    for_cycles: int = 3
    params: dict[str, Any] = field(default_factory=lambda: {"min_drive_command_pct": 5.0,
                                                            "rpm_zero_tol": 0.5})

    def evaluate(self, ctx: RuleContext) -> RuleHit:
        state = _txt(ctx, "machine_state")
        dc = _num(ctx, "drive_command")
        rpm = _num(ctx, "rpm")
        if state is None or dc is None or rpm is None:
            return RuleHit(active=False)
        if state != MachineState.RUN.value:
            return RuleHit(active=False)
        if dc < self.params["min_drive_command_pct"] or rpm > self.params["rpm_zero_tol"]:
            return RuleHit(active=False)
        ev = [e for e in (
            _evidence(ctx, "machine_state", "máquina em operação"),
            _evidence(ctx, "drive_command", "acionamento sendo comandado"),
            _evidence(ctx, "rpm", "realimentação de velocidade em zero"),
            _evidence(ctx, "mass_flow"), _evidence(ctx, "belt_load"),
            _evidence(ctx, "alarm_code"), _evidence(ctx, "motor_load_pct"),
        ) if e is not None]
        return RuleHit(active=True, evidences=ev,
                       summary=f"RPM indicada em {rpm:.0f} com Drive Command em {dc:.1f} % e máquina em RUN")


@dataclass
class BeltLoadLow(Rule):
    rule_id: str = "R-BELT-001"
    version: str = "1.0"
    event_type: EventType = EventType.BELT_LOAD_LOW
    severity: Severity = Severity.WARNING
    description: str = "Belt Load abaixo da fração mínima da referência volumétrica"
    for_cycles: int = 5
    params: dict[str, Any] = field(default_factory=lambda: {"min_fraction_of_ref": 0.7,
                                                            "abs_floor_kg_m": 0.05})

    def evaluate(self, ctx: RuleContext) -> RuleHit:
        bl = _num(ctx, "belt_load")
        ref = _num(ctx, "vol_belt_load")
        state = _txt(ctx, "machine_state")
        if bl is None or state != MachineState.RUN.value:
            return RuleHit(active=False)
        if ref is None or ref <= self.params["abs_floor_kg_m"]:
            return RuleHit(active=False)      # sem referência confiável, a regra se abstém
        if bl >= ref * self.params["min_fraction_of_ref"]:
            return RuleHit(active=False)
        ev = [e for e in (_evidence(ctx, "belt_load", f"{bl / ref:.0%} da referência"),
                          _evidence(ctx, "vol_belt_load", "referência volumétrica"),
                          _evidence(ctx, "drive_command"), _evidence(ctx, "mass_flow"),
                          _evidence(ctx, "alarm_code")) if e is not None]
        return RuleHit(active=True, evidences=ev,
                       summary=f"Belt Load em {bl:.3f} kg/m, {bl / ref:.0%} da referência {ref:.3f} kg/m")


@dataclass
class DriveCommandSaturated(Rule):
    rule_id: str = "R-DRIVE-001"
    version: str = "1.0"
    event_type: EventType = EventType.DRIVE_COMMAND_SATURATED
    severity: Severity = Severity.WARNING
    description: str = "Drive Command sustentado no topo da faixa"
    for_cycles: int = 10
    params: dict[str, Any] = field(default_factory=lambda: {"threshold_pct": 95.0})

    def evaluate(self, ctx: RuleContext) -> RuleHit:
        dc = _num(ctx, "drive_command")
        state = _txt(ctx, "machine_state")
        if dc is None or state != MachineState.RUN.value or dc < self.params["threshold_pct"]:
            return RuleHit(active=False)
        ev = [e for e in (_evidence(ctx, "drive_command"), _evidence(ctx, "mass_flow"),
                          _evidence(ctx, "setpoint"), _evidence(ctx, "belt_load")) if e is not None]
        return RuleHit(active=True, evidences=ev,
                       summary=f"Drive Command em {dc:.1f} % (limiar {self.params['threshold_pct']:.0f} %)")


@dataclass
class RateDeviation(Rule):
    rule_id: str = "R-RATE-001"
    version: str = "1.0"
    event_type: EventType = EventType.RATE_DEVIATION
    severity: Severity = Severity.WARNING
    description: str = "Vazão fora da faixa do setpoint por tempo sustentado"
    for_cycles: int = 10
    params: dict[str, Any] = field(default_factory=lambda: {"max_deviation_frac": 0.10,
                                                            "min_setpoint": 1.0})

    def evaluate(self, ctx: RuleContext) -> RuleHit:
        sp = _num(ctx, "setpoint")
        mf = _num(ctx, "mass_flow")
        state = _txt(ctx, "machine_state")
        if sp is None or mf is None or state != MachineState.RUN.value:
            return RuleHit(active=False)
        if sp < self.params["min_setpoint"]:
            return RuleHit(active=False)
        dev = abs(mf - sp) / sp
        if dev <= self.params["max_deviation_frac"]:
            return RuleHit(active=False)
        ev = [e for e in (_evidence(ctx, "mass_flow", f"desvio de {dev:.1%}"),
                          _evidence(ctx, "setpoint"), _evidence(ctx, "drive_command"),
                          _evidence(ctx, "belt_load")) if e is not None]
        return RuleHit(active=True, evidences=ev,
                       summary=f"Vazão {mf:.0f} kg/h contra setpoint {sp:.0f} kg/h (desvio {dev:.1%})")


@dataclass
class KcmAlarm(Rule):
    """O controlador declarou um código.

    A leitura do código passa pelo catálogo de CHAVE COMPOSTA: o significado
    registrado vem sempre com aplicação, modelo, escopo e fonte. Código fora
    do catálogo é gravado como desconhecido, nunca adivinhado.
    """
    rule_id: str = "R-ALARM-001"
    version: str = "1.0"
    event_type: EventType = EventType.KCM_ALARM
    severity: Severity = Severity.ALARM
    description: str = "Código de alarme ativo no controlador"
    for_cycles: int = 1        # o controlador já declarou; não cabe debounce nosso
    clear_cycles: int = 2

    def evaluate(self, ctx: RuleContext) -> RuleHit:
        code = _num(ctx, "alarm_code")
        if code is None or int(code) == 0:
            return RuleHit(active=False)
        definition = alarms.lookup(int(code), ctx.application, ctx.controller_model)
        ev = [e for e in (_evidence(ctx, "alarm_code", definition.name),
                          _evidence(ctx, "machine_state"), _evidence(ctx, "drive_command"),
                          _evidence(ctx, "rpm"), _evidence(ctx, "belt_load"),
                          _evidence(ctx, "mass_flow")) if e is not None]
        return RuleHit(
            active=True, evidences=ev, severity=definition.severity,
            summary=f"Alarme {int(code)} — {definition.name}",
            extra={"alarm": {"code": int(code), "key": str(definition.key), "name": definition.name,
                             "meaning": definition.meaning, "evidence_level": definition.evidence.value,
                             "scope": definition.scope, "source": definition.source,
                             "observed_on": definition.observed_on,
                             "reverse_warning": definition.reverse_warning,
                             "universal": definition.universal}})


@dataclass
class SftNotResponding(Rule):
    rule_id: str = "R-SFT-001"
    version: str = "1.0"
    event_type: EventType = EventType.SFT_NOT_RESPONDING
    severity: Severity = Severity.ALARM
    description: str = "Lista de SFTs sem o endereço esperado"
    for_cycles: int = 2
    params: dict[str, Any] = field(default_factory=lambda: {"expected": "1"})

    def evaluate(self, ctx: RuleContext) -> RuleHit:
        lst = _txt(ctx, "sft_list")
        if lst is None:
            return RuleHit(active=False)
        if self.params["expected"] in lst:
            return RuleHit(active=False)
        ev = [e for e in (_evidence(ctx, "sft_list", f"esperado conter '{self.params['expected']}'"),
                          _evidence(ctx, "sft_status", "status cru, não decodificado"),
                          _evidence(ctx, "alarm_code"), _evidence(ctx, "net_weight")) if e is not None]
        return RuleHit(active=True, evidences=ev,
                       summary=f"Lista de SFTs em '{lst}'; endereço esperado ausente")


@dataclass
class IntChannelDegraded(Rule):
    rule_id: str = "R-INT-001"
    version: str = "1.0"
    event_type: EventType = EventType.INT_CHANNEL_DEGRADED
    severity: Severity = Severity.WARNING
    description: str = "INT CHANNEL-% abaixo do limiar"
    for_cycles: int = 3
    params: dict[str, Any] = field(default_factory=lambda: {"threshold_pct": 80.0})

    def evaluate(self, ctx: RuleContext) -> RuleHit:
        v = _num(ctx, "int_channel_pct")
        if v is None or v >= self.params["threshold_pct"]:
            return RuleHit(active=False)
        ev = [e for e in (_evidence(ctx, "int_channel_pct"), _evidence(ctx, "kcm_temp"),
                          _evidence(ctx, "sft_status")) if e is not None]
        return RuleHit(active=True, evidences=ev,
                       summary=f"INT CHANNEL em {v:.1f} % (limiar {self.params['threshold_pct']:.0f} %)")


@dataclass
class MachineStopped(Rule):
    """Máquina parada.

    STOP NÃO É FALHA POR PADRÃO. A severidade sai da classificação do STOP BY:
    parada normal ou solicitada é INFO; proteção é WARNING; falha é ALARM.
    """
    rule_id: str = "R-STOP-001"
    version: str = "1.0"
    event_type: EventType = EventType.MACHINE_STOPPED
    severity: Severity = Severity.INFO
    description: str = "Máquina em STOP, com o motivo classificado"
    for_cycles: int = 2
    clear_cycles: int = 2

    SEVERITY_BY_CLASS = {
        StopByClass.NORMAL: Severity.INFO,
        StopByClass.REQUESTED: Severity.INFO,
        StopByClass.PROTECTION: Severity.WARNING,
        StopByClass.FAULT: Severity.ALARM,
        StopByClass.UNKNOWN: Severity.WARNING,
    }

    def evaluate(self, ctx: RuleContext) -> RuleHit:
        state = _txt(ctx, "machine_state")
        if state != MachineState.STOP.value:
            return RuleHit(active=False)
        raw_stop_by = _txt(ctx, "stop_by") or ""
        klass = classify_stop_by(raw_stop_by)
        ev = [e for e in (_evidence(ctx, "machine_state"),
                          _evidence(ctx, "stop_by", f"classificado como {klass.value}"),
                          _evidence(ctx, "drive_command"), _evidence(ctx, "mass_flow"),
                          _evidence(ctx, "alarm_code")) if e is not None]
        motivo = raw_stop_by or "não informado"
        return RuleHit(
            active=True, evidences=ev, severity=self.SEVERITY_BY_CLASS[klass],
            summary=f"Máquina parada — STOP BY '{motivo}' ({klass.value})",
            extra={"stop_by": {"raw": raw_stop_by, "class": klass.value,
                               "is_fault": klass is StopByClass.FAULT,
                               "note": "parada classificada como não-falha" if klass in
                                       (StopByClass.NORMAL, StopByClass.REQUESTED) else ""}})


@dataclass
class CommunicationLoss(Rule):
    """A TENTATIVA de leitura está falhando. Fato de aquisição.

    Alimentado pelos ReadError do ciclo, não pela qualidade das amostras.
    É o par de DataStale, e os dois existem separados de propósito.
    """
    rule_id: str = "R-COMM-001"
    version: str = "1.0"
    event_type: EventType = EventType.COMMUNICATION_LOSS
    severity: Severity = Severity.CRITICAL
    description: str = "Falhas consecutivas na tentativa de leitura"
    for_cycles: int = 2
    clear_cycles: int = 2

    def evaluate(self, ctx: RuleContext) -> RuleHit:
        errors = ctx.cycle.read_errors
        if not errors:
            return RuleHit(active=False)
        worst = max(e.consecutive for e in errors)
        tags = sorted({e.tag for e in errors})
        first = errors[0]
        ev = [Evidence(tag="__acquisition__", label="Tentativas de leitura que falharam",
                       value=len(errors), ts=first.ts, quality=first.quality.value,
                       note=f"{worst} falha(s) consecutiva(s) na tag mais afetada"),
              Evidence(tag="__acquisition__", label="Erro devolvido pelo driver",
                       value=first.error, ts=first.ts, quality=first.quality.value),
              Evidence(tag="__acquisition__", label="Tags afetadas",
                       value=", ".join(tags[:12]), ts=first.ts, quality=first.quality.value)]
        return RuleHit(active=True, evidences=ev,
                       summary=f"{len(errors)} leitura(s) falharam neste ciclo; "
                               f"{worst} ciclo(s) consecutivo(s) sem resposta",
                       extra={"read_errors": {"count": len(errors), "max_consecutive": worst,
                                              "tags": tags, "error": first.error,
                                              "degraded": ctx.cycle.communication_degraded}})


@dataclass
class DataStale(Rule):
    """Os valores EXIBIDOS estão velhos. Fato de apresentação.

    Separado de CommunicationLoss porque responde a outra pergunta:
    não "a leitura falhou?", e sim "o número na tela é de quando?".
    """
    rule_id: str = "R-STALE-001"
    version: str = "1.0"
    event_type: EventType = EventType.DATA_STALE
    severity: Severity = Severity.WARNING
    description: str = "Valores exibidos mantidos de leitura anterior"
    for_cycles: int = 2
    clear_cycles: int = 1

    def evaluate(self, ctx: RuleContext) -> RuleHit:
        stale = [s for s in ctx.samples.values() if s.quality is Quality.STALE]
        if not stale:
            return RuleHit(active=False)
        oldest = max(stale, key=lambda s: s.age_s)
        ev = [Evidence(tag="__presentation__", label="Tags exibindo valor antigo",
                       value=len(stale), ts=ctx.now, quality=Quality.STALE.value),
              Evidence(tag=oldest.tag, label="Valor mais antigo em exibição",
                       value=oldest.value, ts=oldest.source_ts or oldest.ts,
                       quality=oldest.quality.value,
                       note=f"idade de {oldest.age_s:.1f} s")]
        return RuleHit(active=True, evidences=ev,
                       summary=f"{len(stale)} tag(s) exibindo valor mantido; "
                               f"o mais antigo tem {oldest.age_s:.1f} s",
                       extra={"stale": {"count": len(stale), "oldest_tag": oldest.tag,
                                        "oldest_age_s": round(oldest.age_s, 2),
                                        "tags": sorted(s.tag for s in stale)[:12]}})


def default_rules() -> list[Rule]:
    """Conjunto padrão, na ordem em que aparecem para o operador."""
    return [
        CommunicationLoss(), DataStale(), SpeedFeedbackAnomaly(), KcmAlarm(),
        SftNotResponding(), BeltLoadLow(), DriveCommandSaturated(), RateDeviation(),
        IntChannelDegraded(), MachineStopped(),
    ]
