"""RawFrame -> SampleBatch usando o mapping. Caminho unico para simulador e drivers reais.

Payload dict (simulador): valor ja em unidade de engenharia; escala NAO e aplicada.
Payload bytes/palavras (protocolo): recorte pelo layout do bloco, decode por datatype e
endianness do mapping, escala aplicada, bytes brutos preservados em `raw`.
Nunca interpola: tag sem valor vira COMM_ERROR com value None.
"""

from __future__ import annotations

import math
from collections.abc import Mapping as MappingABC
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from forja.domain.assets import EquipmentProfile
from forja.domain.evidence import UNKNOWN
from forja.domain.mapping import DataType, Endianness, Mapping, MappingEntry, Scale
from forja.domain.ports import Clock
from forja.domain.quality import Quality, worst
from forja.domain.samples import RawBlock, RawFrame, ReadBlock, ReadPlan, Sample, SampleBatch
from forja.normalization.decoder import bytes_to_words, decode, words_to_bytes
from forja.normalization.plan import ReadPlanCompiler, layout_of
from forja.normalization.quality_policy import QualityPolicy, Verdict

_PlanKey = tuple[str, str, str, int]
REASON_STRING_PT = "tipo string não representável como número; bruto preservado"
REASON_SCALE_UNKNOWN_PT = "escala UNKNOWN: valor sem conversão de engenharia"


@dataclass(frozen=True)
class _Ctx:
    """O que nao muda dentro de um quadro."""

    equipment_id: str
    driver: str
    source: str
    frame_ts_utc: datetime
    clock: Clock


class Normalizer:
    """Converte quadros brutos em amostras com qualidade. Cacheia o plano por mapping."""

    def __init__(
        self,
        policy: QualityPolicy | None = None,
        compiler: ReadPlanCompiler | None = None,
    ) -> None:
        self._policy = policy or QualityPolicy()
        self._compiler = compiler or ReadPlanCompiler()
        self._plans: dict[_PlanKey, ReadPlan] = {}

    def plan_for(self, profile: EquipmentProfile, mapping: Mapping) -> ReadPlan:
        """Plano compilado para (perfil, mapping), com cache por versao do mapping."""
        key: _PlanKey = (
            profile.id,
            profile.communication.driver,
            mapping.mapping_id,
            mapping.version,
        )
        plan = self._plans.get(key)
        if plan is None:
            plan = self._compiler.compile(profile, mapping)
            self._plans[key] = plan
        return plan

    def normalize(
        self,
        frame: RawFrame,
        profile: EquipmentProfile,
        mapping: Mapping,
        clock: Clock,
        plan: ReadPlan | None = None,
    ) -> SampleBatch:
        if frame.equipment_id != profile.id:
            raise ValueError(f"quadro de {frame.equipment_id!r} para perfil {profile.id!r}")
        plan = plan or self.plan_for(profile, mapping)
        ctx = _Ctx(
            equipment_id=profile.id,
            driver=profile.communication.driver,
            source=mapping.source_label,
            frame_ts_utc=frame.ts_utc,
            clock=clock,
        )
        samples: list[Sample] = []
        for block in plan.blocks:
            raw_block = frame.blocks.get(block.block_id)
            for tag in block.tags:
                entry = mapping.entry(tag)
                if entry is not None:
                    samples.append(self._sample(ctx, block, raw_block, entry))
        return SampleBatch(
            equipment_id=profile.id,
            ts_utc=frame.ts_utc,
            samples=tuple(samples),
            quality=worst([s.quality for s in samples]),
            latency_ms=frame.latency_ms,
        )

    # --- por tag ----------------------------------------------------------------------------

    def _sample(
        self, ctx: _Ctx, block: ReadBlock, raw_block: RawBlock | None, entry: MappingEntry
    ) -> Sample:
        if raw_block is None:
            return self._missing(ctx, entry)
        payload = raw_block.payload
        if isinstance(payload, MappingABC):
            return self._from_dict(ctx, raw_block, payload, entry)
        return self._from_wire(ctx, raw_block, block, payload, entry)

    def _missing(self, ctx: _Ctx, entry: MappingEntry) -> Sample:
        verdict = self._policy.for_missing()
        return Sample(
            ts_utc=ctx.frame_ts_utc,
            equipment_id=ctx.equipment_id,
            tag=entry.semantic_tag,
            value=None,
            quality=verdict.quality,
            source=ctx.source,
            ts_mono_ns=ctx.clock.monotonic_ns(),
            reason_pt=verdict.reason_pt,
        )

    def _from_dict(
        self,
        ctx: _Ctx,
        raw_block: RawBlock,
        payload: MappingABC[str, float | None],
        entry: MappingEntry,
    ) -> Sample:
        value = payload.get(entry.semantic_tag)
        if value is None:
            return _build(ctx, raw_block, entry, None, self._policy.for_missing(), None)
        number = float(value)
        verdict = self._policy.for_value(entry, ctx.driver, number)
        return _build(ctx, raw_block, entry, _finite_or_none(number), verdict, None)

    def _from_wire(
        self,
        ctx: _Ctx,
        raw_block: RawBlock,
        block: ReadBlock,
        payload: bytes | tuple[int, ...],
        entry: MappingEntry,
    ) -> Sample:
        slot = layout_of(block).get(entry.semantic_tag)
        if slot is None:
            verdict = self._policy.for_decode_error("tag sem layout no bloco")
            return _build(ctx, raw_block, entry, None, verdict, None)
        try:
            raw = _slice(payload, slot)
            decoded = _decode_entry(entry, raw, slot)
        except ValueError as exc:
            return _build(
                ctx, raw_block, entry, None, self._policy.for_decode_error(str(exc)), None
            )
        if isinstance(decoded, bytes):
            return _build(ctx, raw_block, entry, None, Verdict(Quality.BAD, REASON_STRING_PT), raw)
        number = _scaled(entry, float(decoded))
        verdict = self._policy.for_value(entry, ctx.driver, number)
        if entry.scale == UNKNOWN and verdict.reason_pt is None:
            verdict = Verdict(verdict.quality, REASON_SCALE_UNKNOWN_PT)
        return _build(ctx, raw_block, entry, _finite_or_none(number), verdict, raw)


