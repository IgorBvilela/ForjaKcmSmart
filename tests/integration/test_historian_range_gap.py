"""Historian: range() escolhe resolucao, devolve GAP e nunca interpola."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import pytest

from forja.config.models import HistorianConfig
from forja.domain import HistorianError, Quality
from forja.historian import SqliteHistorian
from forja.infra.clock import FakeClock
from tests.integration._historian_helpers import EQ, sample, series_1hz, table_count

pytestmark = pytest.mark.integration

TAG = "mass_flow"


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


async def test_range_bruto_com_buraco_devolve_gap_sem_interpolar(
    historian: SqliteHistorian, clock: FakeClock
) -> None:
    t0 = clock.now_utc()
    resume = t0 + timedelta(minutes=10)
    await historian.write(series_1hz(t0, 60, TAG, lambda i: 100.0 + i))
    await historian.write(series_1hz(resume, 60, TAG, 200.0))

    s = await historian.range(EQ, TAG, t0, resume + timedelta(seconds=59))
    assert s.resolution == "raw"
    assert s.bucket_s == 0
    assert not s.downsampled
    gaps = [p for p in s.points if p.n == 0]
    assert len(gaps) == 1
    assert s.gap_count == 1
    gap = gaps[0]
    assert gap.value is None
    assert gap.quality is Quality.COMM_ERROR
    assert t0 + timedelta(seconds=59) < gap.ts_utc < resume
    # nenhum valor inventado dentro do buraco
    inside = [p for p in s.points if t0 + timedelta(seconds=59) < p.ts_utc < resume]
    assert inside == [gap]
    assert len(s.points) == 121
    stamps = [p.ts_utc for p in s.points]
    assert stamps == sorted(stamps)
    assert s.points[0].value == 100.0
    assert s.points[-1].value == 200.0
    assert s.stale_count == 0


async def test_range_sem_dado_devolve_so_gap(historian: SqliteHistorian, clock: FakeClock) -> None:
    t0 = clock.now_utc()
    s = await historian.range(EQ, TAG, t0, t0 + timedelta(minutes=10))
    assert s.resolution == "raw"
    assert len(s.points) == 1
    assert s.points[0].value is None
    assert s.points[0].n == 0
    assert s.gap_count == 1


async def test_range_escolhe_raw_para_janela_curta(
    historian: SqliteHistorian, clock: FakeClock
) -> None:
    t0 = clock.now_utc()
    await historian.write(series_1hz(t0, 300, TAG, lambda i: float(i)))
    s = await historian.range(EQ, TAG, t0, t0 + timedelta(seconds=299))
    assert s.resolution == "raw"
    assert len(s.points) == 300
    assert s.gap_count == 0
    assert all(p.n == 1 for p in s.points)
    assert [p.value for p in s.points[:3]] == [0.0, 1.0, 2.0]


async def test_range_escolhe_1m_para_24h(historian: SqliteHistorian, clock: FakeClock) -> None:
    now = clock.now_utc()
    start = now - timedelta(hours=24)
    await historian.write(series_1hz(start, 60, TAG, 10.0))
    await historian.write(series_1hz(now - timedelta(seconds=60), 60, TAG, 20.0))

    s = await historian.range(EQ, TAG, start, now)
    assert s.resolution == "1m"
    assert s.bucket_s == 60
    assert s.downsampled
    assert 1440 <= len(s.points) <= 1441
    assert all(p.ts_utc.second == 0 and p.ts_utc.microsecond == 0 for p in s.points)
    filled = [p for p in s.points if p.value is not None]
    assert len(filled) == 2
    assert filled[0].ts_utc == start
    assert filled[0].value == 10.0
    assert filled[0].n == 60
    assert filled[0].min == 10.0
    assert filled[0].max == 10.0
    assert filled[1].value == 20.0
    assert s.gap_count == len(s.points) - 2
    # buckets vazios: GAP explicito, nunca valor interpolado
    empty = [p for p in s.points if p.value is None]
    assert all(p.n == 0 and p.quality is Quality.COMM_ERROR for p in empty)


async def test_range_escolhe_1h_para_30_dias(historian: SqliteHistorian, clock: FakeClock) -> None:
    now = clock.now_utc()
    start = now - timedelta(days=30)
    await historian.write(series_1hz(start, 60, TAG, 10.0))
    s = await historian.range(EQ, TAG, start, now)
    assert s.resolution == "1h"
    assert s.bucket_s == 3600
    assert 720 <= len(s.points) <= 721
    filled = [p for p in s.points if p.value is not None]
    assert len(filled) == 1
    assert filled[0].n == 60
    assert filled[0].value == 10.0
    assert filled[0].ts_utc == start


async def test_range_1m_combina_consolidado_e_cauda_ao_vivo(
    historian: SqliteHistorian, clock: FakeClock
) -> None:
    t0 = clock.now_utc()  # 12:00:00
    await historian.write(series_1hz(t0, 60, TAG, 10.0))
    await historian.write(series_1hz(t0 + timedelta(minutes=1), 60, TAG, 20.0))
    await historian.write(series_1hz(t0 + timedelta(minutes=2), 60, TAG, 30.0))
    clock.advance(120)  # 12:02:00 -> minutos 12:00 e 12:01 fechados
    await historian.run_rollups()
    assert table_count(historian.db_path, "samples_agg_1m") == 2  # 12:02 ainda nao consolidado
    clock.advance(60)

    s = await historian.range(EQ, TAG, t0 - timedelta(hours=23), t0 + timedelta(minutes=3))
    assert s.resolution == "1m"
    values = {p.ts_utc: (p.value, p.n) for p in s.points if p.value is not None}
    assert values == {
        t0: (10.0, 60),
        t0 + timedelta(minutes=1): (20.0, 60),
        t0 + timedelta(minutes=2): (30.0, 60),  # veio do bruto, nao do agregado
    }


async def test_bucket_quality_e_a_pior_e_valor_so_dos_utilizaveis(
    historian: SqliteHistorian, clock: FakeClock
) -> None:
    t0 = clock.now_utc()
    await historian.write(series_1hz(t0, 30, TAG, 100.0))
    await historian.write(
        series_1hz(t0 + timedelta(seconds=30), 30, TAG, 999.0, quality=Quality.COMM_ERROR)
    )
    s = await historian.range(EQ, TAG, t0 - timedelta(hours=23), t0 + timedelta(seconds=60))
    assert s.resolution == "1m"
    point = next(p for p in s.points if p.ts_utc == t0)
    assert point.n == 60
    assert point.value == 100.0  # 999 de COMM_ERROR virou NULL e nao entra na media
    assert point.min == 100.0
    assert point.max == 100.0
    assert point.quality is Quality.COMM_ERROR  # pior qualidade do bucket


async def test_range_bruto_acima_do_orcamento_rebucketa_em_segundos(
    historian: SqliteHistorian, clock: FakeClock
) -> None:
    t0 = clock.now_utc()
    # 10 Hz por 100 s = 1000 linhas; janela de 100 s cabe em 200 pontos -> raw, mas estoura
    samples = [sample(t0 + timedelta(milliseconds=100 * i), TAG, float(i)) for i in range(1000)]
    await historian.write(samples)
    s = await historian.range(EQ, TAG, t0, t0 + timedelta(seconds=100), max_points=200)
    assert s.resolution == "1s"
    assert s.bucket_s == 1
    assert s.downsampled
    assert len(s.points) == 101
    first = s.points[0]
    assert first.n == 10
    assert first.value == pytest.approx(4.5)
    assert first.min == 0.0
    assert first.max == 9.0
    assert s.points[-1].n == 0  # bucket de 100 s esta vazio -> GAP
    assert s.gap_count == 1


async def test_range_1h_acima_do_orcamento_funde_buckets(
    historian: SqliteHistorian, clock: FakeClock
) -> None:
    # 30 dias = 721 horas; com 100 pontos nem 1h cabe -> funde 8 horas por bucket
    now = clock.now_utc()
    start = now - timedelta(days=30)
    await historian.write(series_1hz(start, 60, TAG, 10.0))
    s = await historian.range(EQ, TAG, start, now, max_points=100)
    assert s.bucket_s == 28_800  # ceil(721 / 100) = 8 horas
    assert s.resolution == "28800s"
    assert s.downsampled
    assert 90 <= len(s.points) <= 100
    filled = [p for p in s.points if p.value is not None]
    assert len(filled) == 1
    assert filled[0].n == 60
    assert filled[0].value == 10.0


async def test_range_respeita_max_points_da_config(tmp_path: Path, clock: FakeClock) -> None:
    cfg = HistorianConfig(store_on_change=False, max_points_per_query=50)
    h = SqliteHistorian(tmp_path / "h.db", cfg, clock)
    await h.open()
    try:
        now = clock.now_utc()
        start = now - timedelta(hours=24)
        await h.write(series_1hz(start, 60, TAG, 10.0))
        # sem o teto da config, 24 h em 5000 pontos seria "1m"; com teto 50 vira "1h"
        s = await h.range(EQ, TAG, start, now, max_points=5000)
        assert s.resolution == "1h"
        assert s.bucket_s == 3600
        assert len(s.points) <= 50
    finally:
        await h.close()


async def test_range_intervalo_invertido_e_recusado(
    historian: SqliteHistorian, clock: FakeClock
) -> None:
    now = clock.now_utc()
    with pytest.raises(HistorianError, match="intervalo"):
        await historian.range(EQ, TAG, now, now - timedelta(hours=1))
