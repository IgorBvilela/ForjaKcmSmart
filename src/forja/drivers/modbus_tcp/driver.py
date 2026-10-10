"""Driver Modbus TCP somente leitura (EXPERIMENTAL até a validação no KCM real).

Superfície pública: name, connect, disconnect, read, health, capabilities. Nada mais.
Endereços, tipos, ordem de bytes e escalas vêm do mapping externo; IP, porta e unit id vêm do
perfil. Nenhum valor de planta existe neste código. Um bloco do ReadPlan = uma requisição.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from forja.domain.assets import EquipmentProfile
from forja.domain.errors import ConfigError, DriverConnectError, DriverError, DriverReadError
from forja.domain.evidence import UNKNOWN
from forja.domain.mapping import Mapping
from forja.domain.ports import (
    Clock,
    DriverCapabilities,
    DriverHealth,
    DriverSupportState,
    ReadOnlyDriverBase,
)
from forja.domain.samples import RawBlock, RawFrame, ReadPlan
from forja.drivers.modbus_tcp._client import AREA_FUNCTION, ModbusReadClient
from forja.drivers.support import library_version

MAX_UNIT_ID = 255
EXPERIMENTAL_NOTE_PT = (
    "Somente leitura (funções 01, 02, 03 e 04). Testado contra servidor Modbus de teste local; "
    "validação no KCM real pendente."
)


@dataclass(frozen=True)
class ModbusSettings:
    host: str
    port: int
    unit_id: int
    timeout_s: float
    connect_timeout_s: float


def modbus_settings(profile: EquipmentProfile) -> ModbusSettings:
    """Valida IP, porta e unit id do perfil. Mensagens em português; nada é presumido."""
    comm = profile.communication
    problems: list[str] = []
    host = str(comm.ip).strip()
    if host == UNKNOWN or not host:
        problems.append("endereço IP não informado")
    else:
        try:
            ipaddress.IPv4Address(host)
        except ValueError:
            problems.append(f"endereço IP inválido: {host!r}")
    port = _int_or_none(comm.port)
    if port is None:
        problems.append("porta não informada")
    elif not 1 <= port <= 65535:
        problems.append(f"porta fora de 1..65535: {port}")
    unit_id = _int_or_none(comm.unit_id)
    if unit_id is None:
        problems.append("unit id (endereço do escravo) não informado")
    elif not 0 <= unit_id <= MAX_UNIT_ID:
        problems.append(f"unit id fora de 0..{MAX_UNIT_ID}: {unit_id}")
    if problems:
        raise ConfigError(
            f"{profile.id}: Modbus TCP sem configuração completa: {'; '.join(problems)}"
        )
    assert port is not None
    assert unit_id is not None
    return ModbusSettings(
        host=host,
        port=port,
        unit_id=unit_id,
        timeout_s=comm.timeout_s,
        connect_timeout_s=comm.connect_timeout_s,
    )


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


ClientFactory = Callable[[ModbusSettings], ModbusReadClient]


def _default_client(settings: ModbusSettings) -> ModbusReadClient:
    return ModbusReadClient(
        settings.host,
        settings.port,
        timeout_s=settings.timeout_s,
        connect_timeout_s=settings.connect_timeout_s,
    )


class ModbusTcpDriver(ReadOnlyDriverBase):
    """Lê blocos do ReadPlan só com funções de leitura. Payload = tupla de palavras ou bits."""

    name = "modbus_tcp"

    def __init__(
        self,
        profile: EquipmentProfile,
        mapping: Mapping,
        clock: Clock,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self._profile = profile
        self._mapping = mapping
        self._clock = clock
        self._settings = modbus_settings(profile)
        self._factory = client_factory or _default_client
        self._client: ModbusReadClient | None = None
        self._last_ok_utc: datetime | None = None
        self._last_latency_ms: float | None = None
        self._consecutive_errors = 0
        self._detail_pt = "Desconectado"

    async def connect(self) -> None:
        await self.disconnect()
        client = self._factory(self._settings)
        try:
            await client.open()
        except DriverError as exc:
            self._consecutive_errors += 1
            self._detail_pt = str(exc)
            raise
        self._client = client
        self._detail_pt = f"Conectado a {self._settings.host}:{self._settings.port}"

    async def disconnect(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            client.close()
            self._detail_pt = "Desconectado"

    async def read(self, plan: ReadPlan) -> RawFrame:
        client = self._client
        if client is None or not client.connected:
            raise DriverConnectError(f"{self._profile.id}: leitura sem conexão aberta")
        blocks: dict[str, RawBlock] = {}
        frame_t0 = self._clock.monotonic_ns()
        try:
            for block in plan.blocks:
                if block.area not in AREA_FUNCTION:
                    raise DriverReadError(
                        f"bloco {block.block_id}: área {block.area!r} não é Modbus"
                    )
                if isinstance(block.address, bool) or not isinstance(block.address, int):
                    raise DriverReadError(f"bloco {block.block_id}: endereço não numérico")
                t0 = self._clock.monotonic_ns()
                values = await client.read(
                    block.area, block.address, block.count, self._settings.unit_id
                )
                now_mono = self._clock.monotonic_ns()
                blocks[block.block_id] = RawBlock(
                    block_id=block.block_id,
                    payload=values,
                    ts_utc=self._clock.now_utc(),
                    ts_mono_ns=now_mono,
                    latency_ms=(now_mono - t0) / 1_000_000,
                )
        except DriverError as exc:
            self._consecutive_errors += 1
            self._detail_pt = str(exc)
            raise
        latency_ms = (self._clock.monotonic_ns() - frame_t0) / 1_000_000
        ts_utc = self._clock.now_utc()
        self._last_ok_utc = ts_utc
        self._last_latency_ms = latency_ms
        self._consecutive_errors = 0
        self._detail_pt = f"Leitura de {len(blocks)} bloco(s) concluída"
        return RawFrame(
            equipment_id=self._profile.id, ts_utc=ts_utc, blocks=blocks, latency_ms=latency_ms
        )

    async def health(self) -> DriverHealth:
        return DriverHealth(
            connected=self._client is not None and self._client.connected,
            last_ok_utc=self._last_ok_utc,
            latency_ms=self._last_latency_ms,
            consecutive_errors=self._consecutive_errors,
            detail_pt=self._detail_pt,
        )

    def capabilities(self) -> DriverCapabilities:
        return DriverCapabilities(
            protocol="modbus_tcp",
            support_state=DriverSupportState.EXPERIMENTAL,
            library="pymodbus",
            library_version=library_version("pymodbus"),
            read_areas=tuple(AREA_FUNCTION),
            max_block_size=125,
            supports_device_identification=False,
            note_pt=EXPERIMENTAL_NOTE_PT,
        )
