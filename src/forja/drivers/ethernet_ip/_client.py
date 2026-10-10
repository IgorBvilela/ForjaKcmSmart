"""Cliente EtherNet/IP mínimo e somente leitura, sem biblioteca externa.

Fala só por mensagem explícita não conectada (UCMM, comando SendRRData). Não abre conexão de I/O
(Forward_Open): não disputa a posse das saídas do dispositivo com o sistema que já o controla.

Listas fechadas, conferidas ANTES de qualquer byte ser montado:
- comandos de encapsulamento: ListIdentity (0x63), RegisterSession (0x65),
  UnRegisterSession (0x66), SendRRData (0x6F);
- serviços CIP: Get_Attribute_All (0x01) e Get_Attribute_Single (0x0E).
Qualquer outro levanta ReadOnlyContractViolation e nada vai para o fio.

Classe, instância e atributo sempre vêm do mapping; este módulo não conhece nenhum número de
equipamento. Formato do encapsulamento e do caminho lógico: especificação CIP/EtherNet/IP (ODVA).
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import socket
import struct
from typing import Any, Final

from forja.domain.errors import (
    DriverConnectError,
    DriverReadError,
    DriverTimeout,
    ReadOnlyContractViolation,
)

ENCAP_HEADER: Final[struct.Struct] = struct.Struct("<HHII8sI")
"""comando, tamanho dos dados, sessão, status, contexto do remetente, opções (24 bytes)."""

CMD_LIST_IDENTITY: Final[int] = 0x63
CMD_REGISTER_SESSION: Final[int] = 0x65
CMD_UNREGISTER_SESSION: Final[int] = 0x66
CMD_SEND_RR_DATA: Final[int] = 0x6F
ENCAP_COMMANDS: Final[frozenset[int]] = frozenset(
    {CMD_LIST_IDENTITY, CMD_REGISTER_SESSION, CMD_UNREGISTER_SESSION, CMD_SEND_RR_DATA}
)

SVC_GET_ATTRIBUTES_ALL: Final[int] = 0x01
SVC_GET_ATTRIBUTE_SINGLE: Final[int] = 0x0E
READ_SERVICES: Final[frozenset[int]] = frozenset({SVC_GET_ATTRIBUTES_ALL, SVC_GET_ATTRIBUTE_SINGLE})

ITEM_NULL_ADDRESS: Final[int] = 0x0000
ITEM_UNCONNECTED_DATA: Final[int] = 0x00B2
ITEM_IDENTITY: Final[int] = 0x000C

MAX_REPLY_BYTES: Final[int] = 65_535

CIP_STATUS_PT: Final[dict[int, str]] = {
    0x01: "falha de conexão no dispositivo",
    0x02: "recurso indisponível no dispositivo",
    0x04: "caminho (classe/instância/atributo) mal formado",
    0x05: "classe ou instância não existe no dispositivo",
    0x08: "serviço não suportado pelo dispositivo",
    0x0F: "acesso negado pelo dispositivo",
    0x10: "estado do dispositivo não permite a leitura agora",
    0x11: "resposta grande demais",
    0x13: "dados insuficientes no pedido",
    0x14: "atributo não suportado",
    0x15: "dados demais no pedido",
    0x16: "objeto não existe no dispositivo",
}


def cip_status_pt(code: int) -> str:
    return CIP_STATUS_PT.get(code, f"status CIP 0x{code:02X} sem descrição")


def _segment(kind_8: int, kind_16: int, value: int) -> bytes:
    if not 0 <= value <= 0xFFFF:
        raise DriverReadError(f"número de caminho CIP fora de 0..65535: {value}")
    if value <= 0xFF:
        return bytes((kind_8, value))
    return bytes((kind_16, 0)) + struct.pack("<H", value)


def logical_path(class_id: int, instance: int, attribute: int | None) -> bytes:
    """Caminho lógico (EPATH acolchoado): classe, instância e, se houver, atributo."""
    path = _segment(0x20, 0x21, class_id) + _segment(0x24, 0x25, instance)
    if attribute is not None:
        path += _segment(0x30, 0x31, attribute)
    return path


def cip_read_request(service: int, path: bytes) -> bytes:
    """Monta o pedido CIP. Só serviços de leitura; o resto é recusado antes de virar bytes."""
    if service not in READ_SERVICES:
        raise ReadOnlyContractViolation(
            f"serviço CIP 0x{service:02X} bloqueado: a Forja só envia "
            f"{', '.join(f'0x{s:02X}' for s in sorted(READ_SERVICES))}"
        )
    if len(path) % 2:
        raise DriverReadError("caminho CIP com tamanho ímpar")
    return bytes((service, len(path) // 2)) + path


def encapsulate(command: int, session: int, data: bytes, context: bytes) -> bytes:
    """Cabeçalho de encapsulamento + dados. Só comandos da lista fechada."""
    if command not in ENCAP_COMMANDS:
        raise ReadOnlyContractViolation(f"comando de encapsulamento 0x{command:02X} bloqueado")
    return ENCAP_HEADER.pack(command, len(data), session, 0, context, 0) + data


def parse_cip_reply(service: int, payload: bytes) -> bytes:
    """Dados de uma resposta CIP; status diferente de zero vira DriverReadError em português."""
    if len(payload) < 4:
        raise DriverReadError("resposta CIP curta demais")
    reply_service, _reserved, general, ext_words = payload[0], payload[1], payload[2], payload[3]
    expected = service | 0x80
    if reply_service != expected:
        raise DriverReadError(
            f"resposta CIP de outro serviço (0x{reply_service:02X}; esperado 0x{expected:02X})"
        )
    data_start = 4 + 2 * ext_words
    if len(payload) < data_start:
        raise DriverReadError("resposta CIP com status estendido incompleto")
    if general != 0:
        raise DriverReadError(f"status CIP 0x{general:02X}: {cip_status_pt(general)}")
    return payload[data_start:]


def parse_items(data: bytes) -> dict[int, bytes]:
    """Itens CPF (Common Packet Format): {tipo: dados}."""
    if len(data) < 2:
        raise DriverReadError("lista de itens CPF ausente")
    (count,) = struct.unpack_from("<H", data, 0)
    pos = 2
    items: dict[int, bytes] = {}
    for _ in range(count):
        if pos + 4 > len(data):
            raise DriverReadError("item CPF truncado")
        item_type, length = struct.unpack_from("<HH", data, pos)
        pos += 4
        if pos + length > len(data):
            raise DriverReadError("dados de item CPF truncados")
        items[item_type] = data[pos : pos + length]
        pos += length
    return items


def parse_identity(item: bytes) -> dict[str, Any]:
    """Item de identidade do ListIdentity: fabricante, tipo, código, revisão, série e nome."""
    if len(item) < 33:
        raise DriverReadError("identidade CIP curta demais")
    vendor, device_type, product_code = struct.unpack_from("<HHH", item, 18)
    major, minor = item[24], item[25]
    (serial,) = struct.unpack_from("<I", item, 28)
    name_len = item[32]
    name = item[33 : 33 + name_len].decode("latin-1", errors="replace")
    return {
        "vendor_id": vendor,
        "device_type": device_type,
        "product_code": product_code,
        "revision": f"{major}.{minor}",
        "serial": f"{serial:08X}",
        "product_name": name,
    }


class EipReadClient:
    """Sessão EtherNet/IP que só lê. Uma instância por driver; um pedido por vez."""

    def __init__(self, host: str, port: int, *, timeout_s: float, connect_timeout_s: float) -> None:
        self._host = host
        self._port = port
        self._timeout_s = timeout_s
        self._connect_timeout_s = connect_timeout_s
        self._sock: socket.socket | None = None
        self._session = 0
        self._lock = asyncio.Lock()
        self._counter = itertools.count(1)

    @property
    def connected(self) -> bool:
        return self._sock is not None and self._session != 0

    async def open(self) -> None:
        """Conecta (TCP) e registra a sessão de encapsulamento."""
        self.close()
        loop = asyncio.get_running_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setblocking(False)
        try:
            await asyncio.wait_for(
                loop.sock_connect(sock, (self._host, self._port)), timeout=self._connect_timeout_s
            )
        except TimeoutError as exc:
            sock.close()
            raise DriverTimeout(
                f"sem resposta de {self._host}:{self._port} em {self._connect_timeout_s:g} s"
            ) from exc
        except OSError as exc:
            sock.close()
            raise DriverConnectError(
                f"conexão com {self._host}:{self._port} falhou: {exc}"
            ) from exc
        self._sock = sock
        try:
            header, _ = await self._exchange(
                CMD_REGISTER_SESSION, 0, struct.pack("<HH", 1, 0), self._connect_timeout_s
            )
        except Exception:
            self.close()
            raise
        session = header[2]
        if session == 0:
            self.close()
            raise DriverConnectError("dispositivo não abriu sessão EtherNet/IP")
        self._session = session

    def close(self) -> None:
        """Encerra a sessão (melhor esforço) e fecha o socket."""
        sock, self._sock = self._sock, None
        session, self._session = self._session, 0
        if sock is None:
            return
        if session:
            with contextlib.suppress(OSError):
                sock.send(encapsulate(CMD_UNREGISTER_SESSION, session, b"", self._context()))
        with contextlib.suppress(OSError):
            sock.close()

    async def identity(self) -> dict[str, Any] | None:
        """ListIdentity: quem é o dispositivo. Só leitura; None se ele não responder."""
        try:
            _, data = await self._exchange(CMD_LIST_IDENTITY, 0, b"", self._timeout_s)
            item = parse_items(data).get(ITEM_IDENTITY)
            return parse_identity(item) if item else None
        except (DriverReadError, DriverTimeout):
            return None

    async def read_attribute(self, class_id: int, instance: int, attribute: int) -> bytes:
        """Get_Attribute_Single: dados brutos de um atributo."""
        return await self._request(
            SVC_GET_ATTRIBUTE_SINGLE, logical_path(class_id, instance, attribute)
        )

    async def read_all(self, class_id: int, instance: int) -> bytes:
        """Get_Attribute_All: todos os atributos de uma instância, como o dispositivo devolve."""
        return await self._request(SVC_GET_ATTRIBUTES_ALL, logical_path(class_id, instance, None))

    # ------------------------------------------------------------------ interno

    def _context(self) -> bytes:
        return struct.pack("<Q", next(self._counter))

    async def _request(self, service: int, path: bytes) -> bytes:
        if not self.connected:
            raise DriverConnectError("leitura sem sessão EtherNet/IP aberta")
        cip = cip_read_request(service, path)
        body = struct.pack("<IHH", 0, 0, 2)
        body += struct.pack("<HH", ITEM_NULL_ADDRESS, 0)
        body += struct.pack("<HH", ITEM_UNCONNECTED_DATA, len(cip)) + cip
        _, data = await self._exchange(CMD_SEND_RR_DATA, self._session, body, self._timeout_s)
        if len(data) < 6:
            raise DriverReadError("resposta SendRRData curta demais")
        items = parse_items(data[6:])
        payload = items.get(ITEM_UNCONNECTED_DATA)
        if payload is None:
            raise DriverReadError("resposta sem item de dados não conectados")
        return parse_cip_reply(service, payload)

    async def _exchange(
        self, command: int, session: int, data: bytes, timeout_s: float
    ) -> tuple[tuple[int, int, int, int, bytes, int], bytes]:
        sock = self._sock
        if sock is None:
            raise DriverConnectError("sem conexão aberta")
        context = self._context()
        frame = encapsulate(command, session, data, context)
        loop = asyncio.get_running_loop()
        async with self._lock:
            try:
                await asyncio.wait_for(loop.sock_sendall(sock, frame), timeout=timeout_s)
                raw_header = await asyncio.wait_for(
                    self._recv_exact(sock, ENCAP_HEADER.size), timeout=timeout_s
                )
                header = ENCAP_HEADER.unpack(raw_header)
                length = header[1]
                if length > MAX_REPLY_BYTES:
                    raise DriverReadError(f"resposta anunciada com {length} bytes")
                body = (
                    await asyncio.wait_for(self._recv_exact(sock, length), timeout=timeout_s)
                    if length
                    else b""
                )
            except TimeoutError as exc:
                raise DriverTimeout(f"sem resposta em {timeout_s:g} s") from exc
            except (ConnectionError, OSError) as exc:
                raise DriverConnectError(f"conexão perdida: {exc}") from exc
        if header[0] != command:
            raise DriverReadError(
                f"resposta de outro comando (0x{header[0]:02X}; esperado 0x{command:02X})"
            )
        if header[3] != 0:
            raise DriverReadError(f"status de encapsulamento 0x{header[3]:X}")
        if header[4] != context:
            raise DriverReadError("resposta não corresponde ao pedido (contexto diferente)")
        return header, body

    @staticmethod
    async def _recv_exact(sock: socket.socket, size: int) -> bytes:
        loop = asyncio.get_running_loop()
        buf = bytearray()
        while len(buf) < size:
            chunk = await loop.sock_recv(sock, size - len(buf))
            if not chunk:
                raise ConnectionError("conexão fechada pelo dispositivo")
            buf += chunk
        return bytes(buf)
