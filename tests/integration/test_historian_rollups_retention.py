"""Historian: rollups 1m/1h e retencao por FakeClock."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import pytest

from forja.config.models import HistorianConfig
from forja.domain import CommLogEntry, Quality
from forja.historian import SqliteHistorian
from forja.historian.queries import to_ms
from forja.infra.clock import FakeClock
from tests.integration._historian_helpers import EQ, fetch_all, sample, series_1hz, table_count

pytestmark = pytest.mark.integration

TAG = "mass_flow"
SQL_AGG_1M = (
    "SELECT bucket_start_ms, n, n_good, n_comm_error, n_bad, min, max, avg, first, last, "
    "worst_quality FROM samples_agg_1m"
)
SQL_AGG_1H = (
    "SELECT bucket_start_ms, n, n_good, n_comm_error, n_bad, min, max, avg, first, last, "
    "worst_quality FROM samples_agg_1h ORDER BY 1"
)


def config(**overrides: object) -> HistorianConfig:
    base: dict[str, object] = {
        "store_on_change": False,
        "raw_retention_days": 30,
        "raw_simulated_retention_days": 1,
        "rollup_1m_retention_days": 180,
    }
    base.update(overrides)
    return HistorianConfig.model_validate(base)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
async def historian(tmp_path: Path, clock: FakeClock) -> AsyncIterator[SqliteHistorian]:
    h = SqliteHistorian(tmp_path / "forja_historian.db", config(), clock)
    await h.open()
    try:
        yield h
    finally:
        await h.close()


async def open_with(tmp_path: Path, clock: FakeClock, cfg: HistorianConfig) -> SqliteHistorian:
    h = SqliteHistorian(tmp_path / "h.db", cfg, clock)
    await h.open()
    return h


# ----------------------------------------------------------------------------- rollups


async def test_rollup_1m_calcula_n_avg_min_max_first_last_e_pior_qualidade(
    historian: SqliteHistorian, clock: FakeClock
) -> None:
    t0 = clock.now_utc()  # 12:00:00
    await historian.write(series_1hz(t0, 60, TAG, lambda i: float(i)))
    await historian.write(
        [sample(t0 + timedelta(seconds=30.5), TAG, None, Quality.COMM_ERROR, reason_pt="timeout")]
    )
    clock.advance(60)  # 12:01:00 -> minuto 12:00 fechado

    result = await historian.run_rollups()
    assert result["agg_1m"] == 1
    assert result["agg_1h"] == 0
    assert result["watermark_1m_ms"] == to_ms(t0 + timedelta(minutes=1))
    assert result["watermark_1h_ms"] == -1

    rows = fetch_all(historian.db_path, SQL_AGG_1M)
    assert rows == [(to_ms(t0), 61, 60, 1, 0, 0.0, 59.0, 29.5, 0.0, 59.0, 5)]


async def test_rollup_so_fecha_minutos_completos_e_recalcula_atrasados(
    historian: SqliteHistorian, clock: FakeClock
) -> None:
    t0 = clock.now_utc()
    await historian.write(series_1hz(t0, 60, TAG, 10.0))
    await historian.write(series_1hz(t0 + timedelta(minutes=1), 30, TAG, 20.0))
    clock.advance(90)  # 12:01:30 -> so 12:00 fechou
    await historian.run_rollups()
    assert [r[0] for r in fetch_all(historian.db_path, "SELECT n FROM samples_agg_1m")] == [60]

    # amostra atrasada caindo num minuto ja consolidado
    await historian.write([sample(t0 + timedelta(seconds=59.5), TAG, 1000.0)])
    clock.advance(30)  # 12:02:00 -> 12:01 fecha; os ultimos 5 minutos sao recalculados
    await historian.run_rollups()
    rows = fetch_all(
        historian.db_path, "SELECT bucket_start_ms, n, max FROM samples_agg_1m ORDER BY 1"
    )
    assert rows == [(to_ms(t0), 61, 1000.0), (to_ms(t0 + timedelta(minutes=1)), 30, 20.0)]


async def test_rollup_1h_a_partir_de_1m_com_media_ponderada(
    historian: SqliteHistorian, clock: FakeClock
) -> None:
    t0 = clock.now_utc()  # 12:00:00
    await historian.write(series_1hz(t0, 60, TAG, 10.0))
    await historian.write(series_1hz(t0 + timedelta(minutes=30), 30, TAG, 20.0))
    await historian.write(series_1hz(t0 + timedelta(hours=1), 10, TAG, 5.0))
    clock.advance(2 * 3600)  # 14:00:00 -> horas 12 e 13 fechadas

    result = await historian.run_rollups()
    assert table_count(historian.db_path, "samples_agg_1m") == 3
    assert result["agg_1h"] == 2
    assert result["watermark_1h_ms"] == to_ms(t0 + timedelta(hours=2))

    rows = fetch_all(historian.db_path, SQL_AGG_1H)
    assert len(rows) == 2
    h12, h13 = rows
    assert h12[0] == to_ms(t0)
    assert h12[1:5] == (90, 90, 0, 0)
    assert h12[5] == 10.0
    assert h12[6] == 20.0
    assert h12[7] == pytest.approx((10.0 * 60 + 20.0 * 30) / 90)
    assert h12[8] == 10.0  # first
    assert h12[9] == 20.0  # last
    assert h12[10] == 0
    assert h13[0] == to_ms(t0 + timedelta(hours=1))
    assert h13[1] == 10
    assert h13[7] == 5.0


async def test_rollup_sem_dados_nao_cria_marca_dagua(historian: SqliteHistorian) -> None:
    assert await historian.run_rollups() == {
        "agg_1m": 0,
        "agg_1h": 0,
        "watermark_1m_ms": -1,
        "watermark_1h_ms": -1,
    }
    st = await historian.stats()
    assert st["watermark_1m_utc"] is None


# ----------------------------------------------------------------------------- retencao


async def test_retention_apaga_bruto_antigo_e_preserva_agregados(
    historian: SqliteHistorian, clock: FakeClock
) -> None:
    now = clock.now_utc()
    old = now - timedelta(days=40)
    recent = now - timedelta(days=10)
    await historian.write(series_1hz(old, 60, TAG, 10.0))
    await historian.write(series_1hz(recent, 60, TAG, 20.0))
    await historian.log_comm(
        CommLogEntry(ts_utc=old, equipment_id=EQ, level="INFO", kind="CONNECTED", message_pt="ok")
    )
    await historian.log_comm(
        CommLogEntry(
            ts_utc=recent, equipment_id=EQ, level="INFO", kind="CONNECTED", message_pt="ok"
        )
    )
    await historian.run_rollups()
    assert table_count(historian.db_path, "samples_agg_1m") == 2
    assert table_count(historian.db_path, "samples_agg_1h") == 2
    assert await historian.count() == 120

    deleted = await historian.run_retention()
    assert deleted["samples"] == 60
    assert deleted["samples_simulated"] == 0
    assert deleted["samples_agg_1m"] == 0
    assert deleted["samples_agg_1h"] == 0
    assert deleted["comm_log"] == 1
    assert await historian.count() == 60
    remaining = [r[0] for r in fetch_all(historian.db_path, "SELECT ts_utc_ms FROM samples")]
    assert min(remaining) >= to_ms(now - timedelta(days=30))
    # agregados do periodo apagado continuam la (a historia nao some, so o bruto)
    assert table_count(historian.db_path, "samples_agg_1m") == 2
    assert table_count(historian.db_path, "samples_agg_1h") == 2
    assert len(await historian.comm_log(None, None)) == 1


async def test_retention_simulated_tem_prazo_curto(
    historian: SqliteHistorian, clock: FakeClock
) -> None:
    two_days_ago = clock.now_utc() - timedelta(days=2)
    await historian.write(series_1hz(two_days_ago, 10, TAG, 1.0, quality=Quality.SIMULATED))
    await historian.write(series_1hz(two_days_ago, 10, "rpm", 1.0, quality=Quality.GOOD))
    await historian.run_rollups()

    deleted = await historian.run_retention()
    assert deleted["samples_simulated"] == 10
    assert deleted["samples"] == 0
    rows = fetch_all(historian.db_path, "SELECT DISTINCT tag, quality FROM samples")
    assert rows == [("rpm", 0)]


async def test_retention_nunca_apaga_bruto_acima_da_marca_dagua(
    historian: SqliteHistorian, clock: FakeClock
) -> None:
    t0 = clock.now_utc()
    await historian.write(series_1hz(t0 - timedelta(days=40), 60, TAG, 10.0))
    # sem rollup nao ha marca d'agua: nada e apagado, por mais velho que seja
    deleted = await historian.run_retention()
    assert deleted["samples"] == 0
    assert await historian.count() == 60

    # rollup em t0: o minuto de t0 ainda esta aberto -> marca d'agua = t0
    await historian.write(series_1hz(t0, 10, TAG, 20.0))
    result = await historian.run_rollups()
    assert result["watermark_1m_ms"] == to_ms(t0)

    clock.advance(40 * 86_400)  # 40 dias depois, sem novo rollup
    deleted = await historian.run_retention()
    assert deleted["samples"] == 60  # o que estava abaixo da marca d'agua e velho
    assert await historian.count() == 10  # bruto >= marca d'agua sobrevive mesmo com 40 dias


async def test_retention_agg_1m_respeita_prazo_e_marca_dagua_1h(
    tmp_path: Path, clock: FakeClock
) -> None:
    h = await open_with(tmp_path, clock, config(rollup_1m_retention_days=1))
    try:
        now = clock.now_utc()
        await h.write(series_1hz(now - timedelta(days=3), 60, TAG, 10.0))
        await h.write(series_1hz(now - timedelta(hours=2), 60, TAG, 20.0))
        await h.run_rollups()
        assert table_count(h.db_path, "samples_agg_1m") == 2
        assert table_count(h.db_path, "samples_agg_1h") == 2

        deleted = await h.run_retention()
        assert deleted["samples_agg_1m"] == 1
        assert deleted["samples_agg_1h"] == 0  # rollup_1h_retention_days=None guarda para sempre
        assert deleted["samples"] == 0
        left = fetch_all(h.db_path, "SELECT bucket_start_ms FROM samples_agg_1m")
        assert left == [(to_ms(now - timedelta(hours=2)),)]
        assert table_count(h.db_path, "samples_agg_1h") == 2
    finally:
        await h.close()


async def test_retention_agg_1h_opcional(tmp_path: Path, clock: FakeClock) -> None:
    h = await open_with(
        tmp_path, clock, config(rollup_1m_retention_days=1, rollup_1h_retention_days=1)
    )
    try:
        now = clock.now_utc()
        await h.write(series_1hz(now - timedelta(days=3), 60, TAG, 10.0))
        await h.write(series_1hz(now - timedelta(hours=2), 60, TAG, 20.0))
        await h.run_rollups()
        deleted = await h.run_retention()
        assert deleted["samples_agg_1h"] == 1
        assert table_count(h.db_path, "samples_agg_1h") == 1
    finally:
        await h.close()
