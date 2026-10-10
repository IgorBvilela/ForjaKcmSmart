"""Saúde do Edge em linguagem simples e consulta/exportação dos registros (serviço, comunicação,
auditoria). Só leitura."""

from __future__ import annotations

import csv
import io
import shutil
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from forja.api.deps import ContainerDep, jsonable, uptime_s
from forja.api.errors import ApiError
from forja.service.health import HealthInputs, build_health_report
from forja.service.logsetup import LOG_FILE_NAME, read_log_tail
from forja.version import __version__

router = APIRouter(prefix="/api/v1/system", tags=["sistema"])

LogSource = Literal["app", "comm", "audit"]
SOURCE_PT: dict[str, str] = {
    "app": "Serviço",
    "comm": "Comunicação",
    "audit": "Auditoria",
}


async def _stats(obj: Any) -> dict[str, Any] | None:
    fn = getattr(obj, "stats", None)
    if not callable(fn):
        return None
    try:
        result: dict[str, Any] = jsonable(await fn())
    except Exception:
        return None
    return result


def _disk(container: Any) -> tuple[int | None, int | None]:
    try:
        usage = shutil.disk_usage(container.paths.data_dir)
    except OSError:
        return None, None
    return int(usage.total), int(usage.free)


@router.get("/health-report")
async def health_report(request: Request, container: ContainerDep) -> dict[str, Any]:
    """Saúde de cada parte do Edge, com achados em português do mais grave ao mais leve."""
    rt = getattr(container, "runtime", None)
    jobs = getattr(rt, "jobs", None)
    bridge = getattr(rt, "bridge", None)
    hub = getattr(request.app.state, "stream_hub", None)
    total, free = _disk(container)
    inputs = HealthInputs(
        now=container.clock.now_utc(),
        uptime_s=uptime_s(container),
        version=__version__,
        profiles=dict(container.store.profiles),
        statuses=container.manager.statuses(),
        historian=await _stats(container.historian),
        core=await _stats(getattr(container, "core", None)),
        disk_total=total,
        disk_free=free,
        max_historian_gb=container.store.config.historian.max_historian_gb,
        jobs=({"runs": dict(jobs.runs), "errors": dict(jobs.errors)} if jobs is not None else None),
        bridge=(
            {
                "batches": bridge.batches,
                "transitions": bridge.transitions,
                "diagnoses": bridge.diagnoses,
                "errors": bridge.errors,
            }
            if bridge is not None
            else None
        ),
        sse=({"clients": hub.client_count, "dropped": hub.dropped} if hub is not None else None),
    )
    report: dict[str, Any] = jsonable(build_health_report(inputs))
    report["now_utc"] = jsonable(inputs.now)
    report["rules_loaded"] = len(getattr(container.rule_engine, "rules", ()) or ())
    return report


async def _entries(
    container: Any, source: LogSource, limit: int, level: str | None, equipment_id: str | None
) -> list[dict[str, Any]]:
    if source == "app":
        rows = read_log_tail(container.paths.logs_dir / LOG_FILE_NAME, limit=limit, min_level=level)
        return [
            {
                "ts": r["ts"],
                "level": r["level"],
                "origin": r["logger"],
                "message_pt": r["message"],
                "detail": r["detail"],
            }
            for r in rows
        ]
    if source == "comm":
        entries = await container.historian.comm_log(equipment_id, None, limit)
        return [
            {
                "ts": jsonable(e.ts_utc),
                "level": e.level,
                "origin": e.equipment_id,
                "message_pt": e.message_pt,
                "detail": jsonable(e.detail),
            }
            for e in entries
            if not level or e.level == level.upper() or level.upper() == "INFO"
        ]
    lister = getattr(getattr(container, "core", None), "audit_list", None)
    if not callable(lister):
        return []
    rows = await lister(limit)
    return [
        {
            "ts": jsonable(r.get("ts_utc")),
            "level": "INFO",
            "origin": r.get("user", ""),
            "message_pt": audit_message_pt(r),
            "detail": jsonable(
                {
                    "action": r.get("action"),
                    "entity_type": r.get("entity_type"),
                    "entity_id": r.get("entity_id"),
                    "before": r.get("before"),
                    "after": r.get("after"),
                }
            ),
        }
        for r in rows
    ]


AUDIT_ACTION_PT: dict[str, str] = {
    "EVENT_ACK": "Evento reconhecido",
    "COMM_CONFIG_SAVE": "Configuração de comunicação salva",
    "MAPPING_SAVE": "Mapping salvo",
    "COLLECTION_ON": "Coleta ativada",
    "COLLECTION_OFF": "Coleta pausada",
    "COMMISSIONING_OPEN": "Sessão de comissionamento aberta",
    "COMMISSIONING_CLOSE": "Sessão de comissionamento encerrada",
    "BACKUP_CREATE": "Backup criado",
    "EQUIPMENT_CREATE": "Equipamento cadastrado",
}


def audit_message_pt(row: dict[str, Any]) -> str:
    """Frase em português para a trilha de auditoria; o código interno fica no detalhe."""
    action = str(row.get("action", ""))
    label = AUDIT_ACTION_PT.get(action, "Alteração registrada")
    target = row.get("entity_id", "")
    reason = row.get("reason_pt")
    return f"{label} ({target})" + (f": {reason}" if reason else "")


@router.get("/logs")
async def logs(
    container: ContainerDep,
    source: LogSource = "app",
    limit: Annotated[int, Query(ge=1, le=2000)] = 200,
    level: Annotated[str | None, Query(pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")] = None,
    equipment_id: Annotated[str | None, Query(max_length=64)] = None,
) -> dict[str, Any]:
    """Registros mais recentes primeiro: serviço (arquivo), comunicação (banco) ou auditoria."""
    if equipment_id is not None and equipment_id not in container.store.profiles:
        raise ApiError(404, "EQUIPMENT_NOT_FOUND", "Equipamento não encontrado.")
    entries = await _entries(container, source, limit, level, equipment_id)
    return {"source": source, "source_pt": SOURCE_PT[source], "entries": entries}


@router.get("/logs.csv")
async def logs_csv(
    container: ContainerDep,
    source: LogSource = "app",
    limit: Annotated[int, Query(ge=1, le=20000)] = 5000,
) -> Response:
    """Exporta os registros (separador ';', BOM para o Excel em português)."""
    entries = await _entries(container, source, limit, None, None)
    buf = io.StringIO()
    buf.write("﻿")
    writer = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    writer.writerow(("instante", "nivel", "origem", "mensagem", "detalhe"))
    for e in entries:
        writer.writerow((e["ts"], e["level"], e["origin"], e["message_pt"], str(e["detail"] or "")))
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "content-disposition": f'attachment; filename="forja_logs_{source}.csv"',
            "cache-control": "no-store",
        },
    )


__all__ = ["router"]
