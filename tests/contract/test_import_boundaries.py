"""Contrato de fronteiras de import.

- Bibliotecas de protocolo (pymodbus, pycomm3, cpppo, pylogix) só em src/forja/drivers/*/_client.py.
- O domínio não importa web, banco, YAML nem protocolo.
- API e CLI não leem relógio direto (time.time/monotonic, datetime.now/utcnow): só pela porta Clock.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.contract

SRC = Path(__file__).resolve().parents[2] / "src" / "forja"

PROTOCOL_LIBS = frozenset({"pymodbus", "pycomm3", "cpppo", "pylogix"})
CLIENT_FILE = re.compile(r"^drivers/[^/]+/_client\.py$")

DOMAIN_FORBIDDEN = frozenset(
    {"fastapi", "starlette", "uvicorn", "sqlite3", "yaml", "httpx", "sse_starlette", *PROTOCOL_LIBS}
)
DOMAIN_ALLOWED_FORJA = frozenset({"forja.domain", "forja.version"})

CLOCK_CALLS = {
    ("time", "time"),
    ("time", "monotonic"),
    ("time", "monotonic_ns"),
    ("datetime", "now"),
    ("datetime", "utcnow"),
}


def _py_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _imports(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def _top(name: str) -> str:
    return name.split(".", 1)[0]


def test_protocol_libraries_only_in_driver_clients() -> None:
    offenders: list[str] = []
    for path in _py_files(SRC):
        rel = path.relative_to(SRC).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        used = {n for n in _imports(tree) if _top(n) in PROTOCOL_LIBS}
        if used and not CLIENT_FILE.match(rel):
            offenders.append(f"{rel}: {sorted(used)}")
    assert offenders == []


def test_domain_is_pure() -> None:
    stdlib = set(sys.stdlib_module_names)
    offenders: list[str] = []
    for path in _py_files(SRC / "domain"):
        rel = path.relative_to(SRC).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for name in _imports(tree):
            top = _top(name)
            if top in DOMAIN_FORBIDDEN:
                offenders.append(f"{rel}: {name}")
            elif top == "forja" and not any(
                name == a or name.startswith(a + ".") for a in DOMAIN_ALLOWED_FORJA
            ):
                offenders.append(f"{rel}: {name}")
            elif top not in stdlib and top not in {"forja", "pydantic", "typing_extensions"}:
                offenders.append(f"{rel}: {name}")
    assert offenders == []


def _direct_clock_calls(tree: ast.AST) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            if (func.value.id, func.attr) in CLOCK_CALLS:
                found.append(f"linha {node.lineno}: {func.value.id}.{func.attr}()")
    return found


@pytest.mark.parametrize("package", ["api", "tools"])
def test_api_and_cli_use_clock_port_only(package: str) -> None:
    offenders: list[str] = []
    for path in _py_files(SRC / package):
        rel = path.relative_to(SRC).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offenders.extend(f"{rel} {hit}" for hit in _direct_clock_calls(tree))
    assert offenders == []


def test_api_does_not_import_protocol_or_sqlite() -> None:
    offenders: list[str] = []
    for path in _py_files(SRC / "api"):
        rel = path.relative_to(SRC).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        bad = {
            n for n in _imports(tree) if _top(n) in PROTOCOL_LIBS or n.startswith("forja.historian")
        }
        if bad:
            offenders.append(f"{rel}: {sorted(bad)}")
    assert offenders == []
