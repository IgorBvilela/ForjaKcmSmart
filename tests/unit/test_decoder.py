"""decode/encode: round-trip por datatype x 4 endianness (hypothesis), vetores conhecidos, erros."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from forja.domain import DataType, Endianness
from forja.normalization import (
    bytes_to_words,
    decode,
    encode,
    expected_size_bytes,
    reorder,
    words_to_bytes,
)

pytestmark = pytest.mark.unit

ENDIANNESS = list(Endianness)
FIXED_TYPES = [dt for dt in DataType if dt is not DataType.STRING]

_STRATEGIES: dict[DataType, st.SearchStrategy[object]] = {
    DataType.INT16: st.integers(-(1 << 15), (1 << 15) - 1),
    DataType.UINT16: st.integers(0, (1 << 16) - 1),
    DataType.INT32: st.integers(-(1 << 31), (1 << 31) - 1),
    DataType.UINT32: st.integers(0, (1 << 32) - 1),
    DataType.BITFIELD16: st.integers(0, (1 << 16) - 1),
    DataType.BITFIELD32: st.integers(0, (1 << 32) - 1),
    DataType.FLOAT32: st.floats(width=32, allow_nan=False),
    DataType.FLOAT64: st.floats(width=64, allow_nan=False),
    DataType.BOOL: st.booleans(),
}

_EVEN_BYTES = st.binary(min_size=2, max_size=64).filter(lambda b: len(b) % 2 == 0)


def test_all_endianness_covered() -> None:
    assert len(ENDIANNESS) == 4
    assert set(_STRATEGIES) == set(FIXED_TYPES)


@pytest.mark.parametrize("endianness", ENDIANNESS)
@pytest.mark.parametrize("datatype", FIXED_TYPES)
@settings(max_examples=80, database=None, deadline=None)
@given(data=st.data())
def test_round_trip_datatype_x_endianness(
    datatype: DataType, endianness: Endianness, data: st.DataObject
) -> None:
    value = data.draw(_STRATEGIES[datatype])
    wire = encode(value, datatype, endianness)
    assert len(wire) == expected_size_bytes(datatype) == datatype.word_count * 2
    back = decode(wire, datatype, endianness)
    assert back == value
    assert decode(bytes_to_words(wire), datatype, endianness) == value
    if datatype is DataType.BOOL:
        assert isinstance(back, bool)
    elif datatype in (DataType.FLOAT32, DataType.FLOAT64):
        assert isinstance(back, float)
    else:
        assert type(back) is int
    assert encode(back, datatype, endianness) == wire


@pytest.mark.parametrize("endianness", ENDIANNESS)
@settings(max_examples=50, database=None, deadline=None)
@given(payload=_EVEN_BYTES)
def test_string_round_trip_returns_bytes(endianness: Endianness, payload: bytes) -> None:
    wire = encode(payload, DataType.STRING, endianness)
    back = decode(wire, DataType.STRING, endianness)
    assert back == payload
    assert isinstance(back, bytes)


@pytest.mark.parametrize("endianness", ENDIANNESS)
@settings(max_examples=50, database=None, deadline=None)
@given(payload=_EVEN_BYTES)
def test_reorder_is_an_involution(endianness: Endianness, payload: bytes) -> None:
    assert reorder(reorder(payload, endianness), endianness) == payload
    assert len(reorder(payload, endianness)) == len(payload)


def test_known_float32_vectors_per_endianness() -> None:
    # 1.0 em float32 = 3F 80 00 00 (ABCD)
    assert decode(b"\x3f\x80\x00\x00", DataType.FLOAT32, Endianness.BIG) == 1.0
    assert decode([0x3F80, 0x0000], DataType.FLOAT32, Endianness.BIG) == 1.0
    assert decode([0x0000, 0x803F], DataType.FLOAT32, Endianness.LITTLE) == 1.0
    assert decode([0x0000, 0x3F80], DataType.FLOAT32, Endianness.BIG_WORD_SWAP) == 1.0
    assert decode([0x803F, 0x0000], DataType.FLOAT32, Endianness.LITTLE_WORD_SWAP) == 1.0
    assert encode(1.0, DataType.FLOAT32, Endianness.BIG) == b"\x3f\x80\x00\x00"
    assert encode(1.0, DataType.FLOAT32, Endianness.LITTLE) == b"\x00\x00\x80\x3f"
    assert encode(1.0, DataType.FLOAT32, Endianness.BIG_WORD_SWAP) == b"\x00\x00\x3f\x80"
    assert encode(1.0, DataType.FLOAT32, Endianness.LITTLE_WORD_SWAP) == b"\x80\x3f\x00\x00"


def test_known_integer_vectors() -> None:
    assert decode([0xFFFF], DataType.INT16, Endianness.BIG) == -1
    assert decode([0xFFFF], DataType.UINT16, Endianness.BIG) == 65535
    assert decode([0x8000], DataType.INT16, Endianness.BIG) == -32768
    assert decode([0x0001, 0x0000], DataType.INT32, Endianness.BIG) == 65536
    assert decode([0x0001, 0x0000], DataType.INT32, Endianness.BIG_WORD_SWAP) == 1
    assert decode([0x1234, 0x5678], DataType.UINT32, Endianness.LITTLE) == decode(
        b"\x12\x34\x56\x78", DataType.UINT32, Endianness.LITTLE
    )


def test_bitfield_decodes_to_plain_int_not_bool() -> None:
    value = decode([0x0001, 0x0083], DataType.BITFIELD32, Endianness.BIG)
    assert value == 0x0001_0083
    assert type(value) is int
    value16 = decode([0x0181], DataType.BITFIELD16, Endianness.BIG)
    assert value16 == 0x0181
    assert type(value16) is int


def test_bool_decodes_any_nonzero_as_true() -> None:
    assert decode([0], DataType.BOOL, Endianness.BIG) is False
    assert decode([1], DataType.BOOL, Endianness.BIG) is True
    assert decode([5], DataType.BOOL, Endianness.BIG) is True
    assert encode(True, DataType.BOOL, Endianness.BIG) == b"\x00\x01"
    assert encode(False, DataType.BOOL, Endianness.LITTLE) == b"\x00\x00"


@pytest.mark.parametrize(
    ("words", "datatype"),
    [
        ([0x0001], DataType.INT32),
        ([0x0001, 0x0002, 0x0003], DataType.FLOAT32),
        ([0x0001, 0x0002], DataType.INT16),
        ([0x0001, 0x0002], DataType.FLOAT64),
        ([], DataType.INT16),
    ],
)
def test_decode_wrong_size_raises(words: list[int], datatype: DataType) -> None:
    with pytest.raises(ValueError):
        decode(words, datatype, Endianness.BIG)


def test_decode_odd_bytes_and_bad_words_raise() -> None:
    with pytest.raises(ValueError, match="esperado 2 bytes, recebido 1"):
        decode(b"\x00", DataType.INT16, Endianness.BIG)
    with pytest.raises(ValueError, match="ímpar"):
        decode(b"\x00\x01\x02", DataType.STRING, Endianness.BIG)  # string: tamanho livre
    with pytest.raises(ValueError, match="ímpar"):
        reorder(b"\x00", Endianness.LITTLE)
    with pytest.raises(ValueError, match=r"fora de 0\.\.65535"):
        decode([70000], DataType.UINT16, Endianness.BIG)
    with pytest.raises(ValueError):
        decode([-1], DataType.UINT16, Endianness.BIG)
    with pytest.raises(ValueError, match="ímpar"):
        bytes_to_words(b"\x00\x01\x02")
    with pytest.raises(ValueError):
        words_to_bytes([True])


@pytest.mark.parametrize(
    ("value", "datatype"),
    [
        (70000, DataType.UINT16),
        (-1, DataType.UINT16),
        (1 << 31, DataType.INT32),
        (1.5, DataType.INT16),
        (True, DataType.INT16),
        ("1", DataType.FLOAT32),
        (True, DataType.FLOAT32),
        (1e39, DataType.FLOAT32),
        ("abc", DataType.STRING),
        (b"", DataType.STRING),
        (12, DataType.STRING),
    ],
)
def test_encode_rejects_out_of_range_or_wrong_type(value: object, datatype: DataType) -> None:
    with pytest.raises(ValueError):
        encode(value, datatype, Endianness.BIG)


def test_encode_string_accepts_str_as_latin1() -> None:
    assert encode("AB", DataType.STRING, Endianness.BIG) == b"AB"
    assert encode("AB", DataType.STRING, Endianness.LITTLE_WORD_SWAP) == b"BA"
    assert decode(b"BA", DataType.STRING, Endianness.LITTLE_WORD_SWAP) == b"AB"


def test_expected_size_bytes() -> None:
    assert expected_size_bytes(DataType.INT16) == 2
    assert expected_size_bytes(DataType.FLOAT32) == 4
    assert expected_size_bytes(DataType.FLOAT64) == 8
    assert expected_size_bytes(DataType.STRING) is None
