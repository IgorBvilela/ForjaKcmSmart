"""Cadastro de equipamentos: criar, editar a ficha técnica, arquivar e restaurar.

Tudo grava a configuração da Forja (YAML em config/equipment, com histórico e auditoria) e nunca
fala com o KCM. Equipamento novo nasce com o protocolo não identificado: a comunicação é
configurada depois, na tela Comunicação, com teste somente leitura antes da coleta (ADR 0026).
Arquivar não apaga nada: o perfil vai para config/_archive e o histórico continua no banco.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter
from fastapi import Path as PathParam
from pydantic import BaseModel, ConfigDict, Field

from forja.api.deps import ContainerDep, jsonable, require_profile
from forja.api.errors import ApiError
from forja.config.writer import ORIGIN_EQUIPMENT_PT, ConfigConflict, ConfigWriter, config_hash
from forja.domain import (
    UNKNOWN,
    AlarmDefinition,
    Component,
    ConfigError,
    ControllerInfo,
    EquipmentProfile,
    HostInterface,
    KnowledgeState,
    MappingValidationError,
)
from forja.domain.assets import CommunicationConfig
from forja.service.commcenter import template_mapping

logger = logging.getLogger("forja.api")

router = APIRouter(prefix="/api/v1", tags=["equipamentos"])

USER_PATTERN = r"^[\w .@\-]+$"
EQUIPMENT_ID_PATTERN = r"^[A-Z0-9][A-Z0-9_]{1,63}$"
EquipmentId = Annotated[str, PathParam(min_length=1, max_length=64, pattern=EQUIPMENT_ID_PATTERN)]
TEXT_FIELD = Field(default=UNKNOWN, min_length=1, max_length=80)

ALARM_NOTE_PT = (
    "O significado de um código de alarme vale para a combinação exata de fabricante, "
    "controlador, aplicação e versão de software. Fora dela, o mesmo número pode significar outra "
    "coisa."
)


class IdentityFields(BaseModel):
    """O que identifica o equipamento na planta. Desconhecido fica UNKNOWN."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=80)
    plant: str = TEXT_FIELD
    area: str = TEXT_FIELD
    line: str = TEXT_FIELD
    application: str = Field(default=UNKNOWN, pattern=r"^(WBF|LWF|UNKNOWN)$")
    application_evidence: KnowledgeState = KnowledgeState.UNKNOWN
    notes_pt: str = Field(default="", max_length=4000)


class CreateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=EQUIPMENT_ID_PATTERN)
    identity: IdentityFields
    user: str = Field(min_length=1, max_length=64, pattern=USER_PATTERN)
    reason_pt: str = Field(default="", max_length=2000)


class DatasheetBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    identity: IdentityFields
    controller: ControllerInfo
    host_interface: HostInterface
    components: list[Component] = Field(default_factory=list, max_length=50)
    base_hash: str = Field(min_length=64, max_length=64)
    user: str = Field(min_length=1, max_length=64, pattern=USER_PATTERN)
    reason_pt: str = Field(default="", max_length=2000)


class ArchiveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm_id: str = Field(min_length=1, max_length=64)
    """O id digitado de novo: arquivar é deliberado."""
    user: str = Field(min_length=1, max_length=64, pattern=USER_PATTERN)
    reason_pt: str = Field(min_length=3, max_length=2000)


class RestoreBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: str = Field(min_length=1, max_length=64, pattern=USER_PATTERN)
    reason_pt: str = Field(default="", max_length=2000)


def _writer(container: Any) -> ConfigWriter:
    return ConfigWriter(container.paths)


async def _audit(container: Any, **kwargs: Any) -> None:
    audit = getattr(container.core, "audit", None) or getattr(container.events_repo, "audit", None)
    if not callable(audit):
        raise ApiError(
            501, "AUDIT_UNAVAILABLE", "Gravação indisponível: trilha de auditoria não configurada."
        )
    await audit(**kwargs)


def _datasheet(profile: EquipmentProfile) -> dict[str, Any]:
    return {
        "identity": {
            "name": profile.name,
            "plant": profile.plant,
            "area": profile.area,
            "line": profile.line,
            "application": profile.application,
            "application_evidence": profile.application_evidence.value,
            "notes_pt": profile.notes_pt,
        },
        "controller": jsonable(profile.controller),
        "host_interface": jsonable(profile.host_interface),
        "components": jsonable(profile.components),
    }


def unknown_fields(profile: EquipmentProfile) -> list[str]:
    """Campos da ficha ainda UNKNOWN: o que a visita de campo precisa levantar."""
    out = [
        f"identity.{k}"
        for k in ("plant", "area", "line", "application")
        if getattr(profile, k) == UNKNOWN
    ]
    out += [f"controller.{k}" for k, v in profile.controller.model_dump().items() if v == UNKNOWN]
    out += [
        f"host_interface.{k}"
        for k, v in profile.host_interface.model_dump().items()
        if v == UNKNOWN and k != "evidence"
    ]
    return out


