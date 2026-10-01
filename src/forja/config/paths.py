"""Resolucao de caminhos. Em desenvolvimento tudo mora na raiz do repositorio;
em producao a semente e copiada para %ProgramData%\\ForjaKCM (fase N)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


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


def resolve_paths(home: str | os.PathLike[str] | None = None, data_dir: str | None = None) -> ForjaPaths:
    """FORJA_HOME (env) > argumento > raiz do repositorio."""
    env_home = os.environ.get("FORJA_HOME")
    root = Path(home) if home else (Path(env_home) if env_home else find_repo_root())
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
