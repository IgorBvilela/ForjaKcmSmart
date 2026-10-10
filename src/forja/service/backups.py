"""Backups do Edge: criar (bancos + configuração), listar, conferir, rotina diária e limpeza.

A rotina segue `backup` em config/forja.yaml: `auto`, `schedule` (HH:MM no fuso da planta) e
`keep_last` (quantos backups automáticos manter). Só pastas `backup_*` com manifesto válido entram
na limpeza; nada mais é apagado. Restaurar exige o serviço parado e fica na linha de comando.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from collections.abc import Awaitable, Callable
from datetime import datetime, time, timedelta, tzinfo
from pathlib import Path
from typing import Any, Final

from forja.config import ForjaPaths
from forja.config.models import BackupConfig
from forja.domain import Clock, ForjaError

logger = logging.getLogger(__name__)

BACKUP_PREFIX: Final = "backup_"
SYSTEM_USER: Final = "sistema"

AuditFn = Callable[..., Awaitable[Any]]


def parse_schedule(schedule: str) -> time:
    """'02:00' -> 02:00. Formato inválido cai para 02:00 com aviso no log."""
    try:
        hour, minute = (int(p) for p in schedule.strip().split(":", 1))
        return time(hour=hour, minute=minute)
    except (ValueError, TypeError):
        logger.warning("backup.schedule inválido (%r); usando 02:00", schedule)
        return time(2, 0)


def next_run(now_utc: datetime, schedule: str, zone: tzinfo) -> datetime:
    """Próximo horário `schedule` (fuso da planta) estritamente depois de `now_utc`, em UTC."""
    at = parse_schedule(schedule)
    local = now_utc.astimezone(zone)
    candidate = local.replace(hour=at.hour, minute=at.minute, second=0, microsecond=0)
    if candidate <= local:
        candidate += timedelta(days=1)
    return candidate.astimezone(now_utc.tzinfo)


def _folder_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def list_backups(paths: ForjaPaths) -> list[dict[str, Any]]:
    """Backups em backups_dir, do mais novo para o mais antigo. Manifesto ilegível aparece com
    o motivo, sem esconder a pasta."""
    from forja.historian.backup import read_manifest

    root = paths.backups_dir
    if not root.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for folder in sorted(root.iterdir(), key=lambda p: p.name, reverse=True):
        if not folder.is_dir() or not folder.name.startswith(BACKUP_PREFIX):
            continue
        item: dict[str, Any] = {
            "name": folder.name,
            "path": str(folder),
            "size_bytes": _folder_size(folder),
        }
        try:
            manifest = read_manifest(folder)
        except (ForjaError, ValueError) as exc:
            item.update({"valid": False, "error_pt": str(exc)})
        else:
            item.update(
                {
                    "valid": True,
                    "created_at_utc": manifest.created_at_utc.isoformat(),
                    "app_version": manifest.app_version,
                    "files": [
                        {"kind": f.kind, "file_name": f.file_name, "size_bytes": f.size_bytes}
                        for f in manifest.files
                    ],
                    "has_config": any(f.kind == "config" for f in manifest.files),
                }
            )
        out.append(item)
    return out


def verify(paths: ForjaPaths, name: str) -> dict[str, Any]:
    """Confere checksum e integridade de um backup pelo nome da pasta."""
    from forja.historian.backup import verify_backup

    folder = backup_folder(paths, name)
    try:
        manifest = verify_backup(folder)
    except ForjaError as exc:
        return {"name": name, "ok": False, "message_pt": str(exc)}
    return {
        "name": name,
        "ok": True,
        "message_pt": f"Backup íntegro: {len(manifest.files)} arquivo(s) conferido(s).",
    }


def backup_folder(paths: ForjaPaths, name: str) -> Path:
    """Pasta de um backup pelo nome, sempre dentro de backups_dir."""
    if not name.startswith(BACKUP_PREFIX) or "/" in name or "\\" in name or ".." in name:
        raise ForjaError(f"nome de backup inválido: {name!r}")
    folder = (paths.backups_dir / name).resolve()
    if folder.parent != paths.backups_dir.resolve() or not folder.is_dir():
        raise ForjaError(f"backup não encontrado: {name}")
    return folder


def prune(paths: ForjaPaths, keep_last: int) -> list[str]:
    """Apaga os backups válidos mais antigos além de `keep_last`. Devolve os nomes apagados."""
    valid = [b for b in list_backups(paths) if b.get("valid")]
    doomed = valid[max(0, keep_last) :]
    removed: list[str] = []
    for item in doomed:
        try:
            shutil.rmtree(item["path"])
        except OSError:
            logger.exception("backup %s: não foi possível apagar", item["name"])
            continue
        removed.append(str(item["name"]))
    return removed


async def create(historian: Any, core: Any, paths: ForjaPaths) -> dict[str, Any]:
    """Backup consistente agora (bancos + configuração). Devolve o item da lista."""
    from forja.historian.backup import backup_all
    from forja.historian.writer import timestamp_label

    if not callable(getattr(historian, "backup", None)) or not callable(
        getattr(core, "backup", None)
    ):
        raise ForjaError("backup indisponível nesta montagem do serviço")
    manifest = await backup_all(historian, core, paths)
    name = f"{BACKUP_PREFIX}{timestamp_label(manifest.created_at_utc)}"
    return next(
        (b for b in list_backups(paths) if b["name"] == name),
        {"name": name, "path": str(paths.backups_dir / name), "valid": True},
    )


class BackupJob:
    """Backup automático diário no horário de `schedule`, com limpeza por `keep_last`."""

    def __init__(
        self,
        historian: Any,
        core: Any,
        paths: ForjaPaths,
        config: BackupConfig,
        clock: Clock,
        zone: tzinfo,
        *,
        audit: AuditFn | None = None,
    ) -> None:
        self._historian = historian
        self._core = core
        self._paths = paths
        self._config = config
        self._clock = clock
        self._zone = zone
        self._audit = audit
        self.runs = 0
        self.errors = 0
        self.last_result: dict[str, Any] | None = None

    def next_run_utc(self) -> datetime:
        return next_run(self._clock.now_utc(), self._config.schedule, self._zone)

    async def run_once(self) -> dict[str, Any] | None:
        try:
            item = await create(self._historian, self._core, self._paths)
            removed = await asyncio.to_thread(prune, self._paths, self._config.keep_last)
        except asyncio.CancelledError:
            raise
        except Exception:
            self.errors += 1
            logger.exception("backup automático falhou")
            return None
        self.runs += 1
        self.last_result = {**item, "removed": removed}
        logger.info(
            "backup automático %s criado; %d antigo(s) apagado(s)", item["name"], len(removed)
        )
        if self._audit is not None:
            try:
                await self._audit(
                    user=SYSTEM_USER,
                    action="BACKUP_CREATE",
                    entity_type="backup",
                    entity_id=item["name"],
                    before=None,
                    after={"automatic": True, "removed": removed},
                    reason_pt="backup automático diário",
                )
            except Exception:
                logger.exception("backup automático: auditoria não gravada")
        return self.last_result

    async def run_forever(self) -> None:
        while True:
            wait_s = (self.next_run_utc() - self._clock.now_utc()).total_seconds()
            await self._clock.sleep(max(1.0, wait_s))
            await self.run_once()


__all__ = [
    "BACKUP_PREFIX",
    "BackupJob",
    "backup_folder",
    "create",
    "list_backups",
    "next_run",
    "parse_schedule",
    "prune",
    "verify",
]
