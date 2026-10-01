"""Contrato read-only dos drivers: superficie publica, base que recusa escrita, varredura AST."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from forja.domain import (
    DriverSupportState,
    ReadOnlyContractViolation,
    ReadOnlyDriver,
    ReadOnlyDriverBase,
    UnsupportedDriver,
)
from forja.domain.ports import ALLOWED_DRIVER_PUBLIC
from forja.drivers import SimulatorDriver, build_default_registry
from forja.drivers.registry import public_surface
from forja.infra.clock import FakeClock
from tests.contract.forbidden_tokens import (
    ALLOWLIST,
    DRIVERS_REL,
    FORBIDDEN_TOKENS,
    Violation,
    is_forbidden_name,
    scan_source,
    scan_tree,
)
from tests.unit.block1_helpers import load_sim_mapping, sim_profile

pytestmark = [pytest.mark.contract, pytest.mark.readonly]

CONTRACT_SURFACE = frozenset({"name", "connect", "disconnect", "read", "health", "capabilities"})
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"
DRIVERS_DIR = SRC / DRIVERS_REL
NORMALIZATION_DIR = SRC / "forja" / "normalization"

DIRECT_CLOCK_CALLS: frozenset[tuple[str, str]] = frozenset(
    {
        ("time", "time"),
        ("time", "monotonic"),
        ("time", "monotonic_ns"),
        ("time", "perf_counter"),
        ("time", "perf_counter_ns"),
        ("time", "sleep"),
        ("datetime", "now"),
        ("datetime", "utcnow"),
        ("asyncio", "sleep"),
    }
)


def _all_driver_classes() -> list[type[ReadOnlyDriverBase]]:
    found: list[type[ReadOnlyDriverBase]] = []
    stack = list(ReadOnlyDriverBase.__subclasses__())
    while stack:
        cls = stack.pop()
        if cls not in found:
            found.append(cls)
            stack.extend(cls.__subclasses__())
    return found


# --- superficie publica ---------------------------------------------------------------------


def test_contract_surface_matches_domain_constant() -> None:
    assert ALLOWED_DRIVER_PUBLIC == CONTRACT_SURFACE


def test_simulator_driver_is_a_known_driver_class() -> None:
    assert SimulatorDriver in _all_driver_classes()


@pytest.mark.parametrize("cls", _all_driver_classes(), ids=lambda c: c.__name__)
def test_every_driver_class_exposes_exactly_the_contract(cls: type[ReadOnlyDriverBase]) -> None:
    assert public_surface(cls) == CONTRACT_SURFACE
    # nem metodo "privado" com nome de escrita
    private = [n for n in dir(cls) if n.startswith("_") and not n.startswith("__")]
    assert [n for n in private if is_forbidden_name(n.lstrip("_"))] == []


def test_every_registered_driver_instance_or_refusal() -> None:
    registry = build_default_registry()
    mapping = load_sim_mapping()
    clock = FakeClock()
    seen_available = 0
    for name, info in registry.support().items():
        profile = sim_profile(f"CONTRATO_{name.upper()}", driver=name)
        if info.state is DriverSupportState.UNSUPPORTED:
            with pytest.raises(UnsupportedDriver):
                registry.create(profile, mapping, clock)
            continue
        driver = registry.create(profile, mapping, clock)
        seen_available += 1
        assert isinstance(driver, ReadOnlyDriverBase)
        assert isinstance(driver, ReadOnlyDriver)
        assert public_surface(driver) == CONTRACT_SURFACE
        assert driver.name == name
    assert seen_available == 1  # hoje so o simulador; nunca AVAILABLE sem driver funcional


# --- base recusa escrita na definicao ------------------------------------------------------


@pytest.mark.parametrize(
    "method",
    [
        "write",
        "write_register",
        "write_single_coil",
        "set_setpoint",
        "reset",
        "tare",
        "span",
        "calib",
        "calibrate",
        "start",
        "stop",
        "command",
        "send_command",
        "apply",
        "ajustar",  # nome inocente mas fora da superficie permitida
    ],
)
def test_base_refuses_subclass_with_extra_public_method(method: str) -> None:
    async def _noop(self, *args, **kwargs) -> None: ...

    with pytest.raises(ReadOnlyContractViolation):
        type("Rebelde", (ReadOnlyDriverBase,), {"name": "rebelde", method: _noop})


def test_base_refuses_write_attribute_even_if_not_callable() -> None:
    with pytest.raises(ReadOnlyContractViolation):
        type("Rebelde2", (ReadOnlyDriverBase,), {"name": "r2", "write": None})


def test_base_accepts_private_helpers() -> None:
    cls = type(
        "Comportado",
        (ReadOnlyDriverBase,),
        {"name": "ok", "_buffer": None, "_helper": lambda *_: None},
    )
    assert public_surface(cls) == CONTRACT_SURFACE


# --- varredura AST ------------------------------------------------------------------------------


def test_forbidden_token_list_is_the_contract_list() -> None:
    assert set(FORBIDDEN_TOKENS) == {"write", "set_", "reset", "tare", "span", "calib"}


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("write", True),
        ("write_register", True),
        ("WriteRegister", True),
        ("do_write", True),
        ("set_setpoint", True),
        ("_set_value", True),
        ("reset", True),
        ("reset_counter", True),
        ("tare", True),
        ("span", True),
        ("WEIGH_SPAN_M", True),
        ("calib", True),
        ("calibrate", True),
        ("offset", False),
        ("setpoint", False),
        ("setpoint_ref", False),
        ("preset", False),
        ("register", False),
        ("read", False),
        ("set", False),
    ],
)
def test_forbidden_identifier_semantics(name: str, expected: bool) -> None:
    assert is_forbidden_name(name) is expected


def test_drivers_tree_has_no_forbidden_names() -> None:
    assert DRIVERS_DIR.is_dir()
    files = list(DRIVERS_DIR.rglob("*.py"))
    assert len(files) >= 8  # registry, support, __init__ e o pacote simulator
    violations = scan_tree(DRIVERS_DIR, SRC)
    assert violations == [], "\n".join(str(v) for v in violations)


def test_allowlist_is_minimal_and_does_not_rot() -> None:
    assert len(ALLOWLIST) == 2
    for rel, name in ALLOWLIST:
        path = SRC / rel
        assert path.is_file(), rel
        assert rel.startswith(DRIVERS_REL.as_posix())
        assert "/simulator/" in rel  # excecao so no simulador, nunca em driver real
        assert not rel.endswith("driver.py")  # nunca no driver em si
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        defs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        assert name in defs, f"{rel}: {name} saiu do codigo; remova da ALLOWLIST"


def test_scan_catches_planted_violation(tmp_path: Path) -> None:
    planted = tmp_path / "forja" / "drivers" / "plantado" / "driver.py"
    planted.parent.mkdir(parents=True)
    planted.write_text(
        "class FakeDriver:\n"
        "    async def write_register(self, address, value):\n"
        "        return None\n"
        "    def set_setpoint(self, value):\n"
        "        return None\n"
        "    def tare(self):\n"
        "        return None\n"
        "def calibrate(client):\n"
        "    client.write_coil(1, True)\n"
        "def leitura_ok(client):\n"
        "    return client.read_holding_registers(0, 2)\n",
        encoding="utf-8",
    )
    violations = scan_tree(tmp_path / "forja" / "drivers", tmp_path)
    names = {v.name for v in violations}
    assert {"write_register", "set_setpoint", "tare", "calibrate", "write_coil"} <= names
    assert "read_holding_registers" not in names
    assert "leitura_ok" not in names
    assert all(v.path == "forja/drivers/plantado/driver.py" for v in violations)
    assert all(isinstance(v, Violation) for v in violations)
    assert all(v.lineno > 0 for v in violations)


def test_scan_ignores_clean_module_and_catches_imports_and_kwargs() -> None:
    clean = "async def read(plan):\n    return plan\nclass Ok:\n    name = 'ok'\n"
    assert scan_source(clean, "forja/drivers/x.py") == []
    sneaky = (
        "from pymodbus.client import write_registers as escreve\n"
        "def f(client):\n"
        "    return client.read(0, tare_now=True)\n"
    )
    names = {v.name for v in scan_source(sneaky, "forja/drivers/x.py")}
    assert {"write_registers", "tare_now"} <= names
    assert "escreve" not in names


def test_allowlisted_name_outside_its_file_is_still_a_violation() -> None:
    src = "class R:\n    def set_scenario(self, s):\n        return s\n"
    assert scan_source(src, "forja/drivers/simulator/controls.py") == []
    in_driver = scan_source(src, "forja/drivers/simulator/driver.py")
    assert [v.name for v in in_driver] == ["set_scenario"]
    in_registry = scan_source(src, "forja/drivers/registry.py")
    assert [v.name for v in in_registry] == ["set_scenario"]


# --- relogio so pela porta Clock ---------------------------------------------------------------


def _direct_clock_calls(root: Path) -> list[str]:
    found: list[str] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and (node.value.id, node.attr) in DIRECT_CLOCK_CALLS
            ):
                found.append(f"{path.name}:{node.lineno} {node.value.id}.{node.attr}")
    return found


@pytest.mark.parametrize("root", [DRIVERS_DIR, NORMALIZATION_DIR], ids=["drivers", "normalization"])
def test_no_direct_clock_or_sleep_in_block(root: Path) -> None:
    assert _direct_clock_calls(root) == []


def test_clock_detector_catches_planted_call(tmp_path: Path) -> None:
    bad = tmp_path / "forja" / "drivers" / "bad.py"
    bad.parent.mkdir(parents=True)
    bad.write_text("import time\n\ndef f():\n    return time.time()\n", encoding="utf-8")
    hits = _direct_clock_calls(tmp_path / "forja")
    assert len(hits) == 1
    assert hits[0].endswith("time.time")
