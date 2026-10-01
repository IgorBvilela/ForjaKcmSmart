"""Carregamento e validacao de YAML externo. Sempre yaml.safe_load. Nunca yaml.load."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from forja.config.models import ForjaConfig
from forja.config.paths import ForjaPaths, resolve_paths
from forja.domain.alarms import AlarmCatalog, AlarmDefinition, StopByCatalog, StopByEntry
from forja.domain.assets import EquipmentProfile
from forja.domain.errors import ConfigError, MappingValidationError
from forja.domain.mapping import Mapping

MAX_YAML_BYTES = 256 * 1024


def load_yaml_file(path: Path) -> Any:
    if not path.exists():
        raise ConfigError(f"arquivo não encontrado: {path}")
    if path.stat().st_size > MAX_YAML_BYTES:
        raise ConfigError(f"arquivo acima de {MAX_YAML_BYTES} bytes: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _fmt(exc: ValidationError) -> str:
    return "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())


def load_forja_config(path: Path) -> ForjaConfig:
    data = load_yaml_file(path) or {}
    try:
        return ForjaConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"{path.name}: {_fmt(exc)}") from exc


def load_profile(path: Path) -> EquipmentProfile:
    data = load_yaml_file(path)
    try:
        return EquipmentProfile.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"{path.name}: {_fmt(exc)}") from exc


def load_mapping(path: Path) -> Mapping:
    data = load_yaml_file(path)
    try:
        return Mapping.model_validate(data)
    except ValidationError as exc:
        raise MappingValidationError(f"{path.name}: {_fmt(exc)}") from exc


def parse_mapping(data: dict[str, Any]) -> Mapping:
    try:
        return Mapping.model_validate(data)
    except ValidationError as exc:
        raise MappingValidationError(_fmt(exc)) from exc


def load_alarm_catalog(dir_: Path) -> AlarmCatalog:
    defs: list[AlarmDefinition] = []
    for p in sorted(dir_.glob("*.yaml")) if dir_.is_dir() else []:
        data = load_yaml_file(p) or {}
        for raw in data.get("alarms", []):
            try:
                defs.append(AlarmDefinition.model_validate(raw))
            except ValidationError as exc:
                raise ConfigError(f"{p.name}: {_fmt(exc)}") from exc
    return AlarmCatalog(definitions=defs)


def load_stop_by_catalog(dir_: Path) -> StopByCatalog:
    entries: list[StopByEntry] = []
    for p in sorted(dir_.glob("*.yaml")) if dir_.is_dir() else []:
        data = load_yaml_file(p) or {}
        for raw in data.get("entries", []):
            try:
                entries.append(StopByEntry.model_validate(raw))
            except ValidationError as exc:
                raise ConfigError(f"{p.name}: {_fmt(exc)}") from exc
    return StopByCatalog(entries=entries)


class ConfigStore:
    """Le a semente em config/. Em runtime, a fonte da verdade da configuracao editavel
    e o banco core (fase G); ate la, esta classe e a fonte."""

    def __init__(self, paths: ForjaPaths | None = None) -> None:
        self.paths = paths or resolve_paths()
        self.config: ForjaConfig = ForjaConfig()
        self.profiles: dict[str, EquipmentProfile] = {}
        self.mappings: dict[str, Mapping] = {}
        self.alarms: AlarmCatalog = AlarmCatalog()
        self.stop_by: StopByCatalog = StopByCatalog()

    def load_all(self) -> ConfigStore:
        if self.paths.forja_yaml.exists():
            self.config = load_forja_config(self.paths.forja_yaml)
        self.profiles = {}
        for p in sorted(self.paths.equipment_dir.glob("*.yaml")):
            if p.name.startswith("_"):
                continue
            prof = load_profile(p)
            if prof.id in self.profiles:
                raise ConfigError(f"equipment id duplicado: {prof.id} ({p.name})")
            self.profiles[prof.id] = prof
        self.mappings = {}
        for p in sorted(self.paths.mappings_dir.glob("*.yaml")):
            if p.name.startswith("_"):
                continue
            m = load_mapping(p)
            self.mappings[m.mapping_id] = m
        for prof in self.profiles.values():
            if prof.mapping_profile not in self.mappings:
                raise ConfigError(
                    f"{prof.id}: mapping_profile {prof.mapping_profile!r} "
                    "não encontrado em config/mappings"
                )
        self.alarms = load_alarm_catalog(self.paths.alarms_dir)
        self.stop_by = load_stop_by_catalog(self.paths.stop_by_dir)
        return self

    def mapping_for(self, equipment_id: str) -> Mapping:
        prof = self.profiles[equipment_id]
        return self.mappings[prof.mapping_profile]
