"""Modo de comissionamento / validação em campo.

Registra a visita: o que foi encontrado no equipamento (protocolo, versão, Host/Anybus, rede,
contadores Host antes e depois) e cada conferência valor Forja x valor na tela do KCM. Nada aqui
fala com o KCM: os valores da Forja vêm do teste somente leitura ou da coleta, pela tela.
Conferência gravada não muda; sessão encerrada é final.
"""

from __future__ import annotations

from collections import Counter
from typing import Annotated, Any

from fastapi import APIRouter
from fastapi import Path as PathParam
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from forja.api.deps import ContainerDep, jsonable, require_profile
from forja.api.errors import ApiError
from forja.domain import (
    UNKNOWN,
    CheckResult,
    CommissioningCheck,
    CommissioningHeader,
    CommissioningSession,
    CommissioningStatus,
    HistorianError,
    Quality,
    get_tag,
    is_known_tag,
)
from forja.reports.commissioning import commissioning_csv

router = APIRouter(prefix="/api/v1", tags=["comissionamento"])

USER_PATTERN = r"^[\w .@\-]+$"
SESSION_ID = Annotated[str, PathParam(pattern=r"^[A-Za-z0-9_-]{8,64}$")]
EquipmentId = Annotated[str, PathParam(max_length=64)]

SUGGESTED_TAGS: tuple[str, ...] = (
    "setpoint",
    "mass_flow",
    "drive_command",
    "rpm",
    "belt_load",
    "alarm_code",
    "alarm_active",
)
"""Roteiro de validação. Não presume que o KCM expõe estas variáveis: "Não exposta pelo KCM"
é resultado válido."""


class SessionCreateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    header: CommissioningHeader


class HeaderBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    header: CommissioningHeader
    user: str = Field(min_length=1, max_length=64, pattern=USER_PATTERN)


class CheckBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tag: str = Field(max_length=40)
    address_text: str = Field(default="", max_length=300)
    forja_value: float | None = None
    forja_raw_hex: str | None = Field(default=None, max_length=512)
    forja_quality: Quality | None = None
    kcm_value: float | None = None
    kcm_text: str = Field(default="", max_length=200)
    result: CheckResult
    note_pt: str = Field(default="", max_length=2000)
    technician: str = Field(min_length=1, max_length=64, pattern=USER_PATTERN)


class CloseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conclusion_pt: str = Field(min_length=1, max_length=4000)
    host_counters_after: str | None = Field(default=None, max_length=500)
    technician: str = Field(min_length=1, max_length=64, pattern=USER_PATTERN)


def _core(container: Any) -> Any:
    core = getattr(container, "core", None)
    if core is None or not callable(getattr(core, "save_commissioning", None)):
        raise ApiError(503, "CORE_UNAVAILABLE", "Registro de comissionamento indisponível.")
    return core


async def _audit(container: Any, **kwargs: Any) -> None:
    audit = getattr(getattr(container, "core", None), "audit", None)
    if callable(audit):
        await audit(**kwargs)


async def _session(container: Any, session_id: str) -> CommissioningSession:
    session: CommissioningSession | None = await _core(container).get_commissioning(session_id)
    if session is None:
        raise ApiError(404, "SESSION_NOT_FOUND", "Sessão de comissionamento não encontrada.")
    return session


def _require_open(session: CommissioningSession) -> None:
    if session.status is not CommissioningStatus.OPEN:
        raise ApiError(
            409, "SESSION_CLOSED", "Sessão encerrada: não aceita mais alterações nem conferências."
        )


def _prefill(container: Any, equipment_id: str) -> dict[str, Any]:
    """Cabeçalho sugerido a partir do perfil. Desconhecido fica UNKNOWN."""
    profile = container.store.profiles[equipment_id]
    comm = profile.communication
    host = profile.host_interface
    parts = [p for p in (host.type, host.model, host.part_number) if p and p != UNKNOWN]
    mapping = container.store.mappings.get(profile.mapping_profile)
    return {
        "protocol_found": comm.protocol,
        "kcm_software_version": profile.controller.software_version,
        "host_interface": " ".join(parts) if parts else UNKNOWN,
        "ip": comm.ip,
        "subnet_mask": comm.subnet,
        "gateway": comm.gateway,
        "mapping_id": profile.mapping_profile,
        "mapping_version": mapping.version if mapping else None,
    }


def _detail(session: CommissioningSession, checks: list[CommissioningCheck]) -> dict[str, Any]:
    counts = Counter(c.result.value for c in checks)
    return {
        "session": jsonable(session),
        "status_pt": session.status.label_pt,
        "checks": [{**jsonable(c), "result_pt": c.result.label_pt} for c in checks],
        "summary": {r.value: counts.get(r.value, 0) for r in CheckResult},
        "covered_tags": sorted({c.tag for c in checks}),
        "suggested_tags": list(SUGGESTED_TAGS),
    }


@router.get("/equipments/{equipment_id}/commissioning")
async def list_sessions(equipment_id: EquipmentId, container: ContainerDep) -> dict[str, Any]:
    """Sessões do equipamento (mais recentes primeiro), roteiro e cabeçalho pré-preenchido."""
    profile = require_profile(container, equipment_id)
    sessions = await _core(container).list_commissioning(profile.id)
    return {
        "equipment_id": profile.id,
        "sessions": [{**jsonable(s), "status_pt": s.status.label_pt} for s in sessions],
        "suggested_tags": list(SUGGESTED_TAGS),
        "prefill": _prefill(container, profile.id),
    }


