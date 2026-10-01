"""Vocabulário do motor de eventos.

Um EVENTO é uma condição reconhecida por uma regra determinística, com
início, fim e contexto capturado. Não é o alarme do KCM: o alarme do
controlador vira um evento do tipo KCM_ALARM, mas a maioria dos eventos
é reconhecida por nós a partir do comportamento das tags.

Separação que o produto mantém:
    alarme do KCM   -> o que a máquina declarou (dado bruto do controlador)
    evento da Forja -> o que nós reconhecemos (regra nossa, versionada)
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from forja.domain.models import utcnow


class Severity(str, Enum):
    INFO = "INFO"            # registro; não exige ação
    WARNING = "WARNING"      # merece olhar; produção segue
    ALARM = "ALARM"          # exige ação; produção comprometida
    CRITICAL = "CRITICAL"    # parada ou risco de dano


SEVERITY_ORDER = {Severity.INFO: 0, Severity.WARNING: 1, Severity.ALARM: 2, Severity.CRITICAL: 3}


class EventType(str, Enum):
    """Condições que o motor reconhece. Nomes descrevem o SINTOMA observado,
    nunca a causa — a causa é trabalho da biblioteca de diagnóstico."""

    SPEED_FEEDBACK_ANOMALY = "SPEED_FEEDBACK_ANOMALY"
    """Motor comandado e realimentação de velocidade em zero.
    Sintoma, não causa: pode ser encoder, cabo, interface, entrada ou parâmetro."""

    BELT_LOAD_LOW = "BELT_LOAD_LOW"
    """Carga na correia abaixo da referência esperada (aplicação WBF)."""

    DRIVE_COMMAND_SATURATED = "DRIVE_COMMAND_SATURATED"
    """Drive Command encostado no teto por tempo sustentado."""

    RATE_DEVIATION = "RATE_DEVIATION"
    """Vazão fora da faixa do setpoint por tempo sustentado."""

    KCM_ALARM = "KCM_ALARM"
    """O controlador declarou um código de alarme."""

    SFT_NOT_RESPONDING = "SFT_NOT_RESPONDING"
    """A lista de SFTs deixou de mostrar o endereço esperado."""

    INT_CHANNEL_DEGRADED = "INT_CHANNEL_DEGRADED"
    """INT CHANNEL-% abaixo do limiar configurado."""

    MACHINE_STOPPED = "MACHINE_STOPPED"
    """Máquina em STOP. A classificação do STOP BY vai no contexto —
    parada normal NÃO é falha."""

    COMMUNICATION_LOSS = "COMMUNICATION_LOSS"
    """As tentativas de leitura estão falhando (fato de aquisição)."""

    DATA_STALE = "DATA_STALE"
    """Os valores exibidos estão velhos (fato de apresentação).
    Distinto de COMMUNICATION_LOSS de propósito: um diz que a leitura falha,
    o outro diz que o número na tela não é de agora."""


class EventStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class Evidence(BaseModel):
    """Um fato observado que sustenta o evento. Sempre com valor e instante."""
    tag: str
    label: str
    value: Any
    unit: str = ""
    ts: Optional[datetime] = None
    quality: str = ""
    note: str = ""


class Event(BaseModel):
    """Condição reconhecida. `context` carrega o antes e o durante."""
    id: Optional[int] = None
    equipment_id: str
    type: EventType
    severity: Severity
    ts_start: datetime = Field(default_factory=utcnow)
    ts_end: Optional[datetime] = None
    rule_id: str = ""
    rule_version: str = ""
    status: EventStatus = EventStatus.OPEN
    summary: str = ""
    context: dict[str, Any] = Field(default_factory=dict)

    @property
    def duration_s(self) -> Optional[float]:
        if self.ts_end is None:
            return None
        return (self.ts_end - self.ts_start).total_seconds()

    def to_row(self) -> dict:
        return {"equipment_id": self.equipment_id, "type_": self.type.value,
                "severity": self.severity.value, "ts_start": self.ts_start,
                "ts_end": self.ts_end, "rule_id": self.rule_id,
                "rule_version": self.rule_version, "context": self.context}
