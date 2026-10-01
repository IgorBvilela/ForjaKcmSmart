"""Estado mutável de runtime por equipamento e vocabulário de falhas de aquisição.

O estado vive no EquipmentManager, fora da task do loop: assim ele sobrevive a um restart
do watchdog e a um reload de perfil. A task só escreve nele.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from forja.domain import (
    ConfigError,
    ConnectionState,
    DriverConnectError,
    DriverReadError,
    DriverSupportState,
    DriverTimeout,
    EquipmentRuntimeStatus,
    UnsupportedDriver,
)

SAMPLES_WINDOW_S = 60.0
"""Janela, em segundos, usada para calcular samples_per_min."""

NEEDS_FIELD_CONFIG_PT = "Disponível após configuração de campo"


class ConnectionChanged(BaseModel):
    """Payload publicado em TOPIC_CONNECTION a cada mudança de estado de conexão."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    equipment_id: str
    previous: ConnectionState
    current: ConnectionState
    ts_utc: datetime
    detail_pt: str = ""
    consecutive_errors: int = 0
    reconnect_count: int = 0


@dataclass
class EquipmentState:
    """Contadores e última situação conhecida de um equipamento."""

    equipment_id: str
    driver: str
    support_state: DriverSupportState = DriverSupportState.NEEDS_CONFIGURATION
    connection: ConnectionState = ConnectionState.DISCONNECTED
    last_read_utc: datetime | None = None
    last_ok_utc: datetime | None = None
    latency_ms: float | None = None
    consecutive_errors: int = 0
    reconnect_count: int = 0
    restart_count: int = 0
    historian_errors: int = 0
    detail_pt: str = ""
    last_tick_mono_ns: int | None = None
    ok_ticks_mono_ns: deque[int] = field(default_factory=deque)

    def tick(self, mono_ns: int) -> None:
        """Marca que o loop está vivo. O watchdog lê isto."""
        self.last_tick_mono_ns = mono_ns

    def record_ok(self, mono_ns: int) -> None:
        """Registra uma leitura bem-sucedida para a taxa por minuto."""
        self.ok_ticks_mono_ns.append(mono_ns)
        self._prune(mono_ns)

    def samples_per_min(self, now_mono_ns: int) -> float:
        """Leituras bem-sucedidas nos últimos 60 s."""
        self._prune(now_mono_ns)
        return float(len(self.ok_ticks_mono_ns))

    def _prune(self, now_mono_ns: int) -> None:
        limit = now_mono_ns - int(SAMPLES_WINDOW_S * 1_000_000_000)
        while self.ok_ticks_mono_ns and self.ok_ticks_mono_ns[0] < limit:
            self.ok_ticks_mono_ns.popleft()

    def to_status(
        self,
        *,
        now_mono_ns: int,
        is_stale: bool = False,
        stale_for_s: float | None = None,
    ) -> EquipmentRuntimeStatus:
        """Foto imutável para a UI e o health."""
        return EquipmentRuntimeStatus(
            equipment_id=self.equipment_id,
            driver=self.driver,
            support_state=self.support_state,
            connection=self.connection,
            last_read_utc=self.last_read_utc,
            last_ok_utc=self.last_ok_utc,
            latency_ms=self.latency_ms,
            consecutive_errors=self.consecutive_errors,
            reconnect_count=self.reconnect_count,
            restart_count=self.restart_count,
            samples_per_min=self.samples_per_min(now_mono_ns),
            is_stale=is_stale,
            stale_for_s=stale_for_s,
            detail_pt=self.detail_pt,
        )


def reason_pt_for(exc: BaseException) -> str:
    """Motivo curto, em português, para COMM_ERROR. Nome da exceção fica fora do texto."""
    if isinstance(exc, DriverTimeout):
        return "Tempo esgotado aguardando resposta do equipamento"
    if isinstance(exc, DriverConnectError):
        return "Não foi possível conectar ao equipamento"
    if isinstance(exc, DriverReadError):
        return "Falha na leitura do equipamento"
    if isinstance(exc, UnsupportedDriver):
        return "Driver não disponível para este equipamento"
    if isinstance(exc, ConfigError):
        return "Configuração inválida do equipamento (perfil ou mapping)"
    if isinstance(exc, ValueError):
        return "Resposta inválida do equipamento"
    return "Erro inesperado na comunicação"
