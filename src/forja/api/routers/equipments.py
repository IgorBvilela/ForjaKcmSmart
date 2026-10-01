"""Equipamentos: lista, perfil, status de runtime e snapshot ao vivo (com STALE e idade)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any

from fastapi import APIRouter
from fastapi import Path as PathParam

from forja.api.deps import (
    ContainerDep,
    jsonable,
    quality_view,
    require_profile,
    sample_age_s,
)
from forja.domain import TAGS, EquipmentProfile, EquipmentRuntimeStatus, Sample

router = APIRouter(prefix="/api/v1/equipments", tags=["equipamentos"])

EquipmentId = Annotated[str, PathParam(max_length=64, description="Id do equipamento")]


def equipment_summary(profile: EquipmentProfile) -> dict[str, Any]:
    """Resumo do perfil para listas e cards."""
    return {
        "id": profile.id,
        "name": profile.name,
        "display_path": profile.display_path,
        "application": profile.application,
        "application_evidence": profile.application_evidence.value,
        "is_example": profile.is_example,
        "driver": profile.communication.driver,
        "data_source": "SIMULATED" if profile.is_simulated else "EQUIPMENT",
        "needs_configuration": profile.communication.needs_configuration,
        "mapping_profile": profile.mapping_profile,
    }


def status_view(status: EquipmentRuntimeStatus) -> dict[str, Any]:
    """EquipmentRuntimeStatus com rótulos em português."""
    data: dict[str, Any] = jsonable(status)
    data["connection_pt"] = status.connection.label_pt
    data["support_state_pt"] = status.support_state.label_pt
    return data


def _snapshot_samples(snapshot: Any) -> dict[str, Sample]:
    """Extrai {tag: Sample} do LiveSnapshot do bloco 3, aceitando dict ou objeto."""
    # INTEGRACAO: ajustar se LiveSnapshot (forja.acquisition.live) expuser outro nome de campo.
    if isinstance(snapshot, Mapping):
        return {str(k): v for k, v in snapshot.items() if isinstance(v, Sample)}
    for attr in ("samples", "tags", "values"):
        inner = getattr(snapshot, attr, None)
        if isinstance(inner, Mapping):
            return {str(k): v for k, v in inner.items() if isinstance(v, Sample)}
    return {}


def _snapshot_ages(snapshot: Any) -> dict[str, float | None]:
    """Idades {tag: s} calculadas pelo manager (relógio monotônico do momento da leitura)."""
    ages = getattr(snapshot, "ages_s", None)
    if isinstance(ages, Mapping):
        return {str(k): v for k, v in ages.items()}
    return {}


def tag_view(
    sample: Sample, now_mono_ns: int, now_utc: Any, age_s: float | None = None
) -> dict[str, Any]:
    """Uma tag ao vivo: valor, unidade, qualidade, idade e textos em português.

    `age_s` vem do LiveSnapshot quando o manager a calculou; senão deriva do próprio sample.
    """
    meta = TAGS.get(sample.tag)
    view: dict[str, Any] = {
        "tag": sample.tag,
        "label_pt": meta.label_pt if meta else sample.tag,
        "unit": meta.unit if meta else "",
        "kind": meta.kind.value if meta else None,
        "decimals": meta.decimals if meta else 1,
        "explanation_pt": meta.explanation_pt if meta else "",
        "value": jsonable(sample.value),
        "ts_utc": jsonable(sample.ts_utc),
        "age_s": age_s if age_s is not None else sample_age_s(sample, now_mono_ns, now_utc),
        "source": sample.source,
        "reason_pt": sample.reason_pt,
        "raw_hex": sample.raw.hex() if sample.raw is not None else None,
    }
    view.update(quality_view(sample.quality))
    return view


def build_live_view(container: Any, profile: EquipmentProfile) -> dict[str, Any]:
    """Snapshot ao vivo de um equipamento. STALE já aplicado pelo manager; aqui só expomos."""
    manager = container.manager
    status: EquipmentRuntimeStatus = manager.status(profile.id)
    snapshot = manager.live(profile.id)  # INTEGRACAO: LiveSnapshot do bloco 3
    samples = _snapshot_samples(snapshot)
    ages = _snapshot_ages(snapshot)
    now_mono_ns = container.clock.monotonic_ns()
    now_utc = container.clock.now_utc()
    tags = [tag_view(samples[tag], now_mono_ns, now_utc, ages.get(tag)) for tag in sorted(samples)]
    return {
        "equipment_id": profile.id,
        "name": profile.name,
        "data_source": "SIMULATED" if profile.is_simulated else "EQUIPMENT",
        "connection": status.connection.value,
        "connection_pt": status.connection.label_pt,
        "is_stale": bool(getattr(snapshot, "is_stale", status.is_stale)),
        "stale_for_s": getattr(snapshot, "stale_for_s", status.stale_for_s),
        "last_read_utc": jsonable(status.last_read_utc),
        "last_ok_utc": jsonable(status.last_ok_utc),
        "generated_at_utc": jsonable(now_utc),
        "tags": tags,
    }


@router.get("")
async def list_equipments(container: ContainerDep) -> dict[str, Any]:
    """Lista os equipamentos configurados."""
    profiles = container.store.profiles
    return {
        "equipments": [equipment_summary(p) for p in profiles.values()],
        "count": len(profiles),
    }


@router.get("/{equipment_id}")
async def get_equipment(equipment_id: EquipmentId, container: ContainerDep) -> dict[str, Any]:
    """Perfil completo do equipamento e resumo do mapping associado."""
    profile = require_profile(container, equipment_id)
    mapping = container.store.mapping_for(profile.id)
    return {
        "profile": jsonable(profile),
        "mapping": {
            "mapping_id": mapping.mapping_id,
            "version": mapping.version,
            "driver": mapping.driver,
            "source": mapping.source,
            "entries": len(mapping.entries),
            "readable": len(mapping.readable_entries),
            "unknown": len(mapping.unknown_entries),
            "tags": [e.semantic_tag for e in mapping.entries],
        },
    }


@router.get("/{equipment_id}/status")
async def get_status(equipment_id: EquipmentId, container: ContainerDep) -> dict[str, Any]:
    """Estado de runtime (conexão, latência, erros, reconexões)."""
    profile = require_profile(container, equipment_id)
    return status_view(container.manager.status(profile.id))


@router.get("/{equipment_id}/live")
async def get_live(equipment_id: EquipmentId, container: ContainerDep) -> dict[str, Any]:
    """Snapshot ao vivo: tags com valor, unidade, qualidade, idade e textos."""
    profile = require_profile(container, equipment_id)
    return build_live_view(container, profile)
