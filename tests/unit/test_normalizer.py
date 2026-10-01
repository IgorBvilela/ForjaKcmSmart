"""Normalizer, comm_error_batch e ReadPlanCompiler: qualidade por entrada, GAP, planos."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from forja.domain import (
    UNKNOWN,
    DataType,
    Endianness,
    EquipmentProfile,
    KnowledgeState,
    Mapping,
    MappingEntry,
    MappingValidationError,
    Quality,
    RawBlock,
    RawFrame,
    Sample,
    SampleBatch,
    Scale,
    Validation,
)
from forja.drivers.simulator import SimulatorControlRegistry, SimulatorDriver
from forja.infra.clock import FakeClock
from forja.normalization import (
    REASON_NO_READ_PT,
    Normalizer,
    ReadPlanCompiler,
    comm_error_batch,
    encode,
    layout_of,
)
from tests.unit.block1_helpers import load_sim_mapping, sim_profile

pytestmark = pytest.mark.unit


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def mapping() -> Mapping:
    return load_sim_mapping()


@pytest.fixture
def profile() -> EquipmentProfile:
    return sim_profile()


def _by_tag(batch: SampleBatch) -> dict[str, Sample]:
    return {s.tag: s for s in batch.samples}


def _sim_frame(
    profile: EquipmentProfile, clock: FakeClock, payload: dict[str, float | None] | None
) -> RawFrame:
    """Quadro do simulador montado a mao. payload None = bloco ausente."""
    blocks = {}
    if payload is not None:
        blocks["sim"] = RawBlock(
            block_id="sim",
            payload=payload,
            ts_utc=clock.now_utc(),
            ts_mono_ns=clock.monotonic_ns(),
            latency_ms=1.0,
        )
    return RawFrame(equipment_id=profile.id, ts_utc=clock.now_utc(), blocks=blocks, latency_ms=1.0)


def _with_entry(mapping: Mapping, tag: str, **changes: object) -> Mapping:
    entries = [
        e.model_copy(update=changes) if e.semantic_tag == tag else e for e in mapping.entries
    ]
    return mapping.model_copy(update={"entries": entries})


async def _real_sim_frame(
    profile: EquipmentProfile, mapping: Mapping, clock: FakeClock
) -> RawFrame:
    driver = SimulatorDriver(profile, mapping, clock, controls=SimulatorControlRegistry())
    await driver.connect()
    return await driver.read(ReadPlanCompiler().compile(profile, mapping))


# --- simulador: SIMULATED, BAD, COMM_ERROR ---------------------------------------------------


async def test_simulator_frame_is_all_simulated(profile, mapping, clock) -> None:
    frame = await _real_sim_frame(profile, mapping, clock)
    batch = Normalizer().normalize(frame, profile, mapping, clock)
    assert batch.equipment_id == profile.id
    assert batch.ts_utc == frame.ts_utc
    assert batch.latency_ms == frame.latency_ms
    assert len(batch.samples) == 14
    assert batch.quality is Quality.SIMULATED
    for s in batch.samples:
        assert s.quality is Quality.SIMULATED
        assert isinstance(s.value, float)
        assert s.reason_pt is None
        assert s.source == mapping.source_label == "driver:simulator:simulator_wbf@1"
        assert s.equipment_id == profile.id
        assert s.ts_mono_ns == clock.monotonic_ns()
        assert s.raw is None  # payload dict: nao ha bytes de fio


async def test_value_outside_valid_range_is_bad_with_reason(profile, mapping, clock) -> None:
    mapping = _with_entry(mapping, "belt_load", valid_max=0.5)
    mapping = _with_entry(mapping, "rpm", valid_min=1000.0)
    frame = await _real_sim_frame(profile, mapping, clock)
    by_tag = _by_tag(Normalizer().normalize(frame, profile, mapping, clock))
    assert by_tag["belt_load"].quality is Quality.BAD
    assert by_tag["belt_load"].value is not None
    assert by_tag["belt_load"].value > 0.5  # valor preservado, so a qualidade muda
    assert "acima do máximo válido" in (by_tag["belt_load"].reason_pt or "")
    assert by_tag["rpm"].quality is Quality.BAD
    assert "abaixo do mínimo válido" in (by_tag["rpm"].reason_pt or "")
    assert by_tag["mass_flow"].quality is Quality.SIMULATED


async def test_value_inside_valid_range_keeps_quality(profile, mapping, clock) -> None:
    mapping = _with_entry(mapping, "mass_flow", valid_min=0.0, valid_max=5000.0)
    frame = await _real_sim_frame(profile, mapping, clock)
    by_tag = _by_tag(Normalizer().normalize(frame, profile, mapping, clock))
    assert by_tag["mass_flow"].quality is Quality.SIMULATED
    assert by_tag["mass_flow"].reason_pt is None


def test_tag_in_plan_missing_from_frame_is_comm_error(profile, mapping, clock) -> None:
    payload = {e.semantic_tag: 1.0 for e in mapping.readable_entries if e.semantic_tag != "rpm"}
    batch = Normalizer().normalize(_sim_frame(profile, clock, payload), profile, mapping, clock)
    by_tag = _by_tag(batch)
    assert by_tag["rpm"].quality is Quality.COMM_ERROR
    assert by_tag["rpm"].value is None
    assert by_tag["rpm"].reason_pt == REASON_NO_READ_PT == "sem leitura"
    assert by_tag["mass_flow"].quality is Quality.SIMULATED
    assert batch.quality is Quality.COMM_ERROR  # pior do lote


def test_none_value_in_payload_is_comm_error(profile, mapping, clock) -> None:
    payload: dict[str, float | None] = {e.semantic_tag: 1.0 for e in mapping.readable_entries}
    payload["rpm"] = None
    by_tag = _by_tag(
        Normalizer().normalize(_sim_frame(profile, clock, payload), profile, mapping, clock)
    )
    assert by_tag["rpm"].quality is Quality.COMM_ERROR
    assert by_tag["rpm"].value is None


def test_missing_block_makes_every_tag_comm_error(profile, mapping, clock) -> None:
    batch = Normalizer().normalize(_sim_frame(profile, clock, None), profile, mapping, clock)
    assert len(batch.samples) == 14
    assert batch.quality is Quality.COMM_ERROR
    for s in batch.samples:
        assert s.quality is Quality.COMM_ERROR
        assert s.value is None
        assert s.reason_pt == REASON_NO_READ_PT
        assert s.ts_mono_ns == clock.monotonic_ns()


def test_nan_value_is_bad_not_numeric(profile, mapping, clock) -> None:
    payload: dict[str, float | None] = {e.semantic_tag: 1.0 for e in mapping.readable_entries}
    payload["mass_flow"] = float("nan")
    by_tag = _by_tag(
        Normalizer().normalize(_sim_frame(profile, clock, payload), profile, mapping, clock)
    )
    assert by_tag["mass_flow"].quality is Quality.BAD
    assert by_tag["mass_flow"].value is None
    assert "não numérico" in (by_tag["mass_flow"].reason_pt or "")


def test_frame_of_other_equipment_is_rejected(profile, mapping, clock) -> None:
    other = sim_profile("SIM_TESTE_02")
    frame = _sim_frame(other, clock, {})
    with pytest.raises(ValueError, match="quadro de"):
        Normalizer().normalize(frame, profile, mapping, clock)


def test_comm_error_batch_covers_all_readable_entries(profile, mapping, clock) -> None:
    clock.advance(12.5)
    batch = comm_error_batch(profile, mapping, clock, "Tempo esgotado (teste)")
    assert batch.equipment_id == profile.id
    assert batch.ts_utc == clock.now_utc()
    assert batch.quality is Quality.COMM_ERROR
    assert batch.latency_ms is None
    assert {s.tag for s in batch.samples} == {e.semantic_tag for e in mapping.readable_entries}
    for s in batch.samples:
        assert s.quality is Quality.COMM_ERROR
        assert s.value is None
        assert s.reason_pt == "Tempo esgotado (teste)"
        assert s.ts_mono_ns == clock.monotonic_ns()
        assert s.source == mapping.source_label


def test_unknown_entries_never_enter_plan_or_comm_error_batch(profile, mapping, clock) -> None:
    mapping = _with_entry(mapping, "rpm", protocol_address=UNKNOWN)
    plan = ReadPlanCompiler().compile(profile, mapping)
    assert "rpm" not in plan.tags
    assert len(plan.tags) == 13
    assert "rpm" not in {s.tag for s in comm_error_batch(profile, mapping, clock, "x").samples}


async def test_stale_is_never_produced_by_normalization(profile, mapping, clock) -> None:
    frames = [
        await _real_sim_frame(profile, mapping, clock),
        _sim_frame(profile, clock, None),
        _sim_frame(profile, clock, {"rpm": None, "mass_flow": float("inf")}),
    ]
    seen: set[Quality] = set()
    for frame in frames:
        seen |= {s.quality for s in Normalizer().normalize(frame, profile, mapping, clock).samples}
    seen |= {s.quality for s in comm_error_batch(profile, mapping, clock, "x").samples}
    assert Quality.STALE not in seen
    assert Quality.GOOD not in seen  # simulador nunca e GOOD


def test_plan_is_cached_per_mapping_version(profile, mapping) -> None:
    normalizer = Normalizer()
    plan_a = normalizer.plan_for(profile, mapping)
    assert normalizer.plan_for(profile, mapping) is plan_a
    bumped = mapping.model_copy(update={"version": 2})
    plan_b = normalizer.plan_for(profile, bumped)
    assert plan_b is not plan_a
    assert plan_b.mapping_version == 2


# --- caminho de fio (Modbus/EIP): decode, escala, raw ---------------------------------------

MB_ID = "MB_TESTE_01"


def _mb_profile(**communication: object) -> EquipmentProfile:
    return sim_profile(MB_ID, driver="modbus_tcp", mapping_profile="mb_teste", **communication)


def _mb_entry(
    tag: str, address: int, datatype: DataType, count: int | None = None, **kw
) -> MappingEntry:
    return MappingEntry(
        semantic_tag=tag,
        protocol_address={
            "area": "holding",
            "address": address,
            "count": count or datatype.word_count,
        },
        datatype=datatype,
        endianness=kw.pop("endianness", Endianness.BIG),
        scale=kw.pop("scale", Scale()),
        source="teste de unidade",
        evidence=KnowledgeState.FORJA_RULE,
        **kw,
    )


def _mb_mapping(*entries: MappingEntry, **kw: object) -> Mapping:
    return Mapping(
        mapping_id="mb_teste",
        equipment_id=MB_ID,
        driver="modbus_tcp",
        source="teste",
        entries=list(entries),
        **kw,
    )


def _wire_frame(profile: EquipmentProfile, clock: FakeClock, blocks: dict[str, object]) -> RawFrame:
    return RawFrame(
        equipment_id=profile.id,
        ts_utc=clock.now_utc(),
        blocks={
            block_id: RawBlock(
                block_id=block_id,
                payload=payload,
                ts_utc=clock.now_utc(),
                ts_mono_ns=clock.monotonic_ns(),
            )
            for block_id, payload in blocks.items()
        },
    )


def test_wire_payload_is_decoded_scaled_and_raw_preserved(clock) -> None:
    profile = _mb_profile()
    mapping = _mb_mapping(
        _mb_entry("mass_flow", 0, DataType.FLOAT32, valid_min=0.0, valid_max=5000.0),
        _mb_entry("rpm", 2, DataType.UINT16, scale=Scale(factor=0.1)),
        MappingEntry(
            semantic_tag="alarm_active",
            protocol_address={"area": "coil", "address": 0, "count": 1},
            datatype=DataType.BOOL,
            endianness=Endianness.BIG,
            scale=Scale(),
            source="teste",
        ),
    )
    plan = ReadPlanCompiler().compile(profile, mapping)
    assert [b.block_id for b in plan.blocks] == ["holding:0:3", "coil:0:1"]
    flow_bytes = encode(1234.5, DataType.FLOAT32, Endianness.BIG)
    rpm_bytes = encode(425, DataType.UINT16, Endianness.BIG)
    raw = flow_bytes + rpm_bytes
    words = tuple(int.from_bytes(raw[i : i + 2], "big") for i in range(0, 6, 2))
    frame = _wire_frame(profile, clock, {"holding:0:3": words, "coil:0:1": (1,)})
    by_tag = _by_tag(Normalizer().normalize(frame, profile, mapping, clock, plan=plan))
    assert by_tag["mass_flow"].value == 1234.5
    assert by_tag["mass_flow"].raw == flow_bytes
    assert by_tag["mass_flow"].quality is Quality.UNCERTAIN  # nao confirmado
    assert by_tag["rpm"].value == pytest.approx(42.5)
    assert by_tag["rpm"].raw == rpm_bytes
    assert by_tag["alarm_active"].value == 1.0
    assert by_tag["alarm_active"].quality is Quality.UNCERTAIN
    # bytes em vez de palavras: mesmo resultado
    frame_b = _wire_frame(profile, clock, {"holding:0:3": raw, "coil:0:1": b"\x01"})
    by_tag_b = _by_tag(Normalizer().normalize(frame_b, profile, mapping, clock, plan=plan))
    assert by_tag_b["mass_flow"].value == 1234.5
    assert by_tag_b["rpm"].raw == rpm_bytes
    assert by_tag_b["alarm_active"].value == 1.0


def test_confirmed_entry_with_validation_is_good(clock) -> None:
    profile = _mb_profile()
    validation = Validation(
        validated_at_utc=datetime(2026, 1, 1, tzinfo=UTC),
        validated_by="teste",
        forja_value=1.0,
        kcm_value=1.0,
        matched=True,
    )
    mapping = _mb_mapping(
        _mb_entry("rpm", 0, DataType.UINT16, confirmed=True, validation=validation)
    )
    plan = ReadPlanCompiler().compile(profile, mapping)
    frame = _wire_frame(profile, clock, {plan.blocks[0].block_id: (55,)})
    by_tag = _by_tag(Normalizer().normalize(frame, profile, mapping, clock, plan=plan))
    assert by_tag["rpm"].quality is Quality.GOOD
    assert by_tag["rpm"].value == 55.0


def test_short_wire_block_is_bad_decode_error(clock) -> None:
    profile = _mb_profile()
    mapping = _mb_mapping(
        _mb_entry("mass_flow", 0, DataType.FLOAT32), _mb_entry("rpm", 2, DataType.UINT16)
    )
    plan = ReadPlanCompiler().compile(profile, mapping)
    frame = _wire_frame(profile, clock, {"holding:0:3": (0x3F80,)})
    batch = Normalizer().normalize(frame, profile, mapping, clock, plan=plan)
    assert batch.quality is Quality.BAD
    for s in batch.samples:
        assert s.quality is Quality.BAD
        assert s.value is None
        assert s.raw is None
        assert "decodificação falhou" in (s.reason_pt or "")


def test_unknown_scale_keeps_raw_number_and_explains(clock) -> None:
    profile = _mb_profile()
    mapping = _mb_mapping(_mb_entry("rpm", 0, DataType.UINT16, scale=UNKNOWN))
    plan = ReadPlanCompiler().compile(profile, mapping)
    frame = _wire_frame(profile, clock, {"holding:0:1": (425,)})
    by_tag = _by_tag(Normalizer().normalize(frame, profile, mapping, clock, plan=plan))
    assert by_tag["rpm"].value == 425.0
    assert by_tag["rpm"].quality is Quality.UNCERTAIN
    assert "escala UNKNOWN" in (by_tag["rpm"].reason_pt or "")


def test_string_datatype_is_bad_with_raw_preserved(clock) -> None:
    profile = _mb_profile()
    mapping = _mb_mapping(_mb_entry("sft_list", 0, DataType.STRING, count=2))
    plan = ReadPlanCompiler().compile(profile, mapping)
    frame = _wire_frame(profile, clock, {"holding:0:2": (0x4142, 0x4344)})
    by_tag = _by_tag(Normalizer().normalize(frame, profile, mapping, clock, plan=plan))
    assert by_tag["sft_list"].quality is Quality.BAD
    assert by_tag["sft_list"].value is None
    assert by_tag["sft_list"].raw == b"ABCD"


# --- ReadPlanCompiler -------------------------------------------------------------------------


def test_compiler_simulator_single_block_with_all_readable_entries(profile, mapping) -> None:
    plan = ReadPlanCompiler().compile(profile, mapping)
    assert plan.equipment_id == profile.id
    assert plan.mapping_id == "simulator_wbf"
    assert plan.mapping_version == 1
    assert len(plan.blocks) == 1
    block = plan.blocks[0]
    assert block.block_id == block.area == "sim"
    assert block.count == 14
    assert set(block.tags) == {e.semantic_tag for e in mapping.readable_entries}
    assert layout_of(block) == {}


def test_compiler_rejects_mapping_of_other_driver_or_equipment(profile, mapping) -> None:
    with pytest.raises(MappingValidationError, match="mapping é do driver"):
        ReadPlanCompiler().compile(profile, mapping.model_copy(update={"driver": "modbus_tcp"}))
    with pytest.raises(MappingValidationError, match="mapping é do equipamento"):
        ReadPlanCompiler().compile(profile, mapping.model_copy(update={"equipment_id": "OUTRO_01"}))


def test_compiler_rejects_simulator_address_that_does_not_match_tag(profile, mapping) -> None:
    broken = _with_entry(mapping, "rpm", protocol_address="sim:mass_flow")
    with pytest.raises(MappingValidationError, match="endereço do simulador"):
        ReadPlanCompiler().compile(profile, broken)


def test_compiler_modbus_coalesces_contiguous_and_splits_gaps() -> None:
    profile = _mb_profile()
    mapping = _mb_mapping(
        _mb_entry("rpm", 2, DataType.UINT16),
        _mb_entry("mass_flow", 0, DataType.FLOAT32),
        _mb_entry("belt_load", 10, DataType.FLOAT32),
    )
    plan = ReadPlanCompiler().compile(profile, mapping)
    assert [b.block_id for b in plan.blocks] == ["holding:0:3", "holding:10:2"]
    first = plan.blocks[0]
    assert first.tags == ("mass_flow", "rpm")
    assert layout_of(first) == {
        "mass_flow": {"offset": 0, "count": 2, "unit": "word"},
        "rpm": {"offset": 2, "count": 1, "unit": "word"},
    }
    assert plan.tags == ("mass_flow", "rpm", "belt_load")


def test_compiler_modbus_respects_max_block_size_from_profile() -> None:
    profile = _mb_profile(max_block_size=2)
    mapping = _mb_mapping(
        _mb_entry("mass_flow", 0, DataType.FLOAT32), _mb_entry("rpm", 2, DataType.UINT16)
    )
    plan = ReadPlanCompiler().compile(profile, mapping)
    assert [b.block_id for b in plan.blocks] == ["holding:0:2", "holding:2:1"]
    too_big = _mb_mapping(_mb_entry("net_weight", 0, DataType.FLOAT64))
    with pytest.raises(MappingValidationError, match="acima do limite"):
        ReadPlanCompiler().compile(profile, too_big)


def test_compiler_modbus_rejects_bad_address() -> None:
    profile = _mb_profile()
    bad = MappingEntry(
        semantic_tag="rpm",
        protocol_address={"area": "memoria", "address": 0},
        datatype=DataType.UINT16,
        endianness=Endianness.BIG,
        source="teste",
    )
    with pytest.raises(MappingValidationError, match="area Modbus"):
        ReadPlanCompiler().compile(profile, _mb_mapping(bad))


def test_compiler_eip_one_block_per_entry() -> None:
    profile = sim_profile("EIP_TESTE_01", driver="ethernet_ip", mapping_profile="eip_teste")
    entries = [
        MappingEntry(
            semantic_tag=tag,
            protocol_address={
                "kind": "assembly",
                "class": 4,
                "instance": 100,
                "offset": off,
                "length": 4,
            },
            datatype=DataType.FLOAT32,
            endianness=Endianness.LITTLE,
            source="teste",
        )
        for tag, off in (("mass_flow", 0), ("rpm", 4))
    ]
    mapping = Mapping(
        mapping_id="eip_teste",
        equipment_id=profile.id,
        driver="ethernet_ip",
        source="teste",
        entries=entries,
    )
    plan = ReadPlanCompiler().compile(profile, mapping)
    assert [b.block_id for b in plan.blocks] == ["eip:mass_flow", "eip:rpm"]
    assert all(len(b.tags) == 1 for b in plan.blocks)
    assert layout_of(plan.blocks[1]) == {"rpm": {"offset": 0, "count": 4, "unit": "byte"}}
    assert plan.blocks[1].meta["offset"] == 4