def equipment_admin_view(container: Any, profile: EquipmentProfile) -> dict[str, Any]:
    mapping = container.store.mappings.get(profile.mapping_profile)
    return {
        "equipment_id": profile.id,
        "profile": jsonable(profile),
        "config_hash": config_hash(profile),
        "datasheet": _datasheet(profile),
        "unknown_fields": unknown_fields(profile),
        "mapping": {
            "mapping_id": profile.mapping_profile,
            "driver": mapping.driver if mapping is not None else UNKNOWN,
            "entries": len(mapping.entries) if mapping is not None else 0,
            "readable": len(mapping.readable_entries) if mapping is not None else 0,
        },
        "is_simulated": profile.is_simulated,
        "is_example": profile.is_example,
    }


@router.post("/equipments", status_code=201)
async def create_equipment(body: CreateBody, container: ContainerDep) -> dict[str, Any]:
    """Cadastra um equipamento com protocolo não identificado e mapping modelo todo UNKNOWN."""
    writer = _writer(container)
    if body.id in container.store.profiles:
        raise ApiError(409, "EQUIPMENT_EXISTS", "Já existe um equipamento com este id.")
    if any(p.id == body.id for _, p in writer.archived_profiles()):
        raise ApiError(
            409,
            "EQUIPMENT_ARCHIVED",
            "Este id pertence a um equipamento arquivado. Restaure-o em vez de criar outro.",
        )
    mapping = template_mapping(body.id)
    existing = container.store.mappings.get(mapping.mapping_id)
    if existing is not None and existing.equipment_id != body.id:
        raise ApiError(
            409,
            "MAPPING_EXISTS",
            f"Já existe um mapping {mapping.mapping_id} de outro equipamento.",
        )
    profile = EquipmentProfile(
        id=body.id,
        name=body.identity.name,
        plant=body.identity.plant,
        area=body.identity.area,
        line=body.identity.line,
        application=body.identity.application,
        application_evidence=body.identity.application_evidence,
        notes_pt=body.identity.notes_pt,
        communication=CommunicationConfig(driver="UNKNOWN", collection_enabled=False),
        mapping_profile=mapping.mapping_id,
    )
    now = container.clock.now_utc()
    try:
        if existing is None:
            saved_mapping = writer.save_mapping(
                mapping, expected_version=None, now=now, origin_pt=ORIGIN_EQUIPMENT_PT
            ).mapping
        else:
            saved_mapping = existing
        saved = writer.save_profile(
            profile, expected_hash=None, now=now, origin_pt=ORIGIN_EQUIPMENT_PT
        )
    except ConfigConflict as exc:
        raise ApiError(409, "CONFIG_CONFLICT", str(exc)) from exc
    except (ConfigError, MappingValidationError) as exc:
        raise ApiError(422, "CONFIG_INVALID", str(exc)) from exc
    await _audit(
        container,
        user=body.user,
        action="EQUIPMENT_CREATE",
        entity_type="equipment",
        entity_id=profile.id,
        before=None,
        after=_datasheet(saved.profile)["identity"],
        reason_pt=body.reason_pt,
    )
    container.store.mappings[saved_mapping.mapping_id] = saved_mapping
    await container.manager.add(saved.profile, saved_mapping)
    logger.info("equipamento %s cadastrado por %s", profile.id, body.user)
    return equipment_admin_view(container, saved.profile)


@router.get("/equipments/{equipment_id}/datasheet")
async def get_datasheet(equipment_id: EquipmentId, container: ContainerDep) -> dict[str, Any]:
    """Ficha técnica com a evidência de cada informação e o que ainda é desconhecido."""
    profile = require_profile(container, equipment_id)
    return equipment_admin_view(container, profile)


@router.post("/equipments/{equipment_id}/datasheet")
async def save_datasheet(
    equipment_id: EquipmentId, body: DatasheetBody, container: ContainerDep
) -> dict[str, Any]:
    """Grava identidade, controlador, interface Host e componentes. A comunicação não muda."""
    profile = require_profile(container, equipment_id)
    identity = body.identity
    updated = profile.model_copy(
        update={
            "name": identity.name,
            "plant": identity.plant,
            "area": identity.area,
            "line": identity.line,
            "application": identity.application,
            "application_evidence": identity.application_evidence,
            "notes_pt": identity.notes_pt,
            "controller": body.controller,
            "host_interface": body.host_interface,
            "components": body.components,
        }
    )
    try:
        saved = _writer(container).save_profile(
            updated,
            expected_hash=body.base_hash,
            now=container.clock.now_utc(),
            origin_pt=ORIGIN_EQUIPMENT_PT,
        )
    except ConfigConflict as exc:
        raise ApiError(409, "CONFIG_CONFLICT", str(exc)) from exc
    except ConfigError as exc:
        raise ApiError(422, "CONFIG_INVALID", str(exc)) from exc
    await _audit(
        container,
        user=body.user,
        action="EQUIPMENT_DATASHEET_SAVE",
        entity_type="equipment",
        entity_id=profile.id,
        before=_datasheet(profile),
        after=_datasheet(saved.profile),
        reason_pt=body.reason_pt,
    )
    container.store.profiles[profile.id] = saved.profile
    return equipment_admin_view(container, saved.profile)


