"""SampleBuffer: janela deslizante por tag, sem interpolacao."""

from __future__ import annotations

from datetime import timedelta
from itertools import pairwise

import pytest

from forja.domain import Quality
from forja.events.prewindow import SampleBuffer
from tests.fixtures.synthetic_batches import at, comm_error_batch, make_batch, normal_values

ALLOWED = frozenset({Quality.GOOD, Quality.SIMULATED, Quality.UNCERTAIN})


def filled(seconds: int, buffer_s: int = 180) -> SampleBuffer:
    buf = SampleBuffer(buffer_s)
    for t in range(seconds + 1):
        buf.add(make_batch(at(t), normal_values(t)))
    return buf


def test_rejects_non_positive_buffer() -> None:
    with pytest.raises(ValueError, match="buffer_s"):
        SampleBuffer(0)


def test_evicts_samples_older_than_buffer() -> None:
    buf = filled(300, buffer_s=60)
    assert buf.latest_ts == at(300)
    old = buf.between(at(0), at(239))
    assert old == ()
    kept = buf.tag_values("rpm", at(0), at(300), ALLOWED, include_end=True)
    assert kept[0].ts_utc >= at(240)
    assert kept[-1].ts_utc == at(300)


def test_pre_window_is_at_most_60s_and_before_start() -> None:
    buf = filled(200)
    start = at(150)
    pre = buf.pre_window(start, 60, tags=("rpm",))
    assert pre
    assert pre[0].ts_utc == at(90)
    assert pre[-1].ts_utc == at(149)
    assert all(s.ts_utc < start for s in pre)
    assert pre[-1].ts_utc - pre[0].ts_utc <= timedelta(seconds=60)
    # contiguo: um por segundo, sem buraco inventado
    deltas = {(b.ts_utc - a.ts_utc) for a, b in pairwise(pre)}
    assert deltas == {timedelta(seconds=1)}


def test_between_sorted_by_ts_then_tag() -> None:
    buf = filled(5)
    rows = buf.between(at(1), at(2), tags=("rpm", "belt_load"))
    assert [(s.ts_utc, s.tag) for s in rows] == [
        (at(1), "belt_load"),
        (at(1), "rpm"),
        (at(2), "belt_load"),
        (at(2), "rpm"),
    ]
    assert buf.between(at(1), at(2), tags=("rpm",), include_end=False)[-1].ts_utc == at(1)


def test_tag_values_filters_quality_and_none() -> None:
    buf = SampleBuffer(180)
    buf.add(make_batch(at(0), {"rpm": 62.0}))
    buf.add(make_batch(at(1), {"rpm": 61.0}, quality=Quality.BAD))
    buf.add(comm_error_batch(at(2), tags=("rpm",)))
    buf.add(make_batch(at(3), {"rpm": 60.0}, quality=Quality.GOOD))
    usable = buf.tag_values("rpm", at(0), at(3), ALLOWED, include_end=True)
    assert [s.value for s in usable] == [62.0, 60.0]
    # mas o buffer guarda tudo, inclusive o COMM_ERROR (value None), para contagem de GAP
    assert len(buf.between(at(0), at(3), tags=("rpm",))) == 4


def test_previous_skips_unusable() -> None:
    buf = SampleBuffer(180)
    buf.add(make_batch(at(0), {"machine_state": 1}))
    buf.add(make_batch(at(1), {"machine_state": 1}, quality=Quality.STALE))
    buf.add(make_batch(at(2), {"machine_state": 0}))
    prev = buf.previous("machine_state", at(2), ALLOWED)
    assert prev is not None
    assert prev.ts_utc == at(0)
    assert buf.previous("rpm", at(2), ALLOWED) is None


def test_out_of_order_insert_keeps_sorted() -> None:
    buf = SampleBuffer(180)
    buf.add(make_batch(at(5), {"rpm": 5.0}))
    buf.add(make_batch(at(3), {"rpm": 3.0}))
    buf.add(make_batch(at(4), {"rpm": 4.0}))
    rows = buf.between(at(0), at(10), tags=("rpm",))
    assert [s.value for s in rows] == [3.0, 4.0, 5.0]
    assert buf.latest_ts == at(5)
    assert buf.tags == ("rpm",)
