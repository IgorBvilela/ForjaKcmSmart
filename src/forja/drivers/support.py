"""Estado de suporte de cada driver. Nunca AVAILABLE sem driver funcional.

modbus_tcp e ethernet_ip ficam UNSUPPORTED ate as fases J/K e ate haver configuracao de campo.
"""

from __future__ import annotations

from importlib import metadata

from pydantic import BaseModel, ConfigDict

from forja.domain.assets import EquipmentProfile
from forja.domain.ports import DriverSupportState
from forja.version import __version__

UNSUPPORTED_REASON_PT = "Disponível na fase J/K; requer configuração de campo"


class DriverSupportInfo(BaseModel):
    """O que a tela de Comunicacao mostra por driver."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    state: DriverSupportState
    library: str = ""
    version: str = ""
    reason_pt: str = ""


def library_version(distribution: str) -> str:
    """Versao instalada de uma biblioteca, ou '' se ausente. Nao importa a biblioteca."""
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return ""


def probe_simulator() -> DriverSupportInfo:
    return DriverSupportInfo(
        name="simulator",
        state=DriverSupportState.AVAILABLE,
        library="forja",
        version=__version__,
        reason_pt="Dados simulados; nenhum valor representa um KCM real.",
    )


MODBUS_EXPERIMENTAL_PT = (
    "Driver somente leitura implementado e testado contra servidor Modbus de teste local. "
    "Validação no KCM real pendente: o protocolo da interface Host/Anybus precisa ser confirmado "
    "em campo."
)


def probe_modbus_tcp() -> DriverSupportInfo:
    """EXPERIMENTAL: existe e é testado, mas nunca foi validado contra o KCM real."""
    version = library_version("pymodbus")
    if not version:
        return DriverSupportInfo(
            name="modbus_tcp",
            state=DriverSupportState.UNSUPPORTED,
            library="pymodbus",
            reason_pt="Biblioteca pymodbus não instalada nesta máquina.",
        )
    return DriverSupportInfo(
        name="modbus_tcp",
        state=DriverSupportState.EXPERIMENTAL,
        library="pymodbus",
        version=version,
        reason_pt=MODBUS_EXPERIMENTAL_PT,
    )


def probe_ethernet_ip() -> DriverSupportInfo:
    return DriverSupportInfo(
        name="ethernet_ip",
        state=DriverSupportState.UNSUPPORTED,
        library="",
        version="",
        reason_pt=UNSUPPORTED_REASON_PT,
    )


def equipment_support_state(
    info: DriverSupportInfo, profile: EquipmentProfile
) -> DriverSupportState:
    """Por equipamento: UNSUPPORTED vence; depois NEEDS_CONFIGURATION (ip ou protocolo UNKNOWN)."""
    if info.state is DriverSupportState.UNSUPPORTED:
        return DriverSupportState.UNSUPPORTED
    if profile.communication.needs_configuration:
        return DriverSupportState.NEEDS_CONFIGURATION
    return info.state
