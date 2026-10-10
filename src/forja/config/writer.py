"""Gravação da configuração editável (perfil de equipamento e mapping) em YAML.

- Valida tudo pelo domínio antes de tocar no disco (inclusive objeto montado sem validação).
- Conflito: o perfil é comparado pelo hash do conteúdo atual; o mapping, pelo número da versão.
  Quem salva informa o que viu; se o arquivo mudou no meio do caminho, nada é gravado.
- Troca atômica: arquivo temporário no mesmo diretório + ``os.replace``.
- A versão anterior, com o texto original (comentários inclusive), vai para
  ``config/_history/<tipo>/``. O ConfigStore não lê essa pasta.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import yaml
from pydantic import BaseModel, ValidationError

from forja.config.loader import load_mapping, load_profile
from forja.config.paths import ForjaPaths
from forja.domain.assets import EquipmentProfile
from forja.domain.errors import ConfigError, MappingValidationError
from forja.domain.mapping import Mapping

HISTORY_DIR_NAME: Final[str] = "_history"
_SAFE_STEM = re.compile(r"^[a-z0-9][a-z0-9_\-]{1,63}$")


class ConfigConflict(ConfigError):
    """A configuração mudou desde que foi lida. Recarregue antes de salvar."""


def config_hash(model: BaseModel) -> str:
    """sha256 do conteúdo canônico (JSON ordenado). Identifica a versão vista pela tela."""
    canonical = json.dumps(model.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SavedProfile:
    profile: EquipmentProfile
    path: Path
    config_hash: str
    previous_path: Path | None


@dataclass(frozen=True)
class SavedMapping:
    mapping: Mapping
    path: Path
    previous_path: Path | None


def _fmt(exc: ValidationError) -> str:
    return "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())


def _stamp(now: datetime) -> str:
    return now.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


class ConfigWriter:
    """Grava perfis em ``config/equipment`` e mappings em ``config/mappings``."""

    def __init__(self, paths: ForjaPaths) -> None:
        self._paths = paths

    @property
    def history_dir(self) -> Path:
        return self._paths.config_dir / HISTORY_DIR_NAME

    # ------------------------------------------------------------------ localizar

    def find_profile_file(self, equipment_id: str) -> Path | None:
        """Arquivo cujo `id` é equipment_id (o nome do arquivo não manda)."""
        for path in sorted(self._paths.equipment_dir.glob("*.yaml")):
            if path.name.startswith("_"):
                continue
            with contextlib.suppress(ConfigError):
                if load_profile(path).id == equipment_id:
                    return path
        return None

    def find_mapping_file(self, mapping_id: str) -> Path | None:
        for path in sorted(self._paths.mappings_dir.glob("*.yaml")):
            if path.name.startswith("_"):
                continue
            with contextlib.suppress(ConfigError):
                if load_mapping(path).mapping_id == mapping_id:
                    return path
        return None

    # ------------------------------------------------------------------ perfil

    def save_profile(
        self, profile: EquipmentProfile, *, expected_hash: str | None, now: datetime
    ) -> SavedProfile:
        try:
            checked = EquipmentProfile.model_validate(profile.model_dump(mode="json"))
        except ValidationError as exc:
            raise ConfigError(f"perfil inválido: {_fmt(exc)}") from exc
        path = self.find_profile_file(checked.id)
        if path is None:
            if expected_hash is not None:
                raise ConfigConflict(f"perfil {checked.id} não existe mais no disco")
            path = self._target(self._paths.equipment_dir, checked.id.lower())
            previous = None
        else:
            current = load_profile(path)
            if expected_hash is None or expected_hash != config_hash(current):
                raise ConfigConflict(
                    f"perfil {checked.id} mudou desde a leitura; recarregue a tela antes de salvar"
                )
            previous = self._archive(path, "equipment", now)
        self._atomic_dump(path, checked.model_dump(mode="json"), "perfil de equipamento", now)
        return SavedProfile(
            profile=checked, path=path, config_hash=config_hash(checked), previous_path=previous
        )

    # ------------------------------------------------------------------ mapping

    def save_mapping(
        self, mapping: Mapping, *, expected_version: int | None, now: datetime
    ) -> SavedMapping:
        try:
            checked = Mapping.model_validate(mapping.model_dump(mode="json"))
        except ValidationError as exc:
            raise MappingValidationError(f"mapping inválido: {_fmt(exc)}") from exc
        path = self.find_mapping_file(checked.mapping_id)
        if path is None:
            if expected_version is not None:
                raise ConfigConflict(f"mapping {checked.mapping_id} não existe mais no disco")
            path = self._target(self._paths.mappings_dir, checked.mapping_id)
            version = checked.version
            previous = None
        else:
            current = load_mapping(path)
            if expected_version != current.version:
                raise ConfigConflict(
                    f"mapping {checked.mapping_id} está na versão {current.version}; a tela "
                    f"editou a versão {expected_version}. Recarregue antes de salvar."
                )
            version = current.version + 1
            previous = self._archive(path, "mappings", now)
        saved = checked.model_copy(update={"version": version})
        self._atomic_dump(path, saved.model_dump(mode="json"), "mapping", now)
        return SavedMapping(mapping=saved, path=path, previous_path=previous)

    # ------------------------------------------------------------------ disco

    def _target(self, directory: Path, stem: str) -> Path:
        if not _SAFE_STEM.match(stem):
            raise ConfigError(f"identificador impróprio para nome de arquivo: {stem!r}")
        path = (directory / f"{stem}.yaml").resolve()
        if path.parent != directory.resolve():
            raise ConfigError(f"caminho fora da pasta de configuração: {stem!r}")
        return path

    def _archive(self, path: Path, kind: str, now: datetime) -> Path:
        folder = self.history_dir / kind
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{path.stem}__{_stamp(now)}.yaml"
        n = 1
        while target.exists():
            n += 1
            target = folder / f"{path.stem}__{_stamp(now)}_{n}.yaml"
        target.write_bytes(path.read_bytes())
        return target

    def _atomic_dump(self, path: Path, data: dict[str, Any], what: str, now: datetime) -> None:
        header = (
            f"# {what.capitalize()} gravado pela tela Comunicação KCM da Forja "
            f"({now.astimezone(UTC).isoformat()}).\n"
            f"# A versão anterior, com os comentários originais, fica em "
            f"config/{HISTORY_DIR_NAME}/.\n"
        )
        body = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=path.parent)
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(header)
                fh.write(body)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        finally:
            if tmp.exists():
                tmp.unlink()


__all__ = [
    "HISTORY_DIR_NAME",
    "ConfigConflict",
    "ConfigWriter",
    "SavedMapping",
    "SavedProfile",
    "config_hash",
]
