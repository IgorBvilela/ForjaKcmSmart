"""Comandos de administração da instalação: init, backup (create, verify, restore) e service.

Nenhum deles fala com o KCM. `backup restore` exige o serviço parado: ele substitui os bancos.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from forja.config import resolve_paths
from forja.domain import ForjaError


class AdminError(ForjaError):
    """Erro de uso com texto em português para o terminal."""


def add_admin_commands(
    sub: argparse._SubParsersAction[argparse.ArgumentParser], common: argparse.ArgumentParser
) -> None:
    sub.add_parser(
        "init",
        parents=[common],
        help="Prepara a pasta de dados: copia a configuração inicial sem sobrescrever nada.",
    )
    backup = sub.add_parser("backup", help="Cópia de segurança dos bancos locais.")
    bsub = backup.add_subparsers(dest="backup_command", required=True, metavar="ação")
    create = bsub.add_parser("create", parents=[common], help="Cria backup consistente.")
    create.add_argument("--dest", metavar="PASTA", help="Pasta de destino (padrão: var/backups).")
    verify = bsub.add_parser("verify", help="Confere checksum e integridade de um backup.")
    verify.add_argument("folder", metavar="PASTA_DO_BACKUP")
    restore = bsub.add_parser(
        "restore", parents=[common], help="Restaura um backup (serviço PARADO)."
    )
    restore.add_argument("folder", metavar="PASTA_DO_BACKUP")
    restore.add_argument(
        "--sim", action="store_true", help="Confirma a substituição dos bancos atuais."
    )
    restore.add_argument(
        "--configuracao",
        action="store_true",
        help="Também restaura config/ e knowledge/ (a atual fica guardada antes).",
    )
    audit = sub.add_parser("audit", help="Trilha de auditoria.")
    asub = audit.add_subparsers(dest="audit_command", required=True, metavar="ação")
    asub.add_parser(
        "verify", parents=[common], help="Confere a cadeia de hash da trilha de auditoria."
    )
    service = sub.add_parser("service", help="Serviço Windows (usado pelo instalador).")
    ssub = service.add_subparsers(dest="service_command", required=True, metavar="ação")
    ssub.add_parser("run", help="Ponto de entrada chamado pelo gerenciador de serviços.")


def cmd_init(args: argparse.Namespace) -> int:
    from forja.service.seed import seed_home

    paths = resolve_paths(getattr(args, "home", None))
    try:
        created = seed_home(paths.home)
    except FileNotFoundError as exc:
        raise AdminError(str(exc)) from exc
    print(f"Pasta de dados: {paths.home}")
    if created:
        print(f"{len(created)} arquivo(s) de configuração inicial copiado(s).")
    else:
        print("Configuração já existente preservada; nada foi sobrescrito.")
    return 0


async def _backup_create(home: str | None, dest: str | None) -> Path:
    from forja.config import ConfigStore
    from forja.historian.backup import backup_all
    from forja.historian.core_store import SqliteCoreStore
    from forja.historian.sqlite import SqliteHistorian
    from forja.historian.writer import timestamp_label
    from forja.infra import SystemClock

    paths = resolve_paths(home).ensure()
    store = ConfigStore(paths).load_all()
    clock = SystemClock()
    historian = SqliteHistorian(paths.historian_db, store.config.historian, clock)
    core = SqliteCoreStore(paths.core_db, clock)
    await historian.open()
    await core.open()
    try:
        manifest = await backup_all(historian, core, paths, Path(dest) if dest else None)
    finally:
        await historian.close()
        await core.close()
    if dest:
        return Path(dest)
    return paths.backups_dir / f"backup_{timestamp_label(manifest.created_at_utc)}"


def cmd_backup(args: argparse.Namespace) -> int:
    from forja.historian.backup import restore_all, restore_config, verify_backup

    if args.backup_command == "create":
        folder = asyncio.run(_backup_create(getattr(args, "home", None), args.dest))
        print(f"Backup criado e conferido em {folder}")
        return 0
    if args.backup_command == "verify":
        manifest = verify_backup(Path(args.folder))
        print(
            f"Backup íntegro: {len(manifest.files)} arquivo(s), criado em "
            f"{manifest.created_at_utc.isoformat()} (versão {manifest.app_version})."
        )
        return 0
    if args.backup_command == "restore":
        if not args.sim:
            raise AdminError(
                "a restauração substitui os bancos atuais. Pare o serviço e repita com --sim."
            )
        if service_running():
            raise AdminError(
                "o serviço Forja KCM está em execução. Pare o serviço antes de restaurar "
                "(services.msc ou: sc.exe stop ForjaKCM)."
            )
        paths = resolve_paths(getattr(args, "home", None))
        asyncio.run(restore_all(Path(args.folder), paths))
        print(f"Bancos restaurados em {paths.data_dir}.")
        if args.configuracao:
            from forja.infra import SystemClock

            safety = asyncio.run(restore_config(Path(args.folder), paths, SystemClock().now_utc()))
            print(f"Configuração restaurada. A anterior ficou em {safety}.")
        print("Inicie o serviço de novo.")
        return 0
    raise AdminError(f"ação desconhecida: {args.backup_command!r}")


async def _audit_verify(home: str | None) -> dict[str, object]:
    from forja.historian.core_store import SqliteCoreStore
    from forja.infra import SystemClock

    paths = resolve_paths(home).ensure()
    core = SqliteCoreStore(paths.core_db, SystemClock())
    await core.open()
    try:
        return await core.verify_audit()
    finally:
        await core.close()


def cmd_audit(args: argparse.Namespace) -> int:
    if args.audit_command == "verify":
        result = asyncio.run(_audit_verify(getattr(args, "home", None)))
        print(result["message_pt"])
        return 0 if result["ok"] else 1
    raise AdminError(f"ação desconhecida: {args.audit_command!r}")


def service_running() -> bool:
    """True quando o serviço do Windows está instalado e rodando. Fora do Windows, False."""
    if sys.platform != "win32":
        return False
    try:
        import win32service
        import win32serviceutil

        from forja.service.winservice import SERVICE_NAME

        status = win32serviceutil.QueryServiceStatus(SERVICE_NAME)
    except Exception:  # serviço não instalado ou sem permissão de consulta
        return False
    return bool(status[1] != win32service.SERVICE_STOPPED)


def cmd_service(args: argparse.Namespace) -> int:
    if sys.platform != "win32":
        raise AdminError("serviço disponível só no Windows")
    if args.service_command == "run":
        from forja.service.winservice import run_as_service

        return run_as_service()
    raise AdminError(f"ação desconhecida: {args.service_command!r}")


__all__ = [
    "AdminError",
    "add_admin_commands",
    "cmd_audit",
    "cmd_backup",
    "cmd_init",
    "cmd_service",
    "service_running",
]
