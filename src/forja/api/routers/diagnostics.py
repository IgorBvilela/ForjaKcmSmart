"""Diagnóstico (JSON v1.0) por evento e consulta de alarme por chave composta."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from forja.api.deps import ContainerDep, jsonable, require_profile
from forja.api.errors import ApiError
from forja.api.routers.events import EventId, require_event
from forja.domain import AlarmKey, Diagnosis, EquipmentProfile

router = APIRouter(prefix="/api/v1", tags=["diagnostico"])

ALARM_NOTE_PT = (
    "O significado de um código de alarme depende do fabricante, do controlador, da aplicação "
    "e da versão de software. Sem correspondência exata, o alarme é 'não catalogado'."
)


def diagnosis_json(diagnosis: Diagnosis) -> dict[str, Any]:
    """Mesmo objeto que a CLI imprime: o contrato v1.0 serializado pelo Pydantic."""
    return diagnosis.model_dump(mode="json")


def alarm_key_for(profile: EquipmentProfile, code: str) -> AlarmKey:
    """Chave composta a partir do perfil. UNKNOWN permanece UNKNOWN (nunca se inventa versão)."""
    return AlarmKey(
        manufacturer=profile.controller.manufacturer,
        controller=profile.controller.model,
        application=profile.application,
        software_version=profile.controller.software_version,
        code=code,
    )


@router.get("/events/{event_id}/diagnosis")
async def get_diagnosis(event_id: EventId, container: ContainerDep) -> JSONResponse:
    """Diagnóstico v1.0 do evento. 404 se o evento não existe ou ainda não foi diagnosticado."""
    await require_event(container, event_id)
    diagnosis = await container.diagnoses_repo.get_for_event(event_id)
    if diagnosis is None:
        raise ApiError(
            404,
            "DIAGNOSIS_NOT_FOUND",
            "Ainda não há diagnóstico para este evento.",
            {"event_id": event_id},
        )
    if not isinstance(diagnosis, Diagnosis):
        diagnosis = Diagnosis.model_validate(diagnosis)
    return JSONResponse(diagnosis_json(diagnosis))


@router.get("/alarms/lookup")
async def alarm_lookup(
    container: ContainerDep,
    equipment_id: Annotated[str, Query(min_length=1, max_length=64)],
    code: Annotated[str, Query(min_length=1, max_length=16, pattern=r"^[A-Za-z0-9_\-]+$")],
) -> dict[str, Any]:
    """Procura o alarme pela chave composta do perfil. Candidatos são só sugestão."""
    profile = require_profile(container, equipment_id)
    key = alarm_key_for(profile, code.strip())
    lookup = container.store.alarms.lookup(key)
    return {
        "equipment_id": profile.id,
        "code": lookup.code,
        "key": jsonable(key),
        "catalogued": lookup.definition is not None,
        "title_pt": lookup.title_pt,
        "qualifier_pt": lookup.qualifier_pt,
        "definition": jsonable(lookup.definition),
        "candidates": jsonable(lookup.candidates),
        "note_pt": ALARM_NOTE_PT,
    }
