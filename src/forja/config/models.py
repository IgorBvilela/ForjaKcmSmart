"""Modelo de config/forja.yaml."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class EdgeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = "Forja Edge"
    bind_host: str = "127.0.0.1"
    bind_port: int = Field(default=8765, ge=1024, le=65535)
    data_dir: str = "var"
    timezone: str = "America/Sao_Paulo"


class HistorianConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_retention_days: int = 30
    raw_simulated_retention_days: int = 7
    rollup_1m_retention_days: int = 180
    rollup_1h_retention_days: int | None = None
    flush_interval_s: float = 1.0
    store_on_change: bool = True
    forced_sample_every_s: int = 60
    max_points_per_query: int = 2000
    max_historian_gb: float = 20.0


class BackupConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auto: bool = True
    schedule: str = "02:00"
    keep_last: int = 14


class SecurityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_ttl_min: int = 480
    first_admin_setup: bool = True


class LoggingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: str = "INFO"
    rotate_mb: int = 20
    keep: int = 10


class RagProvider(str, Enum):
    NONE = "NONE"
    LOCAL = "LOCAL"
    CLOUD = "CLOUD"


class RagConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: RagProvider = RagProvider.NONE


class EventsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pre_window_s: int = 60
    post_window_s: int = 30
    buffer_s: int = 180


class ForjaConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    edge: EdgeConfig = Field(default_factory=EdgeConfig)
    historian: HistorianConfig = Field(default_factory=HistorianConfig)
    events: EventsConfig = Field(default_factory=EventsConfig)
    backup: BackupConfig = Field(default_factory=BackupConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    rag: RagConfig = Field(default_factory=RagConfig)
