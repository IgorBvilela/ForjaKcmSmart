"""Estado de conexao por equipamento e estagios do teste somente leitura (spec §16, §61)."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict

from forja.domain.ports import DriverSupportState


class ConnectionState(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    HANDSHAKE = "HANDSHAKE"
    CONNECTED = "CONNECTED"
    ERROR = "ERROR"
    RECONNECTING = "RECONNECTING"
    NOT_CONFIGURED = "NOT_CONFIGURED"

    @property
    def label_pt(self) -> str:
        return {
            ConnectionState.DISCONNECTED: "Desconectado",
            ConnectionState.CONNECTING: "Conectando",
            ConnectionState.HANDSHAKE: "Handshake",
            ConnectionState.CONNECTED: "Conectado",
            ConnectionState.ERROR: "Erro de comunicação",
            ConnectionState.RECONNECTING: "Reconectando",
            ConnectionState.NOT_CONFIGURED: "Não configurado",
        }[self]


class ReadTestStage(str, Enum):
    """Estados do botao TESTAR SOMENTE LEITURA (spec §16, passo 4)."""

    CONNECTING = "CONNECTING"
    HANDSHAKE = "HANDSHAKE"
    SESSION_CREATED = "SESSION_CREATED"
    READ_OBTAINED = "READ_OBTAINED"
    TIMEOUT = "TIMEOUT"
    CONNECTION_REFUSED = "CONNECTION_REFUSED"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    UNIDENTIFIED = "UNIDENTIFIED"

    @property
    def label_pt(self) -> str:
        return {
            ReadTestStage.CONNECTING: "Conectando",
            ReadTestStage.HANDSHAKE: "Handshake",
            ReadTestStage.SESSION_CREATED: "Sessão criada",
            ReadTestStage.READ_OBTAINED: "Leitura obtida",
            ReadTestStage.TIMEOUT: "Timeout",
            ReadTestStage.CONNECTION_REFUSED: "Conexão recusada",
            ReadTestStage.INVALID_RESPONSE: "Resposta inválida",
            ReadTestStage.UNIDENTIFIED: "Não identificado",
        }[self]

    @property
    def is_success(self) -> bool:
        return self == ReadTestStage.READ_OBTAINED


class EquipmentRuntimeStatus(BaseModel):
    """Foto do estado de um equipamento para a UI e o health."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    equipment_id: str
    driver: str
    support_state: DriverSupportState
    connection: ConnectionState
    last_read_utc: datetime | None = None
    last_ok_utc: datetime | None = None
    latency_ms: float | None = None
    consecutive_errors: int = 0
    reconnect_count: int = 0
    restart_count: int = 0
    samples_per_min: float = 0.0
    is_stale: bool = False
    stale_for_s: float | None = None
    detail_pt: str = ""
