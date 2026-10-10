"""Backup pela interface: listar, criar agora (auditado) e conferir. Restaurar exige o serviço
parado, por isso fica na linha de comando; a tela mostra o comando pronto para cada backup."""

from __future__ import annotations

import logging
import sys
from typing import Annotated, Any

from fastapi import APIRouter
from fastapi import Path as PathParam
from pydantic import BaseModel, ConfigDict, Field

from forja.api.deps import ContainerDep, jsonable
from forja.api.errors import ApiError
from forja.config.paths import is_frozen
from forja.domain import ForjaError
from forja.events.plant_time import resolve_zone
from forja.service import backups as svc

logger = logging.getLogger("forja.api")

router = APIRouter(prefix="/api/v1/backups", tags=["backup"])

BackupName = Annotated[
    str, PathParam(min_length=8, max_length=80, pattern=r"^backup_[0-9A-Za-z_]+$")
]
USER_PATTERN = r"^[\w .@\-]+$"
RESTORE_NOTE_PT = (
    "Restaurar substitui os bancos atuais. Pare o serviço (services.msc ou Stop-Service ForjaKCM), "
    "rode o comando num PowerShell de Administrador e inicie o serviço de novo. Antes de "
    "restaurar, faça um backup do estado atual."
)


class CreateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: str = Field(min_length=1, max_length=64, pattern=USER_PATTERN)
    reason_pt: str = Field(default="", max_length=2000)


def _cli() -> str:
    return f'& "{sys.executable}"' if is_frozen() else "forja"


def _with_command(item: dict[str, Any], home: str) -> dict[str, Any]:
    home_arg = "" if is_frozen() else f' --home "{home}"'
    return {
        **item,
        "restore_command": f'{_cli()} backup restore "{item["path"]}" --sim{home_arg}',
        "restore_config_command": (
            f'{_cli()} backup restore "{item["path"]}" --sim --configuracao{home_arg}'
        ),
    }


@router.get("")
async def list_backups(container: ContainerDep) -> dict[str, Any]:
    """Rotina automática (horário, quantos guardar, próxima execução) e os backups na pasta."""
    cfg = container.store.config.backup
    paths = container.paths
    job = getattr(container.runtime, "backup_job", None)
    if job is not None:
        next_utc = job.next_run_utc()
    elif cfg.auto:
        zone = resolve_zone(container.store.config.edge.timezone)
        next_utc = svc.next_run(container.clock.now_utc(), cfg.schedule, zone)
    else:
        next_utc = None
    items = [_with_command(b, str(paths.home)) for b in svc.list_backups(paths)]
    return {
        "auto": cfg.auto,
        "schedule": cfg.schedule,
        "keep_last": cfg.keep_last,
        "next_run_utc": jsonable(next_utc),
        "folder": str(paths.backups_dir),
        "restore_note_pt": RESTORE_NOTE_PT,
        "count": len(items),
        "backups": items,
    }


@router.post("", status_code=201)
async def create_backup(body: CreateBody, container: ContainerDep) -> dict[str, Any]:
    """Backup consistente agora: bancos e configuração, com manifesto conferido. Auditado."""
    try:
        item = await svc.create(container.historian, container.core, container.paths)
    except ForjaError as exc:
        raise ApiError(501, "BACKUP_UNAVAILABLE", str(exc)) from exc
    audit = getattr(container.core, "audit", None)
    if callable(audit):
        await audit(
            user=body.user,
            action="BACKUP_CREATE",
            entity_type="backup",
            entity_id=item["name"],
            before=None,
            after={"automatic": False},
            reason_pt=body.reason_pt,
        )
    logger.info("backup %s criado por %s", item["name"], body.user)
    return _with_command(item, str(container.paths.home))


@router.get("/{name}/verify")
async def verify_backup(name: BackupName, container: ContainerDep) -> dict[str, Any]:
    """Confere checksum e integridade de cada arquivo do backup. Não muda nada."""
    try:
        return svc.verify(container.paths, name)
    except ForjaError as exc:
        raise ApiError(404, "BACKUP_NOT_FOUND", str(exc)) from exc


__all__ = ["router"]
