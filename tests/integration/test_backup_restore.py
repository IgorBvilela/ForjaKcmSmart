"""Backup dos dois bancos com manifesto; restore valida checksum antes de tocar em qualquer um."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import pytest

from forja.config.models import HistorianConfig
from forja.config.paths import ForjaPaths
from forja.domain import CommLogEntry, HistorianError
from forja.historian import (
    MANIFEST_NAME,
    BackupManifest,
    SqliteCoreStore,
    SqliteHistorian,
    backup_all,
    restore_all,
    verify_backup,
)
from forja.historian.backup import check_integrity, sha256_file
from forja.historian.writer import connect_immutable
from forja.infra.clock import FakeClock
from forja.version import __version__
from tests.integration._historian_helpers import EQ, make_diagnosis, make_event, series_1hz

pytestmark = pytest.mark.integration


def make_paths(root: Path) -> ForjaPaths:
    return ForjaPaths(
        home=root,
        config_dir=root / "config",
        knowledge_dir=root / "knowledge",
        data_dir=root / "var",
        logs_dir=root / "var" / "logs",
        backups_dir=root / "var" / "backups",
    ).ensure()


class Stores:
    def __init__(self, paths: ForjaPaths, clock: FakeClock) -> None:
        self.paths = paths
        self.clock = clock
        self.historian = SqliteHistorian(
            paths.historian_db, HistorianConfig(store_on_change=False), clock
        )
        self.core = SqliteCoreStore(paths.core_db, clock)

    async def open(self) -> None:
        await self.historian.open()
        await self.core.open()

    async def close(self) -> None:
        await self.core.close()
        await self.historian.close()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
async def stores(tmp_path: Path, clock: FakeClock) -> AsyncIterator[Stores]:
    s = Stores(make_paths(tmp_path), clock)
    await s.open()
    try:
        yield s
    finally:
        await s.close()


EXPECTED_HIST = {
    "samples": 120,
    "samples_latest": 2,
    "samples_agg_1m": 0,
    "samples_agg_1h": 0,
    "comm_log": 1,
}
EXPECTED_CORE = {"events": 2, "diagnoses": 1, "audit_log": 2}


async def seed(s: Stores) -> None:
    now = s.clock.now_utc()
    await s.historian.write(series_1hz(now, 60, "mass_flow", 10.0))
    await s.historian.write(series_1hz(now, 60, "belt_load", 1.5))
    await s.historian.log_comm(
        CommLogEntry(ts_utc=now, equipment_id=EQ, level="INFO", kind="CONNECTED", message_pt="ok")
    )
    e1 = make_event(s.clock, dedupe_key="EQ:R-1")
    e2 = make_event(s.clock, dedupe_key="EQ:R-2", start=now + timedelta(minutes=1))
    await s.core.save(e1)
    await s.core.save(e2)
    await s.core.save(make_diagnosis(e1, s.clock))
    await s.core.audit("maria", "ACK", "event", e1.id, None, {"status": "ACKNOWLEDGED"})
    await s.core.audit("sistema", "BACKUP", "database", "ambos", None, None)


async def test_backup_all_gera_arquivos_e_manifesto(stores: Stores, clock: FakeClock) -> None:
    await seed(stores)
    manifest = await backup_all(stores.historian, stores.core, stores.paths)

    dest = stores.paths.backups_dir / "backup_20260101T120000Z"
    assert (dest / MANIFEST_NAME).is_file()
    hist = manifest.file_for("historian")
    core = manifest.file_for("core")
    assert hist.file_name == "forja_historian_20260101T120000Z.db"
    assert core.file_name == "forja_core_20260101T120000Z.db"
    assert hist.sha256 == sha256_file(dest / hist.file_name)
    assert core.sha256 == sha256_file(dest / core.file_name)
    assert hist.size_bytes == (dest / hist.file_name).stat().st_size
    assert hist.tables == EXPECTED_HIST
    assert core.tables == EXPECTED_CORE
    assert hist.schema_version == 1
    assert core.schema_version == 1
    assert manifest.created_at_utc == clock.now_utc()
    assert manifest.app_version == __version__
    reread = BackupManifest.model_validate_json((dest / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert reread == manifest
    # nada alem dos tres arquivos (sem -wal/-shm sobrando na pasta do backup)
    assert sorted(p.name for p in dest.iterdir()) == sorted(
        [hist.file_name, core.file_name, MANIFEST_NAME]
    )
    assert verify_backup(dest) == manifest
    # o banco vivo segue funcionando depois do backup
    await stores.historian.write(series_1hz(clock.now_utc() + timedelta(minutes=5), 1, "rpm", 1.0))
    assert await stores.historian.count() == 121
    with pytest.raises(HistorianError, match="tipo"):
        manifest.file_for("outro")  # type: ignore[arg-type]


async def test_backup_apagar_restore_mesmas_contagens(tmp_path: Path, clock: FakeClock) -> None:
    s = Stores(make_paths(tmp_path), clock)
    await s.open()
    try:
        await seed(s)
        manifest = await backup_all(s.historian, s.core, s.paths, dest_dir=tmp_path / "bk")
        events_before = await s.core.list()
        stats_before = await s.historian.stats()
    finally:
        await s.close()

    for db in (s.paths.historian_db, s.paths.core_db):
        db.unlink()
        for suffix in ("-wal", "-shm"):
            side = Path(str(db) + suffix)
            if side.exists():
                side.unlink()
    assert not s.paths.historian_db.exists()
    assert not s.paths.core_db.exists()

    await restore_all(tmp_path / "bk", s.paths)
    assert sha256_file(s.paths.historian_db) == manifest.file_for("historian").sha256
    assert sha256_file(s.paths.core_db) == manifest.file_for("core").sha256

    s2 = Stores(s.paths, clock)
    await s2.open()
    try:
        stats_after = await s2.historian.stats()
        assert stats_after["rows"] == stats_before["rows"] == EXPECTED_HIST
        assert await s2.historian.count() == 120
        assert (await s2.core.stats())["rows"] == EXPECTED_CORE
        assert await s2.core.list() == events_before
        assert await s2.core.get_for_event(events_before[-1].id) is not None
        assert len(await s2.core.audit_list()) == 2
        assert len(await s2.historian.comm_log(None, None)) == 1
        latest = await s2.historian.latest(EQ)
        assert latest["mass_flow"].value == 10.0
        # continua gravando depois do restore (migracao idempotente, WAL recriado)
        await s2.historian.write(series_1hz(clock.now_utc() + timedelta(hours=1), 5, "rpm", 3.0))
        assert await s2.historian.count() == 125
    finally:
        await s2.close()


async def test_restore_recusa_checksum_divergente(tmp_path: Path, clock: FakeClock) -> None:
    s = Stores(make_paths(tmp_path), clock)
    await s.open()
    try:
        await seed(s)
        manifest = await backup_all(s.historian, s.core, s.paths, dest_dir=tmp_path / "bk")
    finally:
        await s.close()

    hist_file = tmp_path / "bk" / manifest.file_for("historian").file_name
    with hist_file.open("ab") as fh:
        fh.write(b"\x00" * 64)
    original_core = sha256_file(s.paths.core_db)

    with pytest.raises(HistorianError, match="checksum"):
        await restore_all(tmp_path / "bk", s.paths)
    # nenhum destino foi tocado
    assert sha256_file(s.paths.core_db) == original_core
    s2 = Stores(s.paths, clock)
    await s2.open()
    try:
        assert await s2.historian.count() == 120
    finally:
        await s2.close()


async def test_restore_sem_manifesto(tmp_path: Path) -> None:
    paths = make_paths(tmp_path)
    with pytest.raises(HistorianError, match="manifesto"):
        await restore_all(tmp_path / "vazio", paths)


async def test_backup_individual_do_historian_e_valido(stores: Stores, clock: FakeClock) -> None:
    await stores.historian.write(series_1hz(clock.now_utc(), 30, "mass_flow", 1.0))
    out = await stores.historian.backup(stores.paths.backups_dir / "solo")
    assert out.name == "forja_historian_20260101T120000Z.db"
    check_integrity(out)
    conn = connect_immutable(out)
    try:
        assert conn.execute("SELECT COUNT(*) FROM samples").fetchone() == (30,)
    finally:
        conn.close()
    # segundo backup no mesmo instante do relogio nao sobrescreve
    again = await stores.historian.backup(stores.paths.backups_dir / "solo")
    assert again.name == "forja_historian_20260101T120000Z_1.db"
    core_out = await stores.core.backup(stores.paths.backups_dir / "solo")
    assert core_out.name == "forja_core_20260101T120000Z.db"
    check_integrity(core_out)