@router.post("/equipments/{equipment_id}/commissioning", status_code=200)
async def open_session(
    equipment_id: EquipmentId, body: SessionCreateBody, container: ContainerDep
) -> dict[str, Any]:
    """Abre uma sessão de comissionamento (visita de campo)."""
    profile = require_profile(container, equipment_id)
    now = container.clock.now_utc()
    session = CommissioningSession(
        equipment_id=profile.id, created_at_utc=now, updated_at_utc=now, header=body.header
    )
    await _core(container).save_commissioning(session)
    await _audit(
        container,
        user=body.header.technician,
        action="COMMISSIONING_OPEN",
        entity_type="commissioning",
        entity_id=session.id,
        before=None,
        after={"equipment_id": profile.id, "visit_date": body.header.visit_date.isoformat()},
        reason_pt="",
    )
    return _detail(session, [])


@router.get("/commissioning/{session_id}")
async def get_session(session_id: SESSION_ID, container: ContainerDep) -> dict[str, Any]:
    session = await _session(container, session_id)
    checks = await _core(container).list_commissioning_checks(session.id)
    return _detail(session, list(checks))


@router.post("/commissioning/{session_id}/header", status_code=200)
async def update_header(
    session_id: SESSION_ID, body: HeaderBody, container: ContainerDep
) -> dict[str, Any]:
    """Atualiza o cabeçalho enquanto a sessão está aberta."""
    session = await _session(container, session_id)
    _require_open(session)
    updated = session.model_copy(
        update={"header": body.header, "updated_at_utc": container.clock.now_utc()}
    )
    try:
        await _core(container).save_commissioning(updated)
    except HistorianError as exc:
        raise ApiError(409, "SESSION_CLOSED", str(exc)) from exc
    checks = await _core(container).list_commissioning_checks(session.id)
    return _detail(updated, list(checks))


@router.post("/commissioning/{session_id}/checks", status_code=200)
async def add_check(
    session_id: SESSION_ID, body: CheckBody, container: ContainerDep
) -> dict[str, Any]:
    """Registra uma conferência (valor Forja x valor na tela do KCM). Não se altera depois."""
    session = await _session(container, session_id)
    _require_open(session)
    if not is_known_tag(body.tag):
        raise ApiError(422, "UNKNOWN_TAG", "Variável desconhecida.", {"tag": body.tag})
    meta = get_tag(body.tag)
    check = CommissioningCheck(
        session_id=session.id,
        ts_utc=container.clock.now_utc(),
        tag=body.tag,
        label_pt=meta.label_pt,
        unit=meta.unit,
        address_text=body.address_text,
        forja_value=body.forja_value,
        forja_raw_hex=body.forja_raw_hex,
        forja_quality=body.forja_quality,
        kcm_value=body.kcm_value,
        kcm_text=body.kcm_text,
        result=body.result,
        note_pt=body.note_pt,
        technician=body.technician,
    )
    try:
        check_id = await _core(container).add_commissioning_check(check)
    except HistorianError as exc:
        raise ApiError(409, "SESSION_CLOSED", str(exc)) from exc
    saved = check.model_copy(update={"id": check_id})
    return {"check": {**jsonable(saved), "result_pt": saved.result.label_pt}}


@router.post("/commissioning/{session_id}/close", status_code=200)
async def close_session(
    session_id: SESSION_ID, body: CloseBody, container: ContainerDep
) -> dict[str, Any]:
    """Encerra a sessão com a conclusão do técnico. Encerrada é final."""
    session = await _session(container, session_id)
    _require_open(session)
    header = session.header
    if body.host_counters_after is not None:
        header = header.model_copy(update={"host_counters_after": body.host_counters_after})
    closed = session.model_copy(
        update={
            "status": CommissioningStatus.CLOSED,
            "conclusion_pt": body.conclusion_pt,
            "header": header,
            "updated_at_utc": container.clock.now_utc(),
        }
    )
    await _core(container).save_commissioning(closed)
    await _audit(
        container,
        user=body.technician,
        action="COMMISSIONING_CLOSE",
        entity_type="commissioning",
        entity_id=session.id,
        before={"status": session.status.value},
        after={"status": closed.status.value},
        reason_pt=body.conclusion_pt[:500],
    )
    checks = await _core(container).list_commissioning_checks(session.id)
    return _detail(closed, list(checks))


@router.get("/commissioning/{session_id}/report.csv")
async def report_csv(session_id: SESSION_ID, container: ContainerDep) -> Response:
    session = await _session(container, session_id)
    checks = await _core(container).list_commissioning_checks(session.id)
    text = commissioning_csv(session, list(checks), timezone=container.store.config.edge.timezone)
    name = f"comissionamento_{session.equipment_id}_{session.header.visit_date.isoformat()}.csv"
    return Response(
        content=text,
        media_type="text/csv; charset=utf-8",
        headers={
            "content-disposition": f'attachment; filename="{name}"',
            "cache-control": "no-store",
        },
    )


__all__ = ["SUGGESTED_TAGS", "router"]
