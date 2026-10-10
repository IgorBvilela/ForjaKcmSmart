"""Driver EtherNet/IP somente leitura (EXPERIMENTAL até a validação no KCM real).

Superfície pública: name, connect, disconnect, read, health, capabilities. Nada mais.
Cada bloco do ReadPlan é um atributo CIP (classe, instância, atributo vindos do mapping) lido com
Get_Attribute_Single por mensagem explícita. Os bytes do atributo vão inteiros para o
normalizador, que recorta cada variável pelo deslocamento do mapping.
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
from forja.drivers.ethernet_ip._client import EipReadClient

EXPERIMENTAL_NOTE_PT = (
    "Somente leitura por mensagem explícita (Get_Attribute_Single). Não abre conexão de I/O e não "
    "disputa a posse do dispositivo. Testado contra respondedor de teste local; validação no KCM "
    "real pendente."
)


@dataclass(frozen=True)
class EipSettings:
    host: str
    port: int
    timeout_s: float
    connect_timeout_s: float


def eip_settings(profile: EquipmentProfile) -> EipSettings:
    """Valida IP e porta do perfil. Mensagens em português; nada é presumido."""
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
    port = comm.port if isinstance(comm.port, int) and not isinstance(comm.port, bool) else None
    if port is None and isinstance(comm.port, str) and comm.port.strip().isdigit():
        port = int(comm.port.strip())
    if port is None:
        problems.append("porta não informada")
    elif not 1 <= port <= 65535:
        problems.append(f"porta fora de 1..65535: {port}")
    if problems:
        raise ConfigError(
            f"{profile.id}: EtherNet/IP sem configuração completa: {'; '.join(problems)}"
        )
    assert port is not None
    return EipSettings(
        host=host, port=port, timeout_s=comm.timeout_s, connect_timeout_s=comm.connect_timeout_s
    )


ClientFactory = Callable[[EipSettings], EipReadClient]


def _default_client(settings: EipSettings) -> EipReadClient:
    return EipReadClient(
        settings.host,
        settings.port,
        timeout_s=settings.timeout_s,
        connect_timeout_s=settings.connect_timeout_s,
    )


def _identity_pt(identity: dict[str, object] | None) -> str:
    if not identity:
        return ""
    name = str(identity.get("product_name") or "produto sem nome")
    return (
        f"{name} (fabricante {identity.get('vendor_id')}, produto {identity.get('product_code')}, "
        f"revisão {identity.get('revision')}, série {identity.get('serial')})"
    )


class EthernetIpDriver(ReadOnlyDriverBase):
    """Lê atributos CIP do ReadPlan. Payload de cada bloco = bytes do atributo."""

    name = "ethernet_ip"

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
        self._settings = eip_settings(profile)
        self._factory = client_factory or _default_client
        self._client: EipReadClient | None = None
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
        who = _identity_pt(await client.identity())
        where = f"{self._settings.host}:{self._settings.port}"
        self._detail_pt = f"Sessão aberta com {where}" + (f": {who}" if who else "")

    async def disconnect(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            client.close()
            self._detail_pt = "Desconectado"

    async def read(self, plan: ReadPlan) -> RawFrame:
        client = self._client
        if client is None or not client.connected:
            raise DriverConnectError(f"{self._profile.id}: leitura sem sessão aberta")
        blocks: dict[str, RawBlock] = {}
        frame_t0 = self._clock.monotonic_ns()
        try:
            for block in plan.blocks:
                meta = block.meta
                try:
                    cls, inst, attr = (
                        int(meta["class"]),
                        int(meta["instance"]),
                        int(meta["attribute"]),
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    raise DriverReadError(
                        f"bloco {block.block_id}: sem classe/instância/atributo"
                    ) from exc
                t0 = self._clock.monotonic_ns()
                data = await client.read_attribute(cls, inst, attr)
                if len(data) < block.count:
                    raise DriverReadError(
                        f"atributo {cls}/{inst}/{attr} devolveu {len(data)} bytes; o mapping usa "
                        f"até o byte {block.count}"
                    )
                now_mono = self._clock.monotonic_ns()
                blocks[block.block_id] = RawBlock(
                    block_id=block.block_id,
                    payload=data,
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
            protocol="ethernet_ip",
            support_state=DriverSupportState.EXPERIMENTAL,
            library="forja (cliente CIP mínimo)",
            library_version="",
            read_areas=("attribute",),
            max_block_size=None,
            supports_device_identification=True,
            note_pt=EXPERIMENTAL_NOTE_PT,
        )
