"""Cliente Modbus TCP somente leitura. Único módulo do produto que importa o pymodbus.

Barreiras de leitura, da mais externa para a mais interna:
1. Esta classe só oferece leitura por área: coil (01), discrete (02), holding (03), input (04).
2. Toda PDU de saída passa por ``guard_pdu`` antes de virar quadro: função fora de
   ``READ_FUNCTION_CODES`` levanta ``ReadOnlyContractViolation`` e nada é enviado.
3. ``retries=0`` e ``reconnect_delay=0``: o pymodbus não repete nem reconecta sozinho; quem decide
   nova tentativa é o supervisor da Forja (backoff no loop de aquisição).

O cliente do pymodbus fica num atributo privado; nenhum outro módulo chega até ele.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Final

from pymodbus import ExceptionResponse, FramerType
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ConnectionException, ModbusException, ModbusIOException
from pymodbus.pdu import ModbusPDU

from forja.domain.errors import (
    DriverConnectError,
    DriverReadError,
    DriverTimeout,
    ReadOnlyContractViolation,
)

READ_FUNCTION_CODES: Final[frozenset[int]] = frozenset({1, 2, 3, 4})
"""Únicas funções Modbus que a Forja coloca no fio (Modbus Application Protocol V1.1b3)."""

AREA_FUNCTION: Final[dict[str, int]] = {"coil": 1, "discrete": 2, "holding": 3, "input": 4}
BIT_AREAS: Final[frozenset[str]] = frozenset({"coil", "discrete"})

EXCEPTION_PT: Final[dict[int, str]] = {
    1: "função não aceita pelo equipamento",
    2: "endereço não existe no equipamento",
    3: "quantidade ou valor fora do aceito pelo equipamento",
    4: "falha interna do equipamento ao responder",
    5: "equipamento ocupado processando pedido longo",
    6: "equipamento ocupado",
    8: "erro de paridade de memória no equipamento",
    10: "gateway sem caminho até o equipamento",
    11: "gateway: o equipamento de destino não respondeu",
}


def guard_pdu(sending: bool, pdu: ModbusPDU) -> ModbusPDU:
    """Chamado pelo pymodbus em toda PDU. Bloqueia, antes do fio, qualquer função que não leia."""
    if sending and int(pdu.function_code) not in READ_FUNCTION_CODES:
        raise ReadOnlyContractViolation(
            f"função Modbus {pdu.function_code} bloqueada: a Forja só envia leituras "
            f"{sorted(READ_FUNCTION_CODES)}"
        )
    return pdu


def exception_text_pt(code: int) -> str:
    return EXCEPTION_PT.get(code, f"código de exceção {code} sem descrição")


class ModbusReadClient:
    """Conexão Modbus TCP que só lê. Uma instância por driver; nunca compartilhada."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        timeout_s: float,
        connect_timeout_s: float,
        name: str = "forja",
    ) -> None:
        self._host = host
        self._port = port
        self._timeout_s = timeout_s
        self._connect_timeout_s = connect_timeout_s
        self._name = name
        self._client: AsyncModbusTcpClient | None = None

    @property
    def connected(self) -> bool:
        return self._client is not None and bool(self._client.connected)

    async def open(self) -> None:
        """Abre a conexão TCP. Falha vira DriverConnectError ou DriverTimeout."""
        self.close()
        client = AsyncModbusTcpClient(
            self._host,
            port=self._port,
            framer=FramerType.SOCKET,
            name=self._name,
            timeout=self._timeout_s,
            retries=0,
            reconnect_delay=0,
            reconnect_delay_max=0,
            trace_pdu=guard_pdu,
        )
        self._client = client
        try:
            ok = await asyncio.wait_for(client.connect(), timeout=self._connect_timeout_s)
        except TimeoutError as exc:
            self.close()
            raise DriverTimeout(
                f"sem resposta de {self._host}:{self._port} em {self._connect_timeout_s:g} s"
            ) from exc
        except (OSError, ModbusException) as exc:
            self.close()
            raise DriverConnectError(
                f"conexão com {self._host}:{self._port} falhou: {exc}"
            ) from exc
        if not ok:
            self.close()
            raise DriverConnectError(f"conexão com {self._host}:{self._port} recusada")

    def close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            client.close()

    async def read(self, area: str, address: int, count: int, unit_id: int) -> tuple[int, ...]:
        """Lê ``count`` registradores (0..65535) ou bits (0/1) a partir de ``address``."""
        client = self._client
        if client is None or not client.connected:
            raise DriverConnectError("leitura sem conexão aberta")
        call = self._reader(client, area)
        try:
            response = await call(address, count=count, device_id=unit_id)
        except ReadOnlyContractViolation:
            raise
        except ModbusIOException as exc:
            text = str(exc)
            if "No response" in text or "not responding" in text:
                raise DriverTimeout(
                    f"sem resposta em {self._timeout_s:g} s (área {area}, endereço {address})"
                ) from exc
            raise DriverReadError(f"resposta inválida: {text[:160]}") from exc
        except ConnectionException as exc:
            raise DriverConnectError(f"conexão perdida: {str(exc)[:160]}") from exc
        except (OSError, ModbusException) as exc:
            raise DriverReadError(f"falha na leitura: {str(exc)[:160]}") from exc
        return self._values(response, area, address, count)

    @staticmethod
    def _reader(client: AsyncModbusTcpClient, area: str) -> Callable[..., Awaitable[ModbusPDU]]:
        readers: dict[str, Callable[..., Any]] = {
            "coil": client.read_coils,
            "discrete": client.read_discrete_inputs,
            "holding": client.read_holding_registers,
            "input": client.read_input_registers,
        }
        try:
            return readers[area]
        except KeyError as exc:
            raise DriverReadError(f"área Modbus desconhecida: {area!r}") from exc

    @staticmethod
    def _values(response: ModbusPDU, area: str, address: int, count: int) -> tuple[int, ...]:
        if isinstance(response, ExceptionResponse) or response.isError():
            code = int(getattr(response, "exception_code", 0) or 0)
            raise DriverReadError(
                f"exceção Modbus {code} na área {area}, endereço {address}: "
                f"{exception_text_pt(code)}"
            )
        if area in BIT_AREAS:
            bits = list(getattr(response, "bits", []) or [])
            if len(bits) < count:
                raise DriverReadError(f"resposta curta: {len(bits)} de {count} bits")
            return tuple(1 if b else 0 for b in bits[:count])
        registers = list(getattr(response, "registers", []) or [])
        if len(registers) != count:
            raise DriverReadError(f"resposta com {len(registers)} registradores; esperado {count}")
        return tuple(int(r) & 0xFFFF for r in registers)
