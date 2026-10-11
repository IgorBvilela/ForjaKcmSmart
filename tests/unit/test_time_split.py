"""Medida de tempo por dosador e período: dentro do normal, fora do normal e sem dados.

Classificação: FORJA_RULE (especificação da fase Q, §16). Sem dados nunca conta como normal nem
como fora do normal; aviso antecipado não conta como fora do normal; as três partes somam o
período inteiro.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from forja.domain import Quality, Sample, Severity
from forja.reports.time_split import alarm_intervals, event_intervals, split_time

pytestmark = pytest.mark.unit

T0 = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
HOUR = 3600.0


@dataclass(frozen=True)
class FakeEvent:
    start_utc: datetime
    end_utc: datetime | None
    origin: str = "RULE"
    severity: Severity = Severity.ATTENTION


def at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


def alarm(seconds: float, code: float | None, quality: Quality = Quality.SIMULATED) -> list[Sample]:
    """alarm_code e alarm_active coerentes no mesmo instante, como grava a aquisição."""
    active = None if code is None else (1.0 if code else 0.0)
    return [
        Sample(
            ts_utc=at(seconds),
            equipment_id="EQ",
            tag=tag,
            value=value,
            quality=quality,
            source="sim:teste",
        )
        for tag, value in (("alarm_code", code), ("alarm_active", active))
    ]


def test_three_parts_add_up_to_the_whole_period() -> None:
    split = split_time(HOUR, data=[(0, HOUR)], out=[(600, 1200)])
    assert (split.normal_s, split.out_s, split.no_data_s) == (3000, 600, 0)
    assert split.normal_s + split.out_s + split.no_data_s == HOUR


def test_no_data_never_counts_as_normal_nor_as_out_of_normal() -> None:
    split = split_time(HOUR, data=[(0, 1800)], out=[(1500, 2400)])
    assert split.no_data_s == 1800
    assert split.out_s == 300, "fora do normal só conta onde há dado"
    assert split.normal_s == 1500


def test_overlapping_intervals_are_merged_and_clipped_to_the_period() -> None:
    split = split_time(100, data=[(-50, 60), (50, 200)], out=[(10, 30), (20, 40), (90, 500)])
    assert (split.normal_s, split.out_s, split.no_data_s) == (60, 40, 0)


def test_no_reading_at_all_is_all_no_data() -> None:
    split = split_time(HOUR, data=[], out=[(0, HOUR)])
    assert (split.normal_s, split.out_s, split.no_data_s) == (0, 0, HOUR)


def test_open_rule_event_counts_until_the_end_and_early_warning_never_counts() -> None:
    events = [
        FakeEvent(at(2500), None),
        FakeEvent(at(-300), at(300)),
        FakeEvent(at(0), None, origin="EARLY_WARNING"),
        FakeEvent(at(1200), at(1500), severity=Severity.INFO),
        FakeEvent(at(2000), at(2100), severity=Severity.CRITICAL),
    ]
    assert event_intervals(events, T0, at(HOUR)) == [(0, 300), (2000, 2100), (2500, HOUR)]


def test_kcm_alarm_follows_the_live_rule_and_unusable_readings_stop_it() -> None:
    samples = (
        alarm(0, 0)
        + alarm(300, 56)
        + alarm(360, 56)
        + alarm(420, 0)
        + alarm(1000, 56)
        + alarm(1060, None, Quality.COMM_ERROR)
    )
    assert alarm_intervals(samples, T0, at(HOUR), hold_s=180) == [(300, 420), (1000, 1060)]


def test_kcm_alarm_reading_is_held_only_up_to_the_gap_limit() -> None:
    samples = alarm(0, 56)
    assert alarm_intervals(samples, T0, at(HOUR), hold_s=180) == [(0, 180)]


def test_fractions_and_labels_come_with_the_split() -> None:
    body = split_time(HOUR, data=[(0, 2700)], out=[(0, 900)]).as_dict()
    assert body["normal_pct"] == 50.0
    assert body["out_pct"] == 25.0
    assert body["no_data_pct"] == 25.0
    assert body["evidence_level"] == "FORJA_RULE"
