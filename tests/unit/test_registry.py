"""DriverRegistry: simulator AVAILABLE, modbus/eip UNSUPPORTED honestos, recusa escrita."""

from __future__ import annotations

import pytest

from forja.domain import (
    DriverCapabilities,
    DriverError,
    DriverHealth,
    DriverSupportState,
    RawFrame,
    ReadOnlyContractViolation,
    ReadOnlyDriverBase,
    ReadPlan,
    UnsupportedDriver,
)
from forja.drivers import SimulatorDriver, build_default_registry, equipment_support_state
from forja.drivers.registry import DriverRegistry, DriverSupportInfo
from forja.drivers.support import UNSUPPORTED_REASON_PT, probe_ethernet_ip, probe_modbus_tcp
from forja.infra.clock import FakeClock
from tests.unit.block1_helpers import load_sim_mapping, sim_profile

pytestmark = pytest.mark.unit

EXPECTED_REASON_PT = "Disponível na fase J/K; requer configuração de campo"


def _probe(name: str, state: DriverSupportState = DriverSupportState.AVAILABLE):
    def probe() -> DriverSupportInfo:
        return DriverSupportInfo(name=name, state=state)

    return probe


def test_default_registry_names() -> None:
    assert set(build_default_registry().names()) == {"simulator", "modbus_tcp", "ethernet_ip"}


def test_support_states_are_honest() -> None:
    support = build_default_registry().support()
    assert support["simulator"].state is DriverSupportState.AVAILABLE
    for name in ("modbus_tcp", "ethernet_ip"):
        info = support[name]
        assert info.name == name
        assert info.state is DriverSupportState.UNSUPPORTED
        assert info.reason_pt == EXPECTED_REASON_PT == UNSUPPORTED_REASON_PT
    assert probe_modbus_tcp().state is DriverSupportState.UNSUPPORTED
    assert probe_ethernet_ip().state is DriverSupportState.UNSUPPORTED


def test_create_simulator_returns_driver() -> None:
    registry = build_default_registry()
    driver = registry.create(sim_profile(), load_sim_mapping(), FakeClock())
    assert isinstance(driver, SimulatorDriver)
    assert driver.name == "simulator"


@pytest.mark.parametrize("name", ["modbus_tcp", "ethernet_ip"])
def test_create_unsupported_driver_raises(name: str) -> None:
    registry = build_default_registry()
    with pytest.raises(UnsupportedDriver, match="fase J/K"):
        registry.create(sim_profile(driver=name), load_sim_mapping(), FakeClock())


def test_create_unknown_name_raises() -> None:
    registry = DriverRegistry()  # vazio: 'simulator' nao registrado
    with pytest.raises(UnsupportedDriver, match="desconhecido"):
        registry.create(sim_profile(), load_sim_mapping(), FakeClock())


def test_register_rejects_class_with_write() -> None:
    class WritingDriver:  # nao herda de ReadOnlyDriverBase de proposito
        name = "writing"

        async def connect(self) -> None: ...

        async def disconnect(self) -> None: ...

        async def read(self, plan: ReadPlan) -> RawFrame: ...

        async def health(self) -> DriverHealth: ...

        def capabilities(self) -> DriverCapabilities: ...

        async def write(self, address: int, value: int) -> None: ...

    with pytest.raises(ReadOnlyContractViolation):
        DriverRegistry().register("writing", WritingDriver, _probe("writing"))


def test_register_rejects_bad_or_duplicate_names() -> None:
    registry = build_default_registry()
    with pytest.raises(ValueError, match="já registrado"):
        registry.register("simulator", SimulatorDriver, _probe("simulator"))
    with pytest.raises(ValueError, match="inválido"):
        registry.register("Modbus TCP", SimulatorDriver, _probe("x"))


def test_create_rejects_factory_returning_object_with_write() -> None:
    class Sneaky(SimulatorDriver):
        pass

    def factory(profile, mapping, clock):
        driver = Sneaky(profile, mapping, clock)
        driver.write_register = lambda *_: None  # type: ignore[attr-defined]
        return driver

    registry = DriverRegistry()
    registry.register("simulator", factory, _probe("simulator"))
    with pytest.raises(ReadOnlyContractViolation, match="write_register"):
        registry.create(sim_profile(), load_sim_mapping(), FakeClock())


def test_create_rejects_factory_returning_non_driver() -> None:
    registry = DriverRegistry()
    registry.register("simulator", lambda *_: object(), _probe("simulator"))
    with pytest.raises(ReadOnlyContractViolation, match="não é ReadOnlyDriverBase"):
        registry.create(sim_profile(), load_sim_mapping(), FakeClock())


def test_create_rejects_driver_with_mismatched_name() -> None:
    class Renamed(SimulatorDriver):
        name = "outro"

    registry = DriverRegistry()
    registry.register("simulator", Renamed, _probe("simulator"))
    with pytest.raises(DriverError, match="name="):
        registry.create(sim_profile(), load_sim_mapping(), FakeClock())


def test_base_class_refuses_subclass_with_write_at_definition() -> None:
    with pytest.raises(ReadOnlyContractViolation, match="read-only"):

        class Bad(ReadOnlyDriverBase):
            name = "bad"

            async def write(self, address: int, value: int) -> None: ...


def test_equipment_support_state_rules() -> None:
    available = DriverSupportInfo(name="modbus_tcp", state=DriverSupportState.AVAILABLE)
    unsupported = DriverSupportInfo(name="modbus_tcp", state=DriverSupportState.UNSUPPORTED)
    sim = sim_profile()
    mb_unknown_ip = sim_profile(driver="modbus_tcp")
    mb_configured = sim_profile(driver="modbus_tcp", ip="127.0.0.1", protocol="modbus_tcp")
    assert equipment_support_state(available, sim) is DriverSupportState.AVAILABLE
    assert (
        equipment_support_state(available, mb_unknown_ip) is DriverSupportState.NEEDS_CONFIGURATION
    )
    assert equipment_support_state(available, mb_configured) is DriverSupportState.AVAILABLE
    assert equipment_support_state(unsupported, mb_configured) is DriverSupportState.UNSUPPORTED


def test_support_info_is_frozen_and_strict() -> None:
    info = DriverSupportInfo(name="x", state=DriverSupportState.AVAILABLE)
    with pytest.raises(ValueError):
        info.state = DriverSupportState.UNSUPPORTED  # type: ignore[misc]
    with pytest.raises(ValueError):
        DriverSupportInfo(
            name="x",
            state=DriverSupportState.AVAILABLE,
            extra="n",  # type: ignore[call-arg]
        )
