"""Nomes proibidos em `src/forja/drivers/**` e a varredura AST que os procura.

Qualquer identificador (def, class, atributo, nome, argumento, import) cujo segmento comece
com um destes tokens e violacao do contrato read-only. A lista e a do CONTRATOS_A1 (Bloco 1).

ALLOWLIST: o proprio contrato nomeia `SimulatorControlRegistry.set_scenario` e `set_overrides`
(blocos 3 e 5 chamam esses nomes). Eles mudam o CENARIO do simulador, nunca um dispositivo, e
vivem fora do driver. Sao as unicas excecoes, amarradas ao arquivo exato. Qualquer outro
`set_*` em qualquer arquivo de drivers, inclusive no driver, e violacao.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

FORBIDDEN_TOKENS: tuple[str, ...] = ("write", "set_", "reset", "tare", "span", "calib")
"""Prefixos de segmento proibidos (case-insensitive). `write*`, `set_*`, `reset*`, `tare*`..."""

FORBIDDEN_IDENTIFIER = re.compile(
    r"(?:^|_)(?:" + "|".join(re.escape(tok) for tok in FORBIDDEN_TOKENS) + r")",
    re.IGNORECASE,
)

ALLOWLIST: frozenset[tuple[str, str]] = frozenset(
    {
        ("forja/drivers/simulator/controls.py", "set_scenario"),
        ("forja/drivers/simulator/controls.py", "set_overrides"),
    }
)
"""(caminho relativo a src/, identificador). Ver docstring do modulo."""

DRIVERS_REL = Path("forja") / "drivers"


@dataclass(frozen=True)
class Violation:
    path: str
    lineno: int
    kind: str
    name: str

    def __str__(self) -> str:
        return f"{self.path}:{self.lineno} {self.kind} {self.name!r}"


def is_forbidden_name(name: str) -> bool:
    return FORBIDDEN_IDENTIFIER.search(name) is not None


def _identifiers(node: ast.AST) -> list[tuple[str, str]]:
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        return [("def", node.name)]
    if isinstance(node, ast.ClassDef):
        return [("class", node.name)]
    if isinstance(node, ast.Attribute):
        return [("attr", node.attr)]
    if isinstance(node, ast.Name):
        return [("name", node.id)]
    if isinstance(node, ast.arg):
        return [("arg", node.arg)]
    if isinstance(node, ast.keyword) and node.arg is not None:
        return [("kwarg", node.arg)]
    if isinstance(node, ast.alias):
        # nome original importado E apelido: `from x import write_regs as w` e violacao
        names = [("import", part) for part in node.name.split(".")]
        if node.asname:
            names.append(("import", node.asname))
        return names
    return []


def scan_source(source: str, rel_path: str) -> list[Violation]:
    """Varre o codigo de um modulo. `rel_path` em POSIX relativo a src/ (chave da ALLOWLIST)."""
    tree = ast.parse(source, filename=rel_path)
    found: list[Violation] = []
    for node in ast.walk(tree):
        for kind, name in _identifiers(node):
            if is_forbidden_name(name) and (rel_path, name) not in ALLOWLIST:
                found.append(Violation(rel_path, getattr(node, "lineno", 0), kind, name))
    return sorted(found, key=lambda v: (v.path, v.lineno, v.name))


def scan_tree(root: Path, rel_to: Path) -> list[Violation]:
    """Varre todos os .py abaixo de `root`; caminhos relativos a `rel_to` (normalmente src/)."""
    found: list[Violation] = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(rel_to).as_posix()
        found.extend(scan_source(path.read_text(encoding="utf-8"), rel))
    return found
