"""Historian: leitura das amostras brutas de um período (exportação e análise de janela)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import pytest

from forja.config.models import HistorianConfig
from forja.domain import HistorianError, Quality
from forja.historian import SqliteHistorian
from forja.infra.clock import FakeClock
from tests.integration._historian_helpers import EQ, sample

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


async def test_samples_devolve_linhas_brutas_em_ordem_com_qualidade(
    historian: SqliteHistorian, clock: FakeClock
) -> None:
    t0 = clock.now_utc()
    await historian.write(
        [
            sample(t0, "mass_flow", 100.0, Quality.GOOD),
            sample(t0 + timedelta(seconds=1), "mass_flow", None, Quality.COMM_ERROR),
            sample(
                t0 + timedelta(seconds=2), "mass_flow", 98.0, Quality.UNCERTAIN, raw=b"\x00\x01"
            ),
            sample(t0 + timedelta(seconds=1), "rpm", 61.0, Quality.GOOD),
        ]
    )
    rows = await historian.samples(EQ, ["mass_flow", "rpm"], t0, t0 + timedelta(seconds=5))
    assert [(s.tag, s.value, s.quality) for s in rows] == [
        ("mass_flow", 100.0, Quality.GOOD),
        ("mass_flow", None, Quality.COMM_ERROR),
        ("rpm", 61.0, Quality.GOOD),
        ("mass_flow", 98.0, Quality.UNCERTAIN),
    ]
    assert rows[3].raw == b"\x00\x01"
    assert all(r.ts_utc.tzinfo is not None for r in rows)


async def test_samples_respeita_janela_e_filtro_de_tag(
    historian: SqliteHistorian, clock: FakeClock
) -> None:
    t0 = clock.now_utc()
    await historian.write(
        [sample(t0 + timedelta(seconds=i), "mass_flow", float(i)) for i in range(10)]
        + [sample(t0, "belt_load", 2.0)]
    )
    rows = await historian.samples(
        EQ, ["mass_flow"], t0 + timedelta(seconds=3), t0 + timedelta(seconds=5)
    )
    assert [r.value for r in rows] == [3.0, 4.0, 5.0]
    assert {r.tag for r in rows} == {"mass_flow"}


async def test_samples_limita_quantidade_e_informa_pelo_tamanho(
    historian: SqliteHistorian, clock: FakeClock
) -> None:
    t0 = clock.now_utc()
    await historian.write(
        [sample(t0 + timedelta(seconds=i), "mass_flow", float(i)) for i in range(20)]
    )
    rows = await historian.samples(EQ, ["mass_flow"], t0, t0 + timedelta(seconds=30), limit=5)
    assert len(rows) == 5
    assert [r.value for r in rows] == [0.0, 1.0, 2.0, 3.0, 4.0]


async def test_export_rows_sao_leves_e_iguais_as_amostras(
    historian: SqliteHistorian, clock: FakeClock
) -> None:
    t0 = clock.now_utc()
    await historian.write(
        [
            sample(t0, "mass_flow", 100.0, Quality.GOOD),
            sample(t0 + timedelta(seconds=1), "mass_flow", None, Quality.COMM_ERROR, reason_pt="x"),
        ]
    )
    rows = await historian.export_rows(EQ, ["mass_flow"], t0, t0 + timedelta(seconds=2), 10)
    assert [(r.tag, r.value, r.quality, r.reason_pt) for r in rows] == [
        ("mass_flow", 100.0, Quality.GOOD, None),
        ("mass_flow", None, Quality.COMM_ERROR, "x"),
    ]
    assert rows[0].ts_utc == t0


async def test_samples_sem_tags_devolve_vazio_e_janela_invertida_e_erro(
    historian: SqliteHistorian, clock: FakeClock
) -> None:
    t0 = clock.now_utc()
    assert await historian.samples(EQ, [], t0, t0 + timedelta(seconds=1)) == []
    with pytest.raises(HistorianError):
        await historian.samples(EQ, ["mass_flow"], t0, t0 - timedelta(seconds=1))
