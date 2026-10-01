"""Decodificacao de palavras/bytes brutos em valores, e o inverso para testes e fakes.

Ordem de bytes para N bytes (A e o byte mais significativo):
- big               ABCD      (ordem canonica de rede)
- little            DCBA      (bytes invertidos)
- big_word_swap     CDAB      (palavras de 16 bits em ordem inversa, bytes big dentro da palavra)
- little_word_swap  BADC      (bytes trocados dentro de cada palavra, ordem das palavras mantida)
Cada reordenacao e involucao: aplicar duas vezes devolve a entrada. Por isso decode e encode
usam a mesma funcao `reorder`.
"""

from __future__ import annotations

import struct
from collections.abc import Sequence

from forja.domain.mapping import DataType, Endianness

_FORMAT: dict[DataType, str] = {
    DataType.INT16: ">h",
    DataType.UINT16: ">H",
    DataType.INT32: ">i",
    DataType.UINT32: ">I",
    DataType.FLOAT32: ">f",
    DataType.FLOAT64: ">d",
    DataType.BOOL: ">H",
    DataType.BITFIELD16: ">H",
    DataType.BITFIELD32: ">I",
}

_INT_RANGE: dict[DataType, tuple[int, int]] = {
    DataType.INT16: (-(1 << 15), (1 << 15) - 1),
    DataType.UINT16: (0, (1 << 16) - 1),
    DataType.INT32: (-(1 << 31), (1 << 31) - 1),
    DataType.UINT32: (0, (1 << 32) - 1),
    DataType.BITFIELD16: (0, (1 << 16) - 1),
    DataType.BITFIELD32: (0, (1 << 32) - 1),
}

FLOAT_TYPES = frozenset({DataType.FLOAT32, DataType.FLOAT64})
INT_TYPES = frozenset(_INT_RANGE)


def expected_size_bytes(datatype: DataType) -> int | None:
    """Tamanho fixo em bytes; None para string (tamanho vem do mapping)."""
    if datatype is DataType.STRING:
        return None
    return datatype.word_count * 2


def words_to_bytes(words: Sequence[int]) -> bytes:
    """Registradores de 16 bits -> bytes (cada palavra big-endian)."""
    out = bytearray()
    for i, w in enumerate(words):
        if isinstance(w, bool) or not isinstance(w, int) or not 0 <= w <= 0xFFFF:
            raise ValueError(f"palavra {i} fora de 0..65535: {w!r}")
        out += w.to_bytes(2, "big")
    return bytes(out)


def bytes_to_words(data: bytes) -> tuple[int, ...]:
    if len(data) % 2:
        raise ValueError(f"quantidade ímpar de bytes: {len(data)}")
    return tuple(int.from_bytes(data[i : i + 2], "big") for i in range(0, len(data), 2))


def reorder(data: bytes, endianness: Endianness) -> bytes:
    """Converte entre ordem de fio e ordem canonica (big). Involucao."""
    if len(data) % 2:
        raise ValueError(f"quantidade ímpar de bytes: {len(data)}")
    if endianness is Endianness.BIG:
        return bytes(data)
    if endianness is Endianness.LITTLE:
        return bytes(data[::-1])
    words = [data[i : i + 2] for i in range(0, len(data), 2)]
    if endianness is Endianness.BIG_WORD_SWAP:
        return b"".join(reversed(words))
    if endianness is Endianness.LITTLE_WORD_SWAP:
        return b"".join(w[::-1] for w in words)
    raise ValueError(f"endianness desconhecida: {endianness!r}")


def _as_bytes(words: Sequence[int] | bytes) -> bytes:
    if isinstance(words, bytes | bytearray | memoryview):
        return bytes(words)
    return words_to_bytes(words)


def decode(
    words: Sequence[int] | bytes, datatype: DataType, endianness: Endianness
) -> float | int | bool | bytes:
    """Bytes/palavras no fio -> valor. bitfield -> int, string -> bytes, bool -> bool.

    ValueError em tamanho errado, palavra fora de faixa ou tipo desconhecido.
    """
    data = _as_bytes(words)
    if not data:
        raise ValueError("nenhum byte para decodificar")
    expected = expected_size_bytes(datatype)
    if expected is not None and len(data) != expected:
        raise ValueError(f"{datatype.value}: esperado {expected} bytes, recebido {len(data)}")
    canonical = reorder(data, endianness)
    if datatype is DataType.STRING:
        return canonical
    if datatype is DataType.BOOL:
        return bool(struct.unpack(_FORMAT[datatype], canonical)[0] != 0)
    value: float | int = struct.unpack(_FORMAT[datatype], canonical)[0]
    return value


def encode(value: object, datatype: DataType, endianness: Endianness) -> bytes:
    """Valor -> bytes na ordem de fio. Inverso exato de decode para o mesmo datatype."""
    if datatype is DataType.STRING:
        return _encode_string(value, endianness)
    if datatype is DataType.BOOL:
        return reorder(struct.pack(_FORMAT[datatype], 1 if value else 0), endianness)
    if datatype in INT_TYPES:
        return reorder(struct.pack(_FORMAT[datatype], _checked_int(value, datatype)), endianness)
    if datatype in FLOAT_TYPES:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError(f"{datatype.value}: valor deve ser número (recebido {value!r})")
        try:
            return reorder(struct.pack(_FORMAT[datatype], float(value)), endianness)
        except OverflowError as exc:
            raise ValueError(f"{datatype.value}: valor fora do alcance: {value!r}") from exc
    raise ValueError(f"datatype desconhecido: {datatype!r}")


def _checked_int(value: object, datatype: DataType) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{datatype.value}: valor deve ser inteiro (recebido {value!r})")
    low, high = _INT_RANGE[datatype]
    if not low <= value <= high:
        raise ValueError(f"{datatype.value}: {value} fora de {low}..{high}")
    return value


def _encode_string(value: object, endianness: Endianness) -> bytes:
    if isinstance(value, str):
        data = value.encode("latin-1")
    elif isinstance(value, bytes | bytearray):
        data = bytes(value)
    else:
        raise ValueError(f"string: valor deve ser str ou bytes (recebido {type(value).__name__})")
    if not data or len(data) % 2:
        raise ValueError(f"string: tamanho deve ser par e > 0 (recebido {len(data)})")
    return reorder(data, endianness)