def _build(
    ctx: _Ctx,
    raw_block: RawBlock,
    entry: MappingEntry,
    value: float | None,
    verdict: Verdict,
    raw: bytes | None,
) -> Sample:
    return Sample(
        ts_utc=raw_block.ts_utc,
        equipment_id=ctx.equipment_id,
        tag=entry.semantic_tag,
        value=value,
        quality=verdict.quality,
        source=ctx.source,
        raw=raw,
        ts_mono_ns=raw_block.ts_mono_ns,
        reason_pt=verdict.reason_pt,
    )


def _finite_or_none(number: float) -> float | None:
    return number if math.isfinite(number) else None


def _slice(payload: bytes | tuple[int, ...], slot: dict[str, Any]) -> bytes:
    """Recorta os bytes de uma tag do payload conforme o layout {offset, count, unit}."""
    offset = int(slot["offset"])
    count = int(slot["count"])
    unit = str(slot.get("unit", "word"))
    if unit == "word":
        words = bytes_to_words(payload) if isinstance(payload, bytes) else tuple(payload)
        chunk = words[offset : offset + count]
        if len(chunk) != count:
            raise ValueError(f"bloco curto: faltam palavras para offset {offset} count {count}")
        return words_to_bytes(chunk)
    if unit == "byte":
        data = payload if isinstance(payload, bytes) else words_to_bytes(payload)
        chunk_b = data[offset : offset + count]
        if len(chunk_b) != count:
            raise ValueError(f"bloco curto: faltam bytes para offset {offset} count {count}")
        return chunk_b
    if unit == "bit":
        return _slice_bits(payload, offset, count)
    raise ValueError(f"unidade de layout desconhecida: {unit!r}")


def _slice_bits(payload: bytes | tuple[int, ...], offset: int, count: int) -> bytes:
    """Coils/discretes: tupla com um inteiro por bit, ou bytes com bits LSB-first (Modbus)."""
    if count != 1:
        raise ValueError("leitura de bits suporta count=1 por tag")
    if isinstance(payload, bytes):
        byte_i, bit_i = divmod(offset, 8)
        if byte_i >= len(payload):
            raise ValueError(f"bloco curto: bit {offset} fora dos {len(payload)} bytes")
        bit = (payload[byte_i] >> bit_i) & 1
    else:
        if offset >= len(payload):
            raise ValueError(f"bloco curto: bit {offset} fora de {len(payload)} bits")
        bit = 1 if payload[offset] else 0
    return bit.to_bytes(2, "big")


def _decode_entry(
    entry: MappingEntry, raw: bytes, slot: dict[str, Any]
) -> float | int | bool | bytes:
    if not isinstance(entry.datatype, DataType):
        raise ValueError(f"datatype UNKNOWN no mapping ({entry.datatype!r})")
    if slot.get("unit") == "bit":
        return decode(raw, DataType.BOOL, Endianness.BIG)
    if not isinstance(entry.endianness, Endianness):
        raise ValueError("ordem de bytes UNKNOWN no mapping")
    return decode(raw, entry.datatype, entry.endianness)


def _scaled(entry: MappingEntry, number: float) -> float:
    if isinstance(entry.scale, Scale):
        return entry.scale.apply(number)
    return number


def comm_error_batch(
    profile: EquipmentProfile, mapping: Mapping, clock: Clock, reason_pt: str
) -> SampleBatch:
    """Lote inteiro COMM_ERROR (value None) para quando read() falha. Usado pela aquisicao."""
    ts_utc = clock.now_utc()
    mono = clock.monotonic_ns()
    source = mapping.source_label
    samples = tuple(
        Sample(
            ts_utc=ts_utc,
            equipment_id=profile.id,
            tag=e.semantic_tag,
            value=None,
            quality=Quality.COMM_ERROR,
            source=source,
            ts_mono_ns=mono,
            reason_pt=reason_pt,
        )
        for e in mapping.readable_entries
    )
    return SampleBatch(
        equipment_id=profile.id,
        ts_utc=ts_utc,
        samples=samples,
        quality=Quality.COMM_ERROR,
        latency_ms=None,
    )
