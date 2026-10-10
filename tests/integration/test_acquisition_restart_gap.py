"""Reinício da coleta: o trecho em que a Forja não estava lendo vira buraco, nunca valor seguro.

Com store-on-change o gráfico segura o último valor até a próxima linha gravada. Se o Edge parou
(atualização, queda de energia), segurar o valor seria inventar leitura. Na partida, a coleta
grava uma marca sem valor logo depois da última leitura observada de cada variável.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from forja.acquisition.manager import EquipmentManager
from forja.domain import Quality, Sample
from forja.infra import AsyncBus, FakeClock
from tests.fixtures.acquisition_fakes import (
    TAGS,
    DriverLog,
    FakeRegistry,
    InMemoryHistorian,
    fake_pipeline,
    make_paths,
    make_profile,
    make_store,
    ok_factory,
    run_for,
)

pytestmark = pytest.mark.integration

EQ = "EQ_REINICIO"


def _old(clock: FakeClock, tag: str, age_s: float, value: float | None = 10.0) -> Sample:
    return Sample(
        ts_utc=clock.now_utc() - timedelta(seconds=age_s),
        equipment_id=EQ,
        tag=tag,
        value=value,
        quality=Quality.SIMULATED if value is not None else Quality.COMM_ERROR,
        source="teste",
    )


async def _start(
    tmp_path: Path, historian: InMemoryHistorian, clock: FakeClock
) -> EquipmentManager:
    registry = FakeRegistry()
    registry.add(EQ, ok_factory(DriverLog()))
    manager = EquipmentManager(
        make_store(make_paths(tmp_path), [make_profile(EQ)]),
        registry,
        historian,
        AsyncBus(),
        clock,
        pipeline=fake_pipeline(),
    )
    await manager.start_all()
    return manager


async def test_partida_depois_de_parada_grava_buraco_logo_apos_a_ultima_leitura(
    tmp_path: Path,
) -> None:
    clock = FakeClock()
    historian = InMemoryHistorian()
    previous = [_old(clock, tag, age_s=90) for tag in TAGS]
    await historian.write(previous)
    manager = await _start(tmp_path, historian, clock)
    try:
        await run_for(clock, 2)
        for prev in previous:
            marks = [
                s
                for s in historian.rows_for(EQ, Quality.COMM_ERROR)
                if s.tag == prev.tag and s.ts_utc == prev.ts_utc + timedelta(milliseconds=1)
            ]
            assert len(marks) == 1, prev.tag
            assert marks[0].value is None
            assert marks[0].reason_pt is not None
            assert "não estava coletando" in marks[0].reason_pt
    finally:
        await manager.stop_all(timeout_s=1)


async def test_sem_parada_real_nao_grava_marca(tmp_path: Path) -> None:
    clock = FakeClock()
    historian = InMemoryHistorian()
    await historian.write([_old(clock, tag, age_s=0.5) for tag in TAGS])
    manager = await _start(tmp_path, historian, clock)
    try:
        await run_for(clock, 2)
        assert historian.rows_for(EQ, Quality.COMM_ERROR) == []
    finally:
        await manager.stop_all(timeout_s=1)


async def test_ultima_leitura_ja_sem_valor_nao_duplica_buraco(tmp_path: Path) -> None:
    clock = FakeClock()
    historian = InMemoryHistorian()
    await historian.write([_old(clock, tag, age_s=300, value=None) for tag in TAGS])
    before = len(historian.rows_for(EQ, Quality.COMM_ERROR))
    manager = await _start(tmp_path, historian, clock)
    try:
        await run_for(clock, 2)
        assert len(historian.rows_for(EQ, Quality.COMM_ERROR)) == before
    finally:
        await manager.stop_all(timeout_s=1)


async def test_historian_indisponivel_na_partida_nao_impede_a_coleta(tmp_path: Path) -> None:
    clock = FakeClock()
    historian = InMemoryHistorian()
    await historian.write([_old(clock, tag, age_s=90) for tag in TAGS])

    async def broken_latest(*_args: object, **_kwargs: object) -> dict[str, Sample]:
        raise RuntimeError("banco indisponível (fake)")

    historian.latest = broken_latest  # type: ignore[method-assign]
    manager = await _start(tmp_path, historian, clock)
    try:
        await run_for(clock, 3)
        assert manager.status(EQ).consecutive_errors == 0
        assert await historian.count(EQ) > len(TAGS)
    finally:
        await manager.stop_all(timeout_s=1)
