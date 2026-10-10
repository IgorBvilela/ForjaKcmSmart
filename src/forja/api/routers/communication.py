"""Central de Comunicação KCM: suporte por driver, configuração, mapping, teste somente leitura
e ativação da coleta local.

Nenhuma rota fala com o KCM para mudar nada. O teste só lê, com driver descartável. "Ativar
coleta" liga a LEITURA periódica da Forja; não manda comando ao equipamento. Toda gravação de
configuração é validada, versionada (histórico em config/_history) e auditada.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi import Path as PathParam
from pydantic import BaseModel, ConfigDict, Field

from forja.api.deps import ContainerDep, jsonable, require_profile
from forja.api.errors import ApiError
from forja.api.routers.equipments import status_view
from forja.config.writer import ConfigConflict, ConfigWriter, config_hash
from forja.domain import (
    REAL_DRIVERS,
    UNKNOWN,
    CommunicationConfig,
    ConfigError,
    ControllerInfo,
    DriverSupportState,
    EquipmentProfile,
    HostInterface,
    Mapping,
    NotConfigured,
    UnsupportedDriver,
)
from forja.service.commcenter import (
    COLLECTION_BLOCKED_PREFIX_PT,
    comm_state,
    has_successful_test,
    read_test_view,
    reading_fingerprint,
    template_mapping,
    validate_candidate,
)

logger = logging.getLogger("forja.api.communication")

router = APIRouter(prefix="/api/v1/communication", tags=["comunicacao"])

FIELD_CONFIG_PT = "Disponível após configuração de campo"
USER_PATTERN = r"^[\w .@\-]+$"

EquipmentId = Annotated[str, PathParam(max_length=64, description="Id do equipamento")]


class TestReadBody(BaseModel):
    """Perfil e mapping candidatos. Validados pelo domínio antes de qualquer tentativa."""

    model_config = ConfigDict(extra="forbid")

    profile: EquipmentProfile
    mapping: Mapping
    user: str = Field(default="", max_length=64, pattern=r"^[\w .@\-]*$")


class ValidateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    communication: CommunicationConfig
    mapping: Mapping


class CommConfigBody(BaseModel):
    """Nova configuração de comunicação. `base_hash` = hash do perfil que a tela leu."""

    model_config = ConfigDict(extra="forbid")

    communication: CommunicationConfig
    host_interface: HostInterface | None = None
    controller: ControllerInfo | None = None
    mapping_profile: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9_\-]{1,63}$")
    base_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    user: str = Field(min_length=1, max_length=64, pattern=USER_PATTERN)
    reason_pt: str = Field(default="", max_length=2000)


class MappingBody(BaseModel):
    """Mapping editado. `base_version` = versão que a tela leu (null = mapping novo)."""

    model_config = ConfigDict(extra="forbid")

    mapping: Mapping
    base_version: int | None = Field(default=None, ge=1)
    user: str = Field(min_length=1, max_length=64, pattern=USER_PATTERN)
    reason_pt: str = Field(default="", max_length=2000)


class CollectionBody(BaseModel):
    """Liga ou desliga a LEITURA periódica da Forja. Não comanda o KCM."""

    model_config = ConfigDict(extra="forbid")

    active: bool
    user: str = Field(min_length=1, max_length=64, pattern=USER_PATTERN)
    reason_pt: str = Field(default="", max_length=2000)


# ----------------------------------------------------------------------------- apoio


def _support_state(info: Any) -> DriverSupportState:
    """Estado a partir do DriverSupportInfo (aceita enum ou string)."""
    state = getattr(info, "state", None)
    if isinstance(state, DriverSupportState):
        return state
    try:
        return DriverSupportState(str(state))
    except ValueError:
        return DriverSupportState.UNSUPPORTED


def driver_support(container: Any) -> dict[str, Any]:
    """{nome: info} do registry, com rótulo em português."""
    support = container.registry.support()
    out: dict[str, Any] = {}
    for name, info in sorted(support.items()):
        state = _support_state(info)
        view = jsonable(info)
        if not isinstance(view, dict):
            view = {"name": name}
        view["state"] = state.value
        view["state_pt"] = state.label_pt
        out[name] = view
    return out


def equipment_comm_state(profile: EquipmentProfile, support: dict[str, Any]) -> dict[str, Any]:
    """Estado de comunicação por equipamento. IP/protocolo UNKNOWN => NEEDS_CONFIGURATION."""
    driver = profile.communication.driver
    info = support.get(driver)
    registry_state = DriverSupportState(info["state"]) if info else DriverSupportState.UNSUPPORTED
    state = (
        DriverSupportState.NEEDS_CONFIGURATION
        if profile.communication.needs_configuration
        else registry_state
    )
    return {
        "equipment_id": profile.id,
        "driver": driver,
        "protocol": profile.communication.protocol,
        "ip_known": profile.communication.ip != UNKNOWN,
        "needs_configuration": profile.communication.needs_configuration,
        "collection_enabled": profile.communication.collection_enabled,
        "support_state": state.value,
        "support_state_pt": state.label_pt,
        "driver_state": registry_state.value,
        "message_pt": FIELD_CONFIG_PT if state != DriverSupportState.AVAILABLE else "",
    }


def _writer(container: Any) -> ConfigWriter:
    return ConfigWriter(container.paths)


async def _audit(container: Any, **kwargs: Any) -> None:
    audit = getattr(container.core, "audit", None) or getattr(container.events_repo, "audit", None)
    if not callable(audit):
        raise ApiError(
            501, "AUDIT_UNAVAILABLE", "Gravação indisponível: trilha de auditoria não configurada."
        )
    await audit(**kwargs)


async def _latest_test(container: Any, equipment_id: str) -> dict[str, Any] | None:
    latest = getattr(container.core, "latest_read_test", None)
    if not callable(latest):
        return None
    result: dict[str, Any] | None = await latest(equipment_id)
    return result


async def _successful_test_for(container: Any, equipment_id: str, fingerprint: str) -> bool:
    return await has_successful_test(container.core, equipment_id, fingerprint)


def _mapping_of(container: Any, profile: EquipmentProfile) -> Mapping:
    mapping: Mapping = container.store.mappings[profile.mapping_profile]
    return mapping


def _mapping_shared(container: Any, mapping: Mapping) -> bool:
    users = [
        p.id for p in container.store.profiles.values() if p.mapping_profile == mapping.mapping_id
    ]
    return mapping.equipment_id == "*" or mapping.driver == "simulator" or len(users) > 1


def editable_mapping(container: Any, profile: EquipmentProfile) -> tuple[Mapping, bool]:
    """Mapping que a tela pode editar para este equipamento e se ele já existe no disco.

    Mapping em uso e próprio: ele mesmo. Compartilhado (simulador): o mapping próprio do
    equipamento, se existir; senão um modelo novo com as variáveis principais em UNKNOWN.
    """
    current = _mapping_of(container, profile)
    if not _mapping_shared(container, current):
        return current, True
    for candidate in container.store.mappings.values():
        if candidate.equipment_id == profile.id and not _mapping_shared(container, candidate):
            return candidate, True
    return template_mapping(profile.id), False


async def build_comm_view(container: Any, profile: EquipmentProfile) -> dict[str, Any]:
    """Tudo que a tela de Comunicação precisa de um equipamento."""
    support = driver_support(container)
    mapping = _mapping_of(container, profile)
    fingerprint = reading_fingerprint(profile, mapping)
    status = container.manager.status(profile.id)
    last_test = await _latest_test(container, profile.id)
    info = support.get(profile.communication.driver)
    state = comm_state(profile, info["state"] if info else None, status, last_test, fingerprint)
    editable, editable_exists = editable_mapping(container, profile)
    return {
        "equipment_id": profile.id,
        "name": profile.name,
        "is_example": profile.is_example,
        "profile": jsonable(profile),
        "config_hash": config_hash(profile),
        "mapping": jsonable(mapping),
        "mapping_shared": _mapping_shared(container, mapping),
        "editable_mapping": jsonable(editable),
        "editable_mapping_exists": editable_exists,
        "fingerprint": fingerprint,
        "drivers": support,
        "state": state,
        "collection": _collection_view(profile, status),
        "runtime": status_view(status),
        "last_test": jsonable(last_test),
        "last_test_matches": bool(last_test and last_test.get("fingerprint") == fingerprint),
        "read_only": True,
    }


async def _apply(container: Any, profile: EquipmentProfile, mapping: Mapping) -> None:
    """Atualiza a configuração em memória e recarrega SÓ este equipamento."""
    container.store.mappings[mapping.mapping_id] = mapping
    container.store.profiles[profile.id] = profile
    try:
        await container.manager.reload(profile.id, profile=profile, mapping=mapping)
    except Exception:
        logger.exception("comunicação %s: recarga após gravar falhou", profile.id)


def _blocked_reason(profile: EquipmentProfile, status: Any) -> str | None:
    """Coleta ligada no arquivo, mas a porteira não deixou começar (falta teste desta config)."""
    detail = str(getattr(status, "detail_pt", "") or "")
    if profile.communication.collection_enabled and detail.startswith(COLLECTION_BLOCKED_PREFIX_PT):
        return detail
    return None


def _collection_view(profile: EquipmentProfile, status: Any) -> dict[str, Any]:
    enabled = profile.communication.collection_enabled
    blocked = _blocked_reason(profile, status)
    return {
        "enabled": enabled,
        "blocked": blocked is not None,
        "label_pt": blocked or ("Coleta ativa (somente leitura)" if enabled else "Coleta pausada"),
    }


def _check_mapping_compiles(profile: EquipmentProfile, mapping: Mapping) -> None:
    """Mapping de driver real precisa virar plano de leitura válido (endereços coerentes)."""
    if mapping.driver not in REAL_DRIVERS:
        return
    from forja.normalization.plan import ReadPlanCompiler

    probe = profile.model_copy(
        update={
            "communication": profile.communication.model_copy(update={"driver": mapping.driver}),
            "mapping_profile": mapping.mapping_id,
        }
    )
    try:
        ReadPlanCompiler().compile(probe, mapping)
    except (ConfigError, UnsupportedDriver) as exc:
        raise ApiError(
            422, "MAPPING_INVALID", "Endereços do mapping incoerentes.", {"detail": str(exc)}
        ) from exc


def _conflict(exc: ConfigConflict) -> ApiError:
    return ApiError(409, "CONFIG_CONFLICT", str(exc))


# ----------------------------------------------------------------------------- rotas


@router.get("/drivers")
async def get_drivers(container: ContainerDep) -> dict[str, Any]:
    """Suporte por driver e estado por equipamento."""
    support = driver_support(container)
    statuses = container.manager.statuses()
    equipments = []
    for profile in container.store.profiles.values():
        view = equipment_comm_state(profile, support)
        status = statuses.get(profile.id)
        view["connection"] = status.connection.value if status else None
        view["connection_pt"] = status.connection.label_pt if status else None
        equipments.append(view)
    return {"drivers": support, "equipments": equipments, "read_only": True}


@router.post("/test-read", status_code=200)
async def test_read(body: TestReadBody, container: ContainerDep) -> dict[str, Any]:
    """Teste de leitura com driver descartável. Só lê; nunca escreve."""
    driver = body.profile.communication.driver
    support = driver_support(container)
    info = support.get(driver)
    if info is None or info["state"] == DriverSupportState.UNSUPPORTED.value:
        raise ApiError(
            409,
            "DRIVER_UNSUPPORTED",
            FIELD_CONFIG_PT,
            {"driver": driver, "reason_pt": (info or {}).get("reason_pt", "driver desconhecido")},
        )
    if body.profile.communication.needs_configuration:
        raise ApiError(
            409,
            "NEEDS_CONFIGURATION",
            "Não configurado: informe protocolo e endereço IP antes do teste de leitura.",
            {"driver": driver},
        )
    if body.mapping.equipment_id not in ("*", body.profile.id):
        raise ApiError(
            422,
            "MAPPING_MISMATCH",
            "O mapping informado pertence a outro equipamento.",
            {"mapping_equipment_id": body.mapping.equipment_id, "profile_id": body.profile.id},
        )
    report = validate_candidate(body.profile, body.mapping, container.registry.support())
    if not report.ok:
        raise ApiError(
            422,
            "CONFIG_INVALID",
            "Perfil ou mapping inválidos para o teste de leitura.",
            {"driver": driver, "errors": report.errors},
        )
    try:
        result = await container.manager.test_read(body.profile, body.mapping)
    except UnsupportedDriver as exc:
        raise ApiError(
            409, "DRIVER_UNSUPPORTED", FIELD_CONFIG_PT, {"driver": driver, "reason_pt": str(exc)}
        ) from exc
    except NotConfigured as exc:
        raise ApiError(
            409,
            "NEEDS_CONFIGURATION",
            "Não configurado: informe protocolo e endereço IP antes do teste de leitura.",
            {"driver": driver, "reason_pt": str(exc)},
        ) from exc
    except ConfigError as exc:
        raise ApiError(
            422,
            "CONFIG_INVALID",
            "Perfil ou mapping inválidos para o teste de leitura.",
            {"driver": driver, "detail": str(exc)[:500]},
        ) from exc
    view = jsonable(result)
    if not isinstance(view, dict):
        view = {"result": view}
    final = getattr(result, "final", None)
    success = bool(getattr(final, "is_success", False))
    view["final_pt"] = getattr(final, "label_pt", None)
    view["success"] = success
    view["read_only"] = True
    view["detail"] = read_test_view(result, body.profile, body.mapping, report.blocks)
    view["warnings"] = list(report.warnings)
    fingerprint = reading_fingerprint(body.profile, body.mapping)
    view["fingerprint"] = fingerprint
    saved = container.store.profiles.get(body.profile.id)
    if (
        saved is not None
        and saved.communication.collection_enabled
        and saved.communication.driver in REAL_DRIVERS
    ):
        view["warnings"].append(
            "A coleta deste equipamento está ativa: o teste abriu uma conexão adicional."
        )
    saver = getattr(container.core, "save_read_test", None)
    if saved is not None and callable(saver):
        view["test_id"] = await saver(
            equipment_id=body.profile.id,
            driver=driver,
            final_stage=str(getattr(final, "value", final)),
            success=success,
            latency_ms=getattr(result, "latency_ms", None),
            fingerprint=fingerprint,
            user=body.user,
            result={k: v for k, v in view.items() if k != "values"},
        )
    return view


@router.get("/{equipment_id}")
async def get_comm(equipment_id: EquipmentId, container: ContainerDep) -> dict[str, Any]:
    """Configuração de comunicação, mapping, estado, coleta e último teste de um equipamento."""
    profile = require_profile(container, equipment_id)
    return await build_comm_view(container, profile)


@router.post("/{equipment_id}/validate", status_code=200)
async def validate(
    equipment_id: EquipmentId, body: ValidateBody, container: ContainerDep
) -> dict[str, Any]:
    """Confere a configuração candidata sem abrir conexão (nada é gravado)."""
    profile = require_profile(container, equipment_id)
    candidate = profile.model_copy(
        update={
            "communication": body.communication,
            "mapping_profile": body.mapping.mapping_id,
        }
    )
    report = validate_candidate(candidate, body.mapping, container.registry.support())
    out = report.as_dict()
    out["fingerprint"] = reading_fingerprint(candidate, body.mapping)
    return out


@router.post("/{equipment_id}/config", status_code=200)
async def save_config(
    equipment_id: EquipmentId, body: CommConfigBody, container: ContainerDep
) -> dict[str, Any]:
    """Grava a configuração de comunicação. Se o que muda a leitura mudou, a coleta de um driver
    real fica pausada até um novo teste somente leitura e a ativação."""
    profile = require_profile(container, equipment_id)
    mapping_id = body.mapping_profile or profile.mapping_profile
    if mapping_id not in container.store.mappings:
        raise ApiError(
            422, "MAPPING_NOT_FOUND", "Mapping não encontrado.", {"mapping_profile": mapping_id}
        )
    mapping: Mapping = container.store.mappings[mapping_id]
    comm = body.communication
    updated = profile.model_copy(
        update={
            "communication": comm,
            "host_interface": body.host_interface or profile.host_interface,
            "controller": body.controller or profile.controller,
            "mapping_profile": mapping_id,
        }
    )
    old_fp = reading_fingerprint(profile, _mapping_of(container, profile))
    new_fp = reading_fingerprint(updated, mapping)
    # Esta rota nunca LIGA a coleta (isso é /collection, com o teste exigido). Ela só mantém o
    # estado atual ou pausa, quando o que muda a leitura mudou num driver real.
    keep = profile.communication.collection_enabled
    paused = False
    if comm.driver in REAL_DRIVERS and new_fp != old_fp and keep:
        keep = False
        paused = True
    comm = comm.model_copy(update={"collection_enabled": keep})
    updated = updated.model_copy(update={"communication": comm})
    try:
        saved = _writer(container).save_profile(
            updated, expected_hash=body.base_hash, now=container.clock.now_utc()
        )
    except ConfigConflict as exc:
        raise _conflict(exc) from exc
    except ConfigError as exc:
        raise ApiError(
            422, "CONFIG_INVALID", "Configuração inválida.", {"detail": str(exc)}
        ) from exc
    await _audit(
        container,
        user=body.user,
        action="COMM_CONFIG_SAVE",
        entity_type="equipment",
        entity_id=profile.id,
        before={
            "communication": jsonable(profile.communication),
            "mapping": profile.mapping_profile,
        },
        after={"communication": jsonable(saved.profile.communication), "mapping": mapping_id},
        reason_pt=body.reason_pt,
    )
    await _apply(container, saved.profile, mapping)
    view = await build_comm_view(container, saved.profile)
    view["collection_paused_by_change"] = paused
    view["report"] = validate_candidate(
        saved.profile, mapping, container.registry.support()
    ).as_dict()
    return view


@router.post("/{equipment_id}/mapping", status_code=200)
async def save_mapping(
    equipment_id: EquipmentId, body: MappingBody, container: ContainerDep
) -> dict[str, Any]:
    """Grava o mapping do equipamento com versão nova. Mapping compartilhado (simulador) não é
    editável aqui: crie um mapping próprio do equipamento."""
    profile = require_profile(container, equipment_id)
    mapping = body.mapping
    if mapping.equipment_id != profile.id:
        raise ApiError(
            422,
            "MAPPING_MISMATCH",
            "O mapping precisa ser deste equipamento (equipment_id).",
            {"mapping_equipment_id": mapping.equipment_id},
        )
    _check_mapping_compiles(profile, mapping)
    existing = container.store.mappings.get(mapping.mapping_id)
    if existing is not None and _mapping_shared(container, existing):
        raise ApiError(
            409,
            "MAPPING_SHARED",
            "Este mapping é compartilhado (simulador ou outros equipamentos). Crie um mapping "
            "próprio deste equipamento.",
            {"mapping_id": mapping.mapping_id},
        )
    if existing is None and body.base_version is not None:
        raise ApiError(409, "CONFIG_CONFLICT", "O mapping informado não existe mais.")
    try:
        saved = _writer(container).save_mapping(
            mapping, expected_version=body.base_version, now=container.clock.now_utc()
        )
    except ConfigConflict as exc:
        raise _conflict(exc) from exc
    except ConfigError as exc:
        raise ApiError(422, "CONFIG_INVALID", "Mapping inválido.", {"detail": str(exc)}) from exc
    await _audit(
        container,
        user=body.user,
        action="MAPPING_SAVE",
        entity_type="mapping",
        entity_id=saved.mapping.mapping_id,
        before=None if existing is None else {"version": existing.version},
        after={"version": saved.mapping.version, "entries": len(saved.mapping.entries)},
        reason_pt=body.reason_pt,
    )
    container.store.mappings[saved.mapping.mapping_id] = saved.mapping
    current = container.store.profiles[profile.id]
    if current.mapping_profile == saved.mapping.mapping_id:
        old_fp = reading_fingerprint(current, existing) if existing else ""
        new_fp = reading_fingerprint(current, saved.mapping)
        comm = current.communication
        if comm.driver in REAL_DRIVERS and comm.collection_enabled and new_fp != old_fp:
            paused_profile = current.model_copy(
                update={"communication": comm.model_copy(update={"collection_enabled": False})}
            )
            try:
                result = _writer(container).save_profile(
                    paused_profile,
                    expected_hash=config_hash(current),
                    now=container.clock.now_utc(),
                )
            except ConfigConflict as exc:
                raise _conflict(exc) from exc
            current = result.profile
        await _apply(container, current, saved.mapping)
    return await build_comm_view(container, container.store.profiles[profile.id])


@router.post("/{equipment_id}/collection", status_code=200)
async def set_collection(
    equipment_id: EquipmentId, body: CollectionBody, container: ContainerDep
) -> dict[str, Any]:
    """Ativa ou pausa a coleta LOCAL (leitura periódica). Nunca comanda o KCM.

    Driver real: ativar exige teste somente leitura bem-sucedido da configuração salva.
    """
    profile = require_profile(container, equipment_id)
    comm = profile.communication
    mapping = _mapping_of(container, profile)
    if body.active and comm.driver in REAL_DRIVERS:
        if comm.needs_configuration:
            raise ApiError(
                409,
                "NEEDS_CONFIGURATION",
                "Configure protocolo e endereço antes de ativar a coleta.",
            )
        fingerprint = reading_fingerprint(profile, mapping)
        if not await _successful_test_for(container, profile.id, fingerprint):
            raise ApiError(
                409,
                "READ_TEST_REQUIRED",
                "Antes de ativar a coleta, faça o teste somente leitura com a configuração salva "
                "e obtenha leitura.",
                {"fingerprint": fingerprint},
            )
    if body.active and comm.driver == UNKNOWN:
        raise ApiError(409, "NEEDS_CONFIGURATION", "Protocolo ainda não identificado.")
    if comm.collection_enabled == body.active:
        blocked = _blocked_reason(profile, container.manager.status(profile.id))
        if body.active and blocked is not None:
            # A configuração já pede coleta, mas a porteira bloqueou na partida: com o teste
            # conferido acima, a recarga reavalia e a coleta começa.
            await _audit(
                container,
                user=body.user,
                action="COLLECTION_ON",
                entity_type="equipment",
                entity_id=profile.id,
                before={"collection_enabled": True, "blocked": True},
                after={"collection_enabled": True, "blocked": False},
                reason_pt=body.reason_pt,
            )
            await _apply(container, profile, mapping)
        return await build_comm_view(container, profile)
    updated = profile.model_copy(
        update={"communication": comm.model_copy(update={"collection_enabled": body.active})}
    )
    try:
        saved = _writer(container).save_profile(
            updated, expected_hash=config_hash(profile), now=container.clock.now_utc()
        )
    except ConfigConflict as exc:
        raise _conflict(exc) from exc
    await _audit(
        container,
        user=body.user,
        action="COLLECTION_ON" if body.active else "COLLECTION_OFF",
        entity_type="equipment",
        entity_id=profile.id,
        before={"collection_enabled": comm.collection_enabled},
        after={"collection_enabled": body.active},
        reason_pt=body.reason_pt,
    )
    await _apply(container, saved.profile, mapping)
    return await build_comm_view(container, saved.profile)


@router.get("/{equipment_id}/read-tests")
async def list_read_tests(
    equipment_id: EquipmentId,
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
) -> dict[str, Any]:
    """Histórico dos testes somente leitura (evidência para o comissionamento)."""
    profile = require_profile(container, equipment_id)
    lister = getattr(container.core, "list_read_tests", None)
    tests = await lister(profile.id, limit) if callable(lister) else []
    return {"equipment_id": profile.id, "tests": jsonable(tests)}


@router.get("/{equipment_id}/log")
async def comm_log(
    equipment_id: EquipmentId,
    container: ContainerDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> dict[str, Any]:
    """Log técnico de conexão do equipamento (mais recente primeiro)."""
    profile = require_profile(container, equipment_id)
    entries = await container.historian.comm_log(profile.id, None, limit)
    return {"equipment_id": profile.id, "entries": jsonable(entries)}
