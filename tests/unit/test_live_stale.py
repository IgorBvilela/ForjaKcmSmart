"""LiveState / StaleMonitor: STALE por relógio monotônico, sem alterar valor nem ts.

COMM_ERROR (a tentativa atual falhou) nunca se confunde com STALE (o último valor ficou velho).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from forja.acquisition.live import LiveState, StaleMonitor
from forja.domain import ConnectionState, Quality, Sample, SampleBatch
from forja.infra import FakeClock

pytestmark = pytest.mark.unit

EQ = "EQ_TESTE"
STALE_AFTER = 5.0


def _batch(clock: FakeClock, values: dict[str, float | None], quality: Quality) -> SampleBatch:
    ts = clock.now_utc()
    mono = clock.monotonic_ns()
    samples = tuple(
        Sample(
            ts_utc=ts,
            equipment_id=EQ,
            tag=tag,
            value=value,
            quality=quality,
            source="driver:simulator:fake@1",
            ts_mono_ns=mono,
            reason_pt=None if quality.is_usable_value else "sem leitura",
        )
        for tag, value in values.items()
    )
    return SampleBatch(equipment_id=EQ, ts_utc=ts, samples=samples, quality=quality)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(datetime(2026, 3, 1, 10, 0, tzinfo=UTC))


@pytest.fixture
def live(clock: FakeClock) -> LiveState:
    return LiveState(EQ, clock, STALE_AFTER)


def test_fresh_sample_is_exposed_as_is(clock: FakeClock, live: LiveState) -> None:
    live.update(_batch(clock, {"mass_flow": 1300.0}, Quality.SIMULATED))
    exposed = live.sample("mass_flow")
    assert exposed is not None
    sample, age = exposed
    assert sample.quality is Quality.SIMULATED
    assert sample.value == 1300.0
    assert age == 0.0
    assert live.is_stale is False
    assert live.stale_for_s is None


def test_after_stale_after_s_quality_is_stale_with_original_value_and_ts(
    clock: FakeClock, live: LiveState
) -> None:
    live.update(_batch(clock, {"mass_flow": 1300.0, "rpm": 62.0}, Quality.SIMULATED))
    original_ts = clock.now_utc()
    clock.advance(STALE_AFTER + 0.5)

    exposed = live.sample("mass_flow")
    assert exposed is not None
    sample, age = exposed
    assert sample.quality is Quality.STALE
    assert sample.value == 1300.0
    assert sample.ts_utc == original_ts
    assert age == pytest.approx(5.5)
    assert sample.reason_pt is not None
    assert "Valor antigo" in sample.reason_pt
    assert live.is_stale is True
    assert live.stale_for_s == pytest.approx(0.5)


def test_exactly_at_threshold_is_not_stale_yet(clock: FakeClock, live: LiveState) -> None:
    live.update(_batch(clock, {"rpm": 62.0}, Quality.SIMULATED))
    clock.advance(STALE_AFTER)
    exposed = live.sample("rpm")
    assert exposed is not None
    assert exposed[0].quality is Quality.SIMULATED
    assert live.is_stale is False


def test_comm_error_is_not_stale(clock: FakeClock, live: LiveState) -> None:
    """Leitura boa, depois a tentativa atual falha: o valor anterior ainda é fresco."""
    live.update(_batch(clock, {"mass_flow": 1300.0}, Quality.SIMULATED))
    clock.advance(1.0)
    live.update(_batch(clock, {"mass_flow": None}, Quality.COMM_ERROR))

    exposed = live.sample("mass_flow")
    assert exposed is not None
    sample, age = exposed
    assert sample.quality is Quality.SIMULATED, "COMM_ERROR agora não torna o valor anterior velho"
    assert sample.value == 1300.0
    assert age == pytest.approx(1.0)
    assert live.is_stale is False

    clock.advance(STALE_AFTER)
    exposed = live.sample("mass_flow")
    assert exposed is not None
    assert exposed[0].quality is Quality.STALE
    assert exposed[0].value == 1300.0


def test_comm_error_without_previous_value_is_exposed_as_comm_error(
    clock: FakeClock, live: LiveState
) -> None:
    live.update(_batch(clock, {"belt_load": None}, Quality.COMM_ERROR))
    clock.advance(STALE_AFTER * 3)
    exposed = live.sample("belt_load")
    assert exposed is not None
    sample, _ = exposed
    assert sample.quality is Quality.COMM_ERROR
    assert sample.value is None
    assert live.is_stale is False, "nunca houve valor bom: não existe 'valor velho'"


def test_snapshot_carries_connection_and_ages(clock: FakeClock, live: LiveState) -> None:
    live.update(_batch(clock, {"mass_flow": 1300.0, "rpm": 62.0}, Quality.SIMULATED))
    clock.advance(2.0)
    live.update(_batch(clock, {"mass_flow": None, "rpm": None}, Quality.COMM_ERROR))
    snap = live.snapshot(ConnectionState.ERROR)
    assert snap.connection is ConnectionState.ERROR
    assert set(snap.samples) == {"mass_flow", "rpm"}
    assert snap.samples["mass_flow"].quality is Quality.SIMULATED
    assert snap.ages_s["mass_flow"] == pytest.approx(2.0)
    assert snap.is_stale is False
    assert snap.last_ok_utc == datetime(2026, 3, 1, 10, 0, tzinfo=UTC)


def test_stale_input_is_ignored(clock: FakeClock, live: LiveState) -> None:
    live.update(_batch(clock, {"mass_flow": 999.0}, Quality.STALE))
    assert live.sample("mass_flow") is None
    assert live.tags == ()


def test_bad_is_exposed_as_bad(clock: FakeClock, live: LiveState) -> None:
    live.update(_batch(clock, {"mass_flow": 1300.0}, Quality.SIMULATED))
    clock.advance(1.0)
    live.update(_batch(clock, {"mass_flow": -5.0}, Quality.BAD))
    exposed = live.sample("mass_flow")
    assert exposed is not None
    assert exposed[0].quality is Quality.BAD
    assert exposed[0].value == -5.0


def test_clear_forgets_everything(clock: FakeClock, live: LiveState) -> None:
    live.update(_batch(clock, {"mass_flow": 1300.0}, Quality.SIMULATED))
    live.clear()
    assert live.tags == ()
    assert live.last_ok_utc is None
    assert live.is_stale is False


def test_stale_monitor_edges(clock: FakeClock) -> None:
    monitor = StaleMonitor(clock, STALE_AFTER)
    assert monitor.is_stale(None) is False
    assert monitor.stale_for_s(None) is None
    start = clock.monotonic_ns()
    clock.advance(7.0)
    assert monitor.age_s(start) == pytest.approx(7.0)
    assert monitor.is_stale(start) is True
    assert monitor.stale_for_s(start) == pytest.approx(2.0)
    with pytest.raises(ValueError):
        StaleMonitor(clock, 0.0)
