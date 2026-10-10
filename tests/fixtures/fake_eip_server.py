"""Respondedor EtherNet/IP falso para testes (só 127.0.0.1, porta efêmera).

Implementação própria e mínima, independente do cliente da Forja: registra todo comando de
encapsulamento e todo serviço CIP recebido (inclusive os que não leem, que respondem "serviço
não suportado" e nunca alteram nada) e simula falhas: silêncio, conexão derrubada, resposta
inválida e status CIP de erro. Atributos são dados de teste, sem relação com nenhum dispositivo.
"""

from __future__ import annotations

import asyncio
import contextlib
import struct
from dataclasses import dataclass, field
from typing import Literal

HEADER = struct.Struct("<HHII8sI")
Mode = Literal["ok", "silent", "close", "garbage", "cip_error"]


@dataclass(frozen=True)
class EipRequest:
    command: int
    session: int
    service: int | None = None
    class_id: int | None = None
    instance: int | None = None
    attribute: int | None = None


def _parse_path(path: bytes) -> dict[str, int]:
    out: dict[str, int] = {}
    pos = 0
    names = {
        0x20: "class",
        0x21: "class",
        0x24: "instance",
        0x25: "instance",
        0x30: "attribute",
        0x31: "attribute",
    }
    while pos < len(path):
        seg = path[pos]
        if seg in (0x20, 0x24, 0x30):
            out[names[seg]] = path[pos + 1]
            pos += 2
        elif seg in (0x21, 0x25, 0x31):
            out[names[seg]] = struct.unpack_from("<H", path, pos + 2)[0]
            pos += 4
        else:
            break
    return out


@dataclass
class FakeEipServer:
    attributes: dict[tuple[int, int, int], bytes] = field(default_factory=dict)
    product_name: str = "Dispositivo de teste"
    mode: Mode = "ok"
    cip_error: int = 0x14
    requests: list[EipRequest] = field(default_factory=list)
    connections: int = 0
    _server: asyncio.base_events.Server | None = None
    _writers: set[asyncio.StreamWriter] = field(default_factory=set)
    _next_session: int = 0x0100_0001

    @property
    def port(self) -> int:
        assert self._server is not None
        return int(self._server.sockets[0].getsockname()[1])

    @property
    def services(self) -> set[int]:
        return {r.service for r in self.requests if r.service is not None}

    @property
    def commands(self) -> set[int]:
        return {r.command for r in self.requests}

    async def start(self) -> FakeEipServer:
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
        for w in list(self._writers):
            w.close()
            with contextlib.suppress(Exception):
                await w.wait_closed()
        self._writers.clear()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.connections += 1
        self._writers.add(writer)
        sessions: set[int] = set()
        try:
            while True:
                raw = await reader.readexactly(HEADER.size)
                command, length, session, _status, context, _opt = HEADER.unpack(raw)
                data = await reader.readexactly(length) if length else b""
                reply = self._reply(command, session, data, context, sessions)
                if reply is None:
                    continue
                if reply == b"__close__":
                    break
                writer.write(reply)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            self._writers.discard(writer)
            writer.close()

    def _frame(
        self, command: int, session: int, context: bytes, body: bytes, status: int = 0
    ) -> bytes:
        return HEADER.pack(command, len(body), session, status, context, 0) + body

    def _reply(
        self, command: int, session: int, data: bytes, context: bytes, sessions: set[int]
    ) -> bytes | None:
        if command == 0x65:  # RegisterSession
            self.requests.append(EipRequest(command, session))
            handle = self._next_session
            self._next_session += 1
            sessions.add(handle)
            return self._frame(command, handle, context, data)
        if command == 0x66:  # UnRegisterSession: sem resposta
            self.requests.append(EipRequest(command, session))
            sessions.discard(session)
            return None
        if command == 0x63:  # ListIdentity
            self.requests.append(EipRequest(command, session))
            name = self.product_name.encode("latin-1")
            item = (
                struct.pack("<H", 1)
                + bytes(16)
                + struct.pack("<HHH", 1, 12, 7)
                + bytes((2, 5))
                + struct.pack("<H", 0)
                + struct.pack("<I", 0xABCD1234)
                + bytes((len(name),))
                + name
                + bytes((3,))
            )
            body = struct.pack("<H", 1) + struct.pack("<HH", 0x0C, len(item)) + item
            return self._frame(command, 0, context, body)
        if command != 0x6F:
            self.requests.append(EipRequest(command, session))
            return self._frame(command, session, context, b"", status=0x01)
        # SendRRData
        if session not in sessions:
            self.requests.append(EipRequest(command, session))
            return self._frame(command, session, context, b"", status=0x64)
        count = struct.unpack_from("<H", data, 6)[0]
        pos = 8
        cip = b""
        for _ in range(count):
            item_type, length = struct.unpack_from("<HH", data, pos)
            pos += 4
            if item_type == 0xB2:
                cip = data[pos : pos + length]
            pos += length
        service, words = cip[0], cip[1]
        path = _parse_path(cip[2 : 2 + 2 * words])
        self.requests.append(
            EipRequest(
                command,
                session,
                service,
                path.get("class"),
                path.get("instance"),
                path.get("attribute"),
            )
        )
        if self.mode == "silent":
            return None
        if self.mode == "close":
            return b"__close__"
        if self.mode == "garbage":
            return self._frame(command, session, context, b"\x01\x02")
        status, payload = self._service(service, path)
        reply_cip = bytes((service | 0x80, 0, status, 0)) + payload
        body = (
            struct.pack("<IHH", 0, 0, 2)
            + struct.pack("<HH", 0x0000, 0)
            + struct.pack("<HH", 0x00B2, len(reply_cip))
            + reply_cip
        )
        return self._frame(command, session, context, body)

    def _service(self, service: int, path: dict[str, int]) -> tuple[int, bytes]:
        if self.mode == "cip_error":
            return self.cip_error, b""
        if service == 0x0E:
            key = (path.get("class", -1), path.get("instance", -1), path.get("attribute", -1))
            if key not in self.attributes:
                return 0x14, b""
            return 0, self.attributes[key]
        if service == 0x01:
            found = [
                v
                for (c, i, _a), v in sorted(self.attributes.items())
                if c == path.get("class") and i == path.get("instance")
            ]
            return (0, b"".join(found)) if found else (0x16, b"")
        return 0x08, b""  # qualquer outro serviço: não suportado, nada muda