@router.post("/equipments/{equipment_id}/archive")
async def archive_equipment(
    equipment_id: EquipmentId, body: ArchiveBody, container: ContainerDep
) -> dict[str, Any]:
    """Para a coleta e tira o equipamento da configuração ativa. O histórico fica no banco."""
    profile = require_profile(container, equipment_id)
    if body.confirm_id != profile.id:
        raise ApiError(422, "CONFIRMATION_MISMATCH", "Digite o id do equipamento para confirmar.")
    try:
        archived = _writer(container).archive_profile(profile.id, container.clock.now_utc())
    except ConfigError as exc:
        raise ApiError(409, "ARCHIVE_FAILED", str(exc)) from exc
    await container.manager.remove(profile.id)
    await _audit(
        container,
        user=body.user,
        action="EQUIPMENT_ARCHIVE",
        entity_type="equipment",
        entity_id=profile.id,
        before={"active": True},
        after={"active": False, "archive_file": archived.name},
        reason_pt=body.reason_pt,
    )
    logger.info("equipamento %s arquivado por %s", profile.id, body.user)
    return {"equipment_id": profile.id, "archived": True, "archive_file": archived.name}


@router.get("/archived-equipments")
async def archived_equipments(container: ContainerDep) -> dict[str, Any]:
    """Equipamentos arquivados (o mais recente de cada id)."""
    items = [
        {
            "equipment_id": p.id,
            "name": p.name,
            "display_path": p.display_path,
            "archive_file": path.name,
            "is_example": p.is_example,
        }
        for path, p in _writer(container).archived_profiles()
        if p.id not in container.store.profiles
    ]
    return {"count": len(items), "equipments": items}


@router.post("/archived-equipments/{equipment_id}/restore")
async def restore_equipment(
    equipment_id: EquipmentId, body: RestoreBody, container: ContainerDep
) -> dict[str, Any]:
    """Devolve o equipamento à configuração ativa. A coleta segue a porteira do teste."""
    if equipment_id in container.store.profiles:
        raise ApiError(409, "EQUIPMENT_EXISTS", "O equipamento já está ativo.")
    writer = _writer(container)
    match = next((p for _, p in writer.archived_profiles() if p.id == equipment_id), None)
    if match is None:
        raise ApiError(404, "EQUIPMENT_NOT_FOUND", "Nenhum equipamento arquivado com este id.")
    mapping = container.store.mappings.get(match.mapping_profile)
    if mapping is None:
        raise ApiError(
            409,
            "MAPPING_NOT_FOUND",
            f"O mapping {match.mapping_profile} do equipamento não está na configuração.",
        )
    try:
        saved = writer.restore_profile(equipment_id)
    except ConfigConflict as exc:
        raise ApiError(409, "CONFIG_CONFLICT", str(exc)) from exc
    except ConfigError as exc:
        raise ApiError(404, "EQUIPMENT_NOT_FOUND", str(exc)) from exc
    await container.manager.add(saved.profile, mapping)
    await _audit(
        container,
        user=body.user,
        action="EQUIPMENT_RESTORE",
        entity_type="equipment",
        entity_id=equipment_id,
        before={"active": False},
        after={"active": True},
        reason_pt=body.reason_pt,
    )
    return equipment_admin_view(container, saved.profile)


def _alarm_view(definition: AlarmDefinition) -> dict[str, Any]:
    data: dict[str, Any] = jsonable(definition)
    data["evidence_pt"] = definition.evidence.label_pt
    return data


@router.get("/equipments/{equipment_id}/alarm-catalog")
async def alarm_catalog(equipment_id: EquipmentId, container: ContainerDep) -> dict[str, Any]:
    """Alarmes catalogados para a chave deste equipamento e, à parte, os de outras chaves."""
    profile = require_profile(container, equipment_id)
    key = {
        "manufacturer": profile.controller.manufacturer,
        "controller": profile.controller.model,
        "application": profile.application,
        "software_version": profile.controller.software_version,
    }
    exact: list[AlarmDefinition] = []
    other: list[AlarmDefinition] = []
    for definition in container.store.alarms.definitions:
        k = definition.key
        same = (
            k.manufacturer == key["manufacturer"]
            and k.controller == key["controller"]
            and k.application == key["application"]
            and k.software_version == key["software_version"]
        )
        (exact if same else other).append(definition)

    def order(d: AlarmDefinition) -> tuple[int, str]:
        code = d.key.code
        return (int(code), code) if code.isdigit() else (10**9, code)

    return {
        "equipment_id": profile.id,
        "key": key,
        "key_unknown": [k for k, v in key.items() if v == UNKNOWN],
        "alarms": [_alarm_view(d) for d in sorted(exact, key=order)],
        "other_keys": [_alarm_view(d) for d in sorted(other, key=order)],
        "note_pt": ALARM_NOTE_PT,
    }


__all__ = ["equipment_admin_view", "router", "unknown_fields"]
