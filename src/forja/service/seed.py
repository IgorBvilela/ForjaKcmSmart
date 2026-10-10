"""Preparação da pasta de dados (comando `forja init`).

Copia a semente (config/ e knowledge/) para a pasta de dados SÓ onde o arquivo ainda não existe e
cria var/, var/logs e var/backups. Nunca sobrescreve: a configuração ajustada em campo e o
historiador sobrevivem a qualquer atualização do programa.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from forja.config.paths import find_repo_root, is_frozen

SEED_FOLDERS: tuple[str, ...] = ("config", "knowledge")


def seed_source() -> Path:
    """Onde está a semente: dentro do executável empacotado, ou a raiz do repositório."""
    if is_frozen():
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        return base / "seed"
    return find_repo_root()


def seed_home(home: Path, source: Path | None = None) -> list[str]:
    """Copia os arquivos que faltam e cria as pastas de dados. Devolve o que foi criado."""
    src = source or seed_source()
    if not all((src / folder).is_dir() for folder in SEED_FOLDERS):
        raise FileNotFoundError(f"semente de configuração não encontrada em {src}")
    created: list[str] = []
    for folder in SEED_FOLDERS:
        for item in sorted((src / folder).rglob("*")):
            if not item.is_file() or {"_history", "_archive"} & set(item.parts):
                continue
            rel = item.relative_to(src)
            target = home / rel
            if target.exists() or _archived(home, rel):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            created.append(rel.as_posix())
    for folder in ("var", "var/logs", "var/backups"):
        (home / folder).mkdir(parents=True, exist_ok=True)
    return created


def _archived(home: Path, rel: Path) -> bool:
    """Perfil da semente que o usuário arquivou não volta numa atualização."""
    if rel.parts[:2] != ("config", "equipment"):
        return False
    archive = home / "config" / "_archive" / "equipment"
    return archive.is_dir() and any(archive.glob(f"{rel.stem}__*.yaml"))


__all__ = ["SEED_FOLDERS", "seed_home", "seed_source"]
