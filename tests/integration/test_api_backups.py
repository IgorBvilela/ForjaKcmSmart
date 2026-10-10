"""Backup pela API e rotina automática, sobre o Container REAL (SQLite em pasta temporária)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

from forja.api.app import create_app
from forja.config.models import BackupConfig
from forja.infra import FakeClock
from forja.service import backups as svc
from forja.service.container import Container
from forja.service.runner import build_container, stop
from tests.integration.test_api_real_container import tmp_paths

pytestmark = pytest.mark.integration

ZONE = ZoneInfo("America/Sao_Paulo")


@pytest.fixture
async def real(tmp_path: Path) -> AsyncIterator[tuple[Container, FakeClock]]:
    clock = FakeClock(datetime(2026, 10, 10, 12, 0, tzinfo=UTC))
    container = await build_container(tmp_paths(tmp_path), clock)
    try:
        yield container, clock
    finally:
        await stop(container, timeout_s=2)


async def _client(container: Container) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=create_app(container))
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


async def test_criar_listar_e_conferir_com_configuracao(
    real: tuple[Container, FakeClock],
) -> None:
    container, _ = real
    async with await _client(container) as c:
        resp = await c.post(
            "/api/v1/backups", json={"user": "tecnico", "reason_pt": "antes da visita"}
        )
        assert resp.status_code == 201, resp.text
        item = resp.json()
        assert item["has_config"] is True
        assert {f["kind"] for f in item["files"]} == {"historian", "core", "config"}
        assert "--sim" in item["restore_command"]

        listing = (await c.get("/api/v1/backups")).json()
        assert listing["count"] == 1
        assert listing["backups"][0]["name"] == item["name"]
        assert listing["auto"] is True
        assert listing["next_run_utc"] is not None

        ok = (await c.get(f"/api/v1/backups/{item['name']}/verify")).json()
        assert ok["ok"] is True

        config_zip = next(Path(item["path"]).glob("config_*.zip"))
        config_zip.write_bytes(config_zip.read_bytes()[:-20] + b"x" * 20)
        bad = (await c.get(f"/api/v1/backups/{item['name']}/verify")).json()
        assert bad["ok"] is False
        assert "checksum" in bad["message_pt"]

        assert (await c.get("/api/v1/backups/backup_nao_existe/verify")).status_code == 404
        assert (await c.get("/api/v1/backups/..%2F..%2Fsegredo/verify")).status_code in (404, 422)

    audit = await container.core.audit_list()
    assert audit[0]["action"] == "BACKUP_CREATE"
    assert audit[0]["user"] == "tecnico"


async def test_rotina_automatica_cria_e_guarda_so_os_ultimos(
    real: tuple[Container, FakeClock],
) -> None:
    container, clock = real
    job = svc.BackupJob(
        container.historian,
        container.core,
        container.paths,
        BackupConfig(auto=True, schedule="02:00", keep_last=2),
        clock,
        ZONE,
        audit=container.core.audit,
    )
    names = []
    for _ in range(3):
        result = await job.run_once()
        assert result is not None
        names.append(result["name"])
        clock.advance(3600)
    left = [b["name"] for b in svc.list_backups(container.paths)]
    assert left == sorted(names, reverse=True)[:2]
    assert job.last_result is not None
    assert job.last_result["removed"] == [names[0]]
    audit = await container.core.audit_list()
    assert audit[0]["user"] == "sistema"
    assert audit[0]["action"] == "BACKUP_CREATE"


def test_proximo_horario_no_fuso_da_planta() -> None:
    before = datetime(2026, 10, 10, 4, 30, tzinfo=UTC)  # 01:30 em São Paulo
    after = datetime(2026, 10, 10, 6, 0, tzinfo=UTC)  # 03:00 em São Paulo
    assert svc.next_run(before, "02:00", ZONE) == datetime(2026, 10, 10, 5, 0, tzinfo=UTC)
    assert svc.next_run(after, "02:00", ZONE) == datetime(2026, 10, 11, 5, 0, tzinfo=UTC)
    assert svc.next_run(after, "hora errada", ZONE) == datetime(2026, 10, 11, 5, 0, tzinfo=UTC)


def test_pasta_fora_dos_backups_e_recusada(tmp_path: Path) -> None:
    paths = tmp_paths(tmp_path)
    paths.backups_dir.mkdir(parents=True)
    from forja.domain import ForjaError

    with pytest.raises(ForjaError):
        svc.backup_folder(paths, "backup_..")
    with pytest.raises(ForjaError):
        svc.backup_folder(paths, "outra_coisa")
