"""Dependências compartilhadas das rotas: container, perfil, serialização segura.

A API recebe um Container pronto (bloco 3) e programa contra as portas do domínio. Aqui ficam os
utilitários que todas as rotas usam. Nada aqui inicia aquisição.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Iterable, Mapping
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import Depends, Request
from pydantic import BaseModel

from forja.api.errors import ApiError
from forja.domain import EquipmentProfile, Quality, Sample

if TYPE_CHECKING:  # INTEGRACAO: tipo real vem do bloco 3 (forja.service.container.Container)
    from forja.service.container import Container
else:  # em runtime a API usa duck typing contra os nomes do contrato
    Container = Any

DEV_MODE_MARKER = "desenvolvimento"
"""Modo dev quando `edge.name` contém esta palavra (contrato: /docs só em desenvolvimento)."""

MAX_ID_ECHO = 64


def get_container(request: Request) -> Any:
    """Container guardado em `app.state` por `create_app`."""
    return request.app.state.container


ContainerDep = Annotated[Any, Depends(get_container)]


def is_dev_mode(edge_name: str) -> bool:
    """Modo desenvolvimento habilita /docs e /openapi.json."""
    return DEV_MODE_MARKER in edge_name.casefold()


def require_profile(container: Any, equipment_id: str) -> EquipmentProfile:
    """Perfil do equipamento ou 404 com envelope."""
    profile: EquipmentProfile | None = container.store.profiles.get(equipment_id)
    if profile is None:
        shown = equipment_id[:MAX_ID_ECHO]
        raise ApiError(
            404,
            "EQUIPMENT_NOT_FOUND",
            f"Equipamento não encontrado: {shown}",
            {"equipment_id": shown},
        )
    return profile


def data_source_for(profiles: Iterable[EquipmentProfile]) -> str:
    """SIMULATED | EQUIPMENT | MIXED conforme os drivers dos perfis carregados."""
    simulated = 0
    real = 0
    for p in profiles:
        if p.is_simulated:
            simulated += 1
        else:
            real += 1
    if real and simulated:
        return "MIXED"
    if real:
        return "EQUIPMENT"
    return "SIMULATED"


def data_source_label_pt(data_source: str) -> str:
    """Rótulo honesto para a UI."""
    return {
        "SIMULATED": "DADOS SIMULADOS",
        "EQUIPMENT": "DADOS DO EQUIPAMENTO",
        "MIXED": "DADOS MISTOS (simulados e do equipamento)",
    }.get(data_source, "ORIGEM DESCONHECIDA")


def uptime_s(container: Any) -> float:
    """Segundos desde `started_at_utc`, pelo relógio do container."""
    started = getattr(container, "started_at_utc", None)
    if started is None:
        return 0.0
    return max(0.0, float((container.clock.now_utc() - started).total_seconds()))


def sample_age_s(sample: Sample, now_mono_ns: int, now_utc: datetime) -> float | None:
    """Idade da amostra. Prefere o relógio monotônico; cai para o de parede se não houver."""
    if sample.ts_mono_ns is not None:
        return max(0.0, (now_mono_ns - sample.ts_mono_ns) / 1e9)
    if sample.ts_utc.tzinfo is None:
        return None
    return max(0.0, (now_utc - sample.ts_utc).total_seconds())


def quality_view(quality: Quality) -> dict[str, Any]:
    """Qualidade com rótulo em português."""
    return {
        "quality": quality.value,
        "quality_pt": quality.label_pt,
        "is_usable": quality.is_usable_value,
    }


def jsonable(obj: Any) -> Any:
    """Converte modelos, enums, datas e bytes em tipos JSON puros.

    `bytes` vira hexadecimal (o padrão do Pydantic exige UTF-8 e quebra com payload bruto).
    NaN/inf viram null: a UI nunca recebe número inválido.
    """
    if obj is None or isinstance(obj, bool | int):
        return obj
    if isinstance(obj, Enum):
        return jsonable(obj.value)
    if isinstance(obj, str):
        return obj
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, bytes | bytearray | memoryview):
        return bytes(obj).hex()
    if isinstance(obj, BaseModel):
        return jsonable(obj.model_dump(mode="python"))
    if isinstance(obj, Mapping):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple | set | frozenset):
        return [jsonable(v) for v in obj]
    if isinstance(obj, Path):
        return str(obj)
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: jsonable(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    return str(obj)
