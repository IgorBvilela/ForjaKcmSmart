"""Historian: escrita, latest, STALE/COMM_ERROR, store-on-change, comm_log, stats."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from forja.config.models import HistorianConfig
from forja.domain import CommLogEntry, HistorianError, Quality, Sample
from forja.historian import SqliteHistorian
from forja.infra.clock import FakeClock
from tests.integration._historian_helpers import EQ, SRC, fetch_all, sample, series_1hz

pytestmark = pytest.mark.integration


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
async def historian(tmp_path: Path, clock: FakeClock) -> AsyncIterator[SqliteHistorian]:
    h = SqliteHistorian(
        tmp_path / "forja_historian.db", HistorianConfig(store_on_change=False), clock
    )
    await h.open()
    try:
        yield h
    finally:
        await h.close()


async def test_open_cria_banco_wal_strict_e_registra_migracao(historian: SqliteHistorian) -> None:
    assert historian.is_open
    rows = fetch_all(historian.db_path, "PRAGMA journal_mode")
    assert rows == [("wal",)]
    tables = {
        r[0]
        for r in fetch_all(historian.db_path, "SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {
        "samples",
        "samples_latest",
        "samples_agg_1m",
        "samples_agg_1h",
        "comm_log",
        "rollup_state",
        "schema_migrations",
    } <= tables
    (ddl,) = fetch_all(historian.db_path, "SELECT sql FROM sqlite_master WHERE name = 'samples'")[0]
    assert "STRICT" in str(ddl)
    assert "WITHOUT ROWID" in str(ddl)
    assert "PRIMARY KEY (equipment_id, tag, ts_utc_ms)" in str(ddl)
    assert fetch_all(historian.db_path, "SELECT version, name FROM schema_migrations") == [
        (1, "0001_historian")
    ]


async def test_write_e_latest(historian: SqliteHistorian, clock: FakeClock) -> None:
    s1 = sample(clock, "mass_flow", 120.5, Quality.SIMULATED)
    s2 = sample(clock, "belt_load", 1.25, Quality.GOOD, raw=b"\x01\x02")
    await historian.write([s1, s2])

    latest = await historian.latest(EQ)
    assert set(latest) == {"mass_flow", "belt_load"}
    assert latest["mass_flow"].value == 120.5
    assert latest["mass_flow"].quality is Quality.SIMULATED
    assert latest["mass_flow"].ts_utc == clock.now_utc()
    assert latest["mass_flow"].source == SRC
    assert latest["belt_load"].raw == b"\x01\x02"
    assert latest["belt_load"].quality is Quality.GOOD

    assert await historian.count() == 2
    assert await historian.count(EQ) == 2
    assert await historian.count("OUTRO") == 0
    # tempo no banco: INTEGER epoch ms UTC
    (ts_ms,) = fetch_all(
        historian.db_path, "SELECT ts_utc_ms FROM samples WHERE tag = 'mass_flow'"
    )[0]
    assert ts_ms == int(clock.now_utc().timestamp() * 1000)


async def test_latest_filtra_tags_e_devolve_o_mais_novo(
    historian: SqliteHistorian, clock: FakeClock
) -> None:
    await historian.write([sample(clock, value=1.0)])
    clock.advance(5)
    await historian.write([sample(clock, value=2.0), sample(clock, "rpm", 30.0)])

    latest = await historian.latest(EQ, tags=["mass_flow"])
    assert list(latest) == ["mass_flow"]
    assert latest["mass_flow"].value == 2.0
    assert latest["mass_flow"].ts_utc == clock.now_utc()
    assert await historian.latest(EQ, tags=[]) == {}
    assert await historian.latest("NAO_EXISTE") == {}


async def test_comm_error_grava_value_null(historian: SqliteHistorian, clock: FakeClock) -> None:
    await historian.write(
        [sample(clock, value=None, quality=Quality.COMM_ERROR, reason_pt="timeout")]
    )
    # mesmo que venha numero por engano, COMM_ERROR vira NULL
    await historian.write([sample(clock, "rpm", 42.0, Quality.COMM_ERROR)])

    rows = fetch_all(
        historian.db_path, "SELECT tag, value, quality, reason_pt FROM samples ORDER BY tag"
    )
    assert rows == [("mass_flow", None, 5, "timeout"), ("rpm", None, 5, None)]
    latest = await historian.latest(EQ)
    assert latest["rpm"].value is None
    assert latest["rpm"].quality is Quality.COMM_ERROR
    assert latest["mass_flow"].reason_pt == "timeout"


async def test_stale_nunca_e_gravado(historian: SqliteHistorian, clock: FakeClock) -> None:
    await historian.write([sample(clock, value=10.0, quality=Quality.SIMULATED)])
    t_first = clock.now_utc()
    clock.advance(30)
    await historian.write([sample(clock, value=10.0, quality=Quality.STALE)])

    assert await historian.count() == 1
    stale_rows = fetch_all(historian.db_path, "SELECT COUNT(*) FROM samples WHERE quality = 3")
    assert stale_rows == [(0,)]
    latest = await historian.latest(EQ)
    assert latest["mass_flow"].quality is Quality.SIMULATED
    assert latest["mass_flow"].ts_utc == t_first  # STALE nao atualiza nem o latest


async def test_store_on_change_reduz_linhas_e_forca_amostra_a_cada_60s(
    tmp_path: Path, clock: FakeClock
) -> None:
    cfg = HistorianConfig(store_on_change=True, forced_sample_every_s=60)
    h = SqliteHistorian(tmp_path / "h.db", cfg, clock)
    await h.open()
    try:
        start = clock.now_utc()
        # 181 amostras constantes (t = 0..180 s): so a primeira e as forcadas viram linha
        await h.write(series_1hz(start, 181, "mass_flow", 100.0))
        assert await h.count() == 4
        stored = [r[0] for r in fetch_all(h.db_path, "SELECT ts_utc_ms FROM samples ORDER BY 1")]
        base = int(start.timestamp() * 1000)
        assert stored == [base, base + 60_000, base + 120_000, base + 180_000]

        # mudanca acima da banda morta (mass_flow: 0 decimais -> 0,5) grava
        await h.write([sample(start + timedelta(seconds=181), value=101.0)])
        assert await h.count() == 5
        # mudanca abaixo da banda morta nao grava
        await h.write([sample(start + timedelta(seconds=182), value=101.2)])
        assert await h.count() == 5
        # mudanca de qualidade grava
        await h.write(
            [sample(start + timedelta(seconds=183), value=101.2, quality=Quality.SIMULATED)]
        )
        assert await h.count() == 6
        # latest reflete a ultima leitura mesmo quando nao virou linha
        await h.write(
            [sample(start + timedelta(seconds=184), value=101.3, quality=Quality.SIMULATED)]
        )
        assert await h.count() == 6
        latest = await h.latest(EQ)
        assert latest["mass_flow"].value == 101.3
        assert latest["mass_flow"].ts_utc == start + timedelta(seconds=184)
    finally:
        await h.close()


async def test_sem_store_on_change_grava_tudo(historian: SqliteHistorian, clock: FakeClock) -> None:
    await historian.write(series_1hz(clock.now_utc(), 181, "mass_flow", 100.0))
    assert await historian.count() == 181


async def test_comm_log_com_filtros(historian: SqliteHistorian, clock: FakeClock) -> None:
    t0 = clock.now_utc()
    await historian.log_comm(
        CommLogEntry(
            ts_utc=t0,
            equipment_id=EQ,
            level="INFO",
            kind="CONNECTED",
            message_pt="Conectado",
            detail={"ip": "127.0.0.1", "tentativa": 1},
        )
    )
    clock.advance(10)
    await historian.log_comm(
        CommLogEntry(
            ts_utc=clock.now_utc(),
            equipment_id="EQ2",
            level="ERROR",
            kind="TIMEOUT",
            message_pt="Timeout",
        )
    )
    clock.advance(10)
    await historian.log_comm(
        CommLogEntry(
            ts_utc=clock.now_utc(),
            equipment_id=EQ,
            level="WARN",
            kind="RECONNECTING",
            message_pt="Reconectando",
        )
    )

    everything = await historian.comm_log(None, None)
    assert [e.kind for e in everything] == ["RECONNECTING", "TIMEOUT", "CONNECTED"]
    by_eq = await historian.comm_log(EQ, None)
    assert [e.kind for e in by_eq] == ["RECONNECTING", "CONNECTED"]
    assert by_eq[1].detail == {"ip": "127.0.0.1", "tentativa": 1}
    assert by_eq[1].ts_utc == t0
    since = await historian.comm_log(None, t0 + timedelta(seconds=5))
    assert [e.kind for e in since] == ["RECONNECTING", "TIMEOUT"]
    assert len(await historian.comm_log(None, None, limit=1)) == 1


async def test_datetime_sem_fuso_e_recusado(historian: SqliteHistorian) -> None:
    naive = Sample(
        ts_utc=datetime(2026, 1, 1, 12, 0, 0),
        equipment_id=EQ,
        tag="mass_flow",
        value=1.0,
        quality=Quality.GOOD,
        source=SRC,
    )
    with pytest.raises(HistorianError, match="tzinfo"):
        await historian.write([naive])
    assert await historian.count() == 0


async def test_operacoes_fora_do_ciclo_de_vida_falham(tmp_path: Path, clock: FakeClock) -> None:
    h = SqliteHistorian(tmp_path / "h.db", HistorianConfig(), clock)
    assert not h.is_open
    with pytest.raises(HistorianError, match="não está aberto"):
        await h.write([sample(clock)])
    await h.open()
    with pytest.raises(HistorianError, match="já aberto"):
        await h.open()
    await h.close()
    await h.close()  # idempotente
    with pytest.raises(HistorianError, match="não está aberto"):
        await h.latest(EQ)


async def test_stats(historian: SqliteHistorian, clock: FakeClock) -> None:
    await historian.write(series_1hz(clock.now_utc(), 10, "mass_flow", 1.0))
    await historian.write([sample(clock.now_utc() + timedelta(seconds=9), "rpm", 2.0)])
    st = await historian.stats()
    assert st["rows"] == {
        "samples": 11,
        "samples_latest": 2,
        "samples_agg_1m": 0,
        "samples_agg_1h": 0,
        "comm_log": 0,
    }
    assert st["last_sample_utc"] == (clock.now_utc() + timedelta(seconds=9)).isoformat()
    assert st["watermark_1m_utc"] is None
    assert st["schema_version"] == 1
    assert st["size_bytes"] > 0
    assert st["store_on_change"] is False
    assert datetime.fromisoformat(st["last_sample_utc"]).tzinfo is not None
    assert datetime.fromisoformat(st["last_sample_utc"]).utcoffset() == UTC.utcoffset(None)
