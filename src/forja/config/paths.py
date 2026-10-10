"""Resolucao de caminhos.

Desenvolvimento: tudo mora na raiz do repositorio. Empacotado (PyInstaller): o padrao e
%ProgramData%/ForjaKCM, com config/, knowledge/ e var/ (bancos, logs, backups) separados da pasta
do programa. Atualizar o programa nao toca nos dados nem na configuracao.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

PRODUCT_DIR = "ForjaKCM"


@dataclass(frozen=True)
class ForjaPaths:
    home: Path
    config_dir: Path
    knowledge_dir: Path
    data_dir: Path
    logs_dir: Path
    backups_dir: Path

    @property
    def equipment_dir(self) -> Path:
        return self.config_dir / "equipment"

    @property
    def mappings_dir(self) -> Path:
        return self.config_dir / "mappings"

    @property
    def rules_dir(self) -> Path:
        return self.config_dir / "rules"

    @property
    def alarms_dir(self) -> Path:
        return self.config_dir / "alarms"

    @property
    def stop_by_dir(self) -> Path:
        return self.config_dir / "stop_by"

    @property
    def forja_yaml(self) -> Path:
        return self.config_dir / "forja.yaml"

    @property
    def core_db(self) -> Path:
        return self.data_dir / "forja_core.db"

    @property
    def historian_db(self) -> Path:
        return self.data_dir / "forja_historian.db"

    def ensure(self) -> ForjaPaths:
        for p in (self.data_dir, self.logs_dir, self.backups_dir):
            p.mkdir(parents=True, exist_ok=True)
        return self


def find_repo_root(start: Path | None = None) -> Path:
    here = (start or Path(__file__)).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "pyproject.toml").exists() and (candidate / "config").is_dir():
            return candidate
    return Path.cwd()


def is_frozen() -> bool:
    """Rodando a partir do executavel empacotado."""
    return bool(getattr(sys, "frozen", False))


def default_home() -> Path:
    """Empacotado: %ProgramData%/ForjaKCM. Desenvolvimento: raiz do repositorio."""
    if is_frozen():
        base = os.environ.get("PROGRAMDATA") or os.path.join(
            os.environ.get("SystemDrive", "C:") + os.sep, "ProgramData"
        )
        return Path(base) / PRODUCT_DIR
    return find_repo_root()


def resolve_paths(
    home: str | os.PathLike[str] | None = None, data_dir: str | None = None
) -> ForjaPaths:
    """argumento > FORJA_HOME (env) > padrao (ProgramData empacotado, repositorio em dev)."""
    env_home = os.environ.get("FORJA_HOME")
    root = Path(home) if home else (Path(env_home) if env_home else default_home())
    root = root.resolve()
    data = Path(data_dir) if data_dir else Path(os.environ.get("FORJA_DATA_DIR", root / "var"))
    if not data.is_absolute():
        data = root / data
    return ForjaPaths(
        home=root,
        config_dir=root / "config",
        knowledge_dir=root / "knowledge",
        data_dir=data,
        logs_dir=data / "logs",
        backups_dir=data / "backups",
    )
