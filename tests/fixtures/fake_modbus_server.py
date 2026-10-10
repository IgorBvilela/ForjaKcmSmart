"""Servidor Modbus TCP falso para testes (só 127.0.0.1, porta efêmera).

Implementação própria e mínima do quadro MBAP, independente do pymodbus: assim o teste prova o que
chega no fio. Registra TODA função recebida (inclusive as de escrita, que respondem exceção 01 e
nunca alteram nada) e simula falhas reais: silêncio (timeout), conexão derrubada, exceção Modbus,
resposta curta, resposta inválida e atraso.

Valores são dados de teste, sem relação com nenhum equipamento real.
"""

from __future__ import annotations

import asyncio
import contextlib
import struct
from dataclasses import dataclass, field
from typing import Literal

Mode = Literal["ok", "silent", "close", "exception", "short", "garbage", "delay"]

READ_FCS = frozenset({1, 2, 3, 4})


@dataclass(frozen=True)
class Request:
    unit: int
    function: int
    start: int | None
    quantity: int | None
    raw_pdu: bytes


@dataclass
class FakeModbusServer:
    holding: dict[int, int] = field(default_factory=dict)
    inputs: dict[int, int] = field(default_factory=dict)
    coils: dict[int, bool] = field(default_factory=dict)
    discretes: dict[int, bool] = field(default_factory=dict)
    unit_id: int | None = None
    """Se definido, outra unidade recebe exceção 0x0B (gateway: alvo não respondeu)."""
    strict: bool = True
    """Endereço sem valor definido responde exceção 02 (como um equipamento real)."""
    mode: Mode = "ok"
    exception_code: int = 2
    delay_s: float = 0.0
    requests: list[Request] = field(default_factory=list)
    connections: int = 0
    _server: asyncio.base_events.Server | None = None
    _writers: set[asyncio.StreamWriter] = field(default_factory=set)

    @property
    def port(self) -> int:
        assert self._server is not None
        sock = self._server.sockets[0]
        return int(sock.getsockname()[1])

    @property
    def functions(self) -> set[int]:
        return {r.function for r in self.requests}

    async def start(self) -> FakeModbusServer:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        return self

    async def stop(self) -> None:
        for w in list(self._writers):
            w.close()
        if self._server is not None:
            self._server.close()
            with contextlib.suppress(Exception):
                await self._server.wait_closed()
            self._server = None

    async def drop_clients(self) -> None:
        """Derruba as conexões abertas (cabo arrancado, reinício do módulo)."""
        for w in list(self._writers):
            w.close()
            with contextlib.suppress(Exception):
                await w.wait_closed()
        self._writers.clear()

    # ------------------------------------------------------------------ protocolo

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.connections += 1
        self._writers.add(writer)
        try:
            while True:
                header = await reader.readexactly(7)
                tid, pid, length, unit = struct.unpack(">HHHB", header)
                pdu = await reader.readexactly(length - 1)
                fc = pdu[0]
                start = qty = None
                if len(pdu) >= 5:
                    start, qty = struct.unpack(">HH", pdu[1:5])
                self.requests.append(Request(unit, fc, start, qty, bytes(pdu)))
                reply = await self._reply(unit, fc, start, qty)
                if reply is None:
                    continue
                if reply == b"__close__":
                    break
                writer.write(struct.pack(">HHHB", tid, pid, len(reply) + 1, unit) + reply)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            self._writers.discard(writer)
            writer.close()

    async def _reply(self, unit: int, fc: int, start: int | None, qty: int | None) -> bytes | None:
        if self.mode == "silent":
            return None
        if self.mode == "close":
            return b"__close__"
        if self.mode == "delay" and self.delay_s > 0:
            await asyncio.sleep(self.delay_s)
        if self.mode == "garbage":
            return bytes([fc, 0xFF, 0x01])
        if fc not in READ_FCS:
            return bytes([fc | 0x80, 0x01])
        if self.unit_id is not None and unit != self.unit_id:
            return bytes([fc | 0x80, 0x0B])
        if self.mode == "exception":
            return bytes([fc | 0x80, self.exception_code])
        assert start is not None
        assert qty is not None
        if fc in (1, 2):
            table = self.coils if fc == 1 else self.discretes
            bits = [table.get(a) for a in range(start, start + qty)]
            if self.strict and any(b is None for b in bits):
                return bytes([fc | 0x80, 0x02])
            packed = bytearray((qty + 7) // 8)
            for i, b in enumerate(bits):
                if b:
                    packed[i // 8] |= 1 << (i % 8)
            return bytes([fc, len(packed)]) + bytes(packed)
        table16 = self.holding if fc == 3 else self.inputs
        words = [table16.get(a) for a in range(start, start + qty)]
        if self.strict and any(w is None for w in words):
            return bytes([fc | 0x80, 0x02])
        if self.mode == "short":
            words = words[: max(0, qty - 1)]
        data = b"".join(struct.pack(">H", (w or 0) & 0xFFFF) for w in words)
        return bytes([fc, len(data)]) + data


def float32_words(value: float, order: Literal["ABCD", "CDAB"] = "ABCD") -> tuple[int, int]:
    """float32 em duas palavras de 16 bits (dados de teste)."""
    hi, lo = struct.unpack(">HH", struct.pack(">f", value))
    return (hi, lo) if order == "ABCD" else (lo, hi)
