"""Amostras, quadros brutos e snapshot ao vivo (spec §23; Documento Mestre §16).

Sample minimo: timestamp, equipment_id, tag, value, quality, source.
plant/area/line nao se repetem por amostra: vem do perfil pelo equipment_id.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from forja.domain.quality import Quality


def utcnow() -> datetime:
    return datetime.now(UTC)


class Sample(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ts_utc: datetime
    equipment_id: str
    tag: str
    value: float | None
    quality: Quality
    source: str
    """driver:<nome>:<mapping_id>@<versao> ou sim:<cenario>."""
    raw: bytes | None = None
    """Bytes exatamente como vieram do driver, antes de escala e endianness."""
    ts_mono_ns: int | None = None
    reason_pt: str | None = None
    """Para COMM_ERROR/BAD: motivo curto em portugues."""


class SampleBatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    equipment_id: str
    ts_utc: datetime
    samples: tuple[Sample, ...]
    quality: Quality
    """Pior qualidade do lote."""
    latency_ms: float | None = None


class ReadBlock(BaseModel):
    """Um bloco contiguo a ler no dispositivo. Enderecos vem do mapping, nunca do codigo."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    block_id: str
    area: str
    address: int | str
    count: int
    tags: tuple[str, ...]
    meta: dict[str, Any] = Field(default_factory=dict)


class ReadPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    equipment_id: str
    mapping_id: str
    mapping_version: int
    blocks: tuple[ReadBlock, ...]

    @property
    def tags(self) -> tuple[str, ...]:
        out: list[str] = []
        for b in self.blocks:
            out.extend(b.tags)
        return tuple(dict.fromkeys(out))


class RawBlock(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    block_id: str
    payload: bytes | tuple[int, ...] | dict[str, float | None]
    """bytes (Modbus/EIP) ou dict tag->valor (simulador, que ja entrega valor pronto)."""
    ts_utc: datetime
    ts_mono_ns: int | None = None
    latency_ms: float | None = None


class RawFrame(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    equipment_id: str
    ts_utc: datetime
    blocks: dict[str, RawBlock]
    latency_ms: float | None = None
