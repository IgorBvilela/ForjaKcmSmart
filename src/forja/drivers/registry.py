"""Registro de drivers. Cria o driver certo para um perfil e recusa qualquer um com escrita.

Checagem estrutural em dois pontos: no `register` (quando a factory e a propria classe) e no
`create` (na instancia devolvida). Superficie publica permitida: ALLOWED_DRIVER_PUBLIC.
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable
from dataclasses import dataclass

from forja.domain.assets import EquipmentProfile
from forja.domain.errors import DriverError, ReadOnlyContractViolation, UnsupportedDriver
from forja.domain.mapping import Mapping
from forja.domain.ports import (
    ALLOWED_DRIVER_PUBLIC,
    FORBIDDEN_DRIVER_METHOD,
    Clock,
    DriverSupportState,
    ReadOnlyDriverBase,
)
from forja.drivers.simulator.driver import SimulatorDriver
from forja.drivers.support import (
    UNSUPPORTED_REASON_PT,
    DriverSupportInfo,
    probe_ethernet_ip,
    probe_modbus_tcp,
    probe_simulator,
)

DriverFactory = Callable[[EquipmentProfile, Mapping, Clock], ReadOnlyDriverBase]
DriverProbe = Callable[[], DriverSupportInfo]

__all__ = [
    "DriverFactory",
    "DriverProbe",
    "DriverRegistry",
    "DriverSupportInfo",
    "build_default_registry",
    "public_surface",
]

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


def public_surface(target: object) -> frozenset[str]:
    """Nomes publicos (sem underscore) de uma classe ou instancia, herdados inclusive."""
    return frozenset(n for n in dir(target) if not n.startswith("_"))


def _check_surface(label: str, surface: frozenset[str]) -> None:
    extra = sorted(surface - ALLOWED_DRIVER_PUBLIC)
    forbidden = sorted(n for n in surface if FORBIDDEN_DRIVER_METHOD.match(n))
    if extra or forbidden:
        raise ReadOnlyContractViolation(
            f"{label}: superfície pública fora do contrato read-only: "
            f"extra={extra} proibidos={forbidden}; permitido={sorted(ALLOWED_DRIVER_PUBLIC)}"
        )


def _check_driver_class(cls: type) -> None:
    if not issubclass(cls, ReadOnlyDriverBase):
        raise ReadOnlyContractViolation(f"{cls.__name__}: driver deve herdar de ReadOnlyDriverBase")
    _check_surface(cls.__name__, public_surface(cls))


def _check_driver_instance(driver: object) -> ReadOnlyDriverBase:
    if not isinstance(driver, ReadOnlyDriverBase):
        raise ReadOnlyContractViolation(
            f"{type(driver).__name__}: factory devolveu objeto que não é ReadOnlyDriverBase"
        )
    _check_surface(type(driver).__name__, public_surface(driver))
    return driver


@dataclass(frozen=True)
class _Registration:
    factory: DriverFactory
    probe: DriverProbe


class DriverRegistry:
    """Nome do driver -> (factory, probe). O nome vem de `profile.communication.driver`."""

    def __init__(self) -> None:
        self._regs: dict[str, _Registration] = {}

    def register(self, name: str, factory: DriverFactory, probe: DriverProbe) -> None:
        if not _NAME_RE.match(name):
            raise ValueError(f"nome de driver inválido: {name!r}")
        if name in self._regs:
            raise ValueError(f"driver já registrado: {name!r}")
        if inspect.isclass(factory):
            _check_driver_class(factory)
        self._regs[name] = _Registration(factory=factory, probe=probe)

    def names(self) -> list[str]:
        return list(self._regs)

    def support(self) -> dict[str, DriverSupportInfo]:
        return {name: reg.probe() for name, reg in self._regs.items()}

    def create(
        self, profile: EquipmentProfile, mapping: Mapping, clock: Clock
    ) -> ReadOnlyDriverBase:
        """UnsupportedDriver se o nome for desconhecido ou o driver estiver UNSUPPORTED."""
        name = profile.communication.driver
        reg = self._regs.get(name)
        if reg is None:
            raise UnsupportedDriver(f"driver desconhecido: {name!r}")
        info = reg.probe()
        if info.state is DriverSupportState.UNSUPPORTED:
            raise UnsupportedDriver(info.reason_pt or f"driver {name!r} não suportado")
        driver = _check_driver_instance(reg.factory(profile, mapping, clock))
        if driver.name != name:
            raise DriverError(f"driver {name!r} devolveu instância com name={driver.name!r}")
        return driver


def _unsupported_factory(name: str) -> DriverFactory:
    """Factory que nunca cria nada: segunda barreira para drivers ainda nao implementados."""

    def _factory(
        _profile: EquipmentProfile, _mapping: Mapping, _clock: Clock
    ) -> ReadOnlyDriverBase:
        raise UnsupportedDriver(f"driver {name!r}: {UNSUPPORTED_REASON_PT}")

    return _factory


def build_default_registry() -> DriverRegistry:
    """simulator AVAILABLE; modbus_tcp e ethernet_ip UNSUPPORTED ate as fases J/K."""
    registry = DriverRegistry()
    registry.register("simulator", SimulatorDriver, probe_simulator)
    registry.register("modbus_tcp", _unsupported_factory("modbus_tcp"), probe_modbus_tcp)
    registry.register("ethernet_ip", _unsupported_factory("ethernet_ip"), probe_ethernet_ip)
    return registry
