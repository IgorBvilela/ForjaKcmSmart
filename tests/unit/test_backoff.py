"""Backoff exponencial: cresce, respeita o teto, jitter dentro da faixa, reset, determinismo."""

from __future__ import annotations

import random

import pytest

from forja.acquisition.backoff import Backoff

pytestmark = pytest.mark.unit


def test_grows_exponentially_without_jitter() -> None:
    b = Backoff(jitter=0.0)
    delays = [b.next_delay() for _ in range(8)]
    assert delays == [1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0]


def test_never_exceeds_cap_even_with_jitter() -> None:
    b = Backoff(seed=123)
    delays = [b.next_delay() for _ in range(40)]
    assert max(delays) <= 60.0
    assert all(d > 0 for d in delays)
    # depois de atingir o teto, fica no teto (com jitter só para baixo)
    assert all(48.0 <= d <= 60.0 for d in delays[10:])


@pytest.mark.parametrize("seed", [0, 1, 7, 42, 2026])
def test_jitter_stays_within_20_percent(seed: int) -> None:
    b = Backoff(seed=seed)
    for raw in (1.0, 2.0, 4.0, 8.0, 16.0, 32.0):
        delay = b.next_delay()
        assert raw * 0.8 - 1e-9 <= delay <= raw * 1.2 + 1e-9, (raw, delay)


def test_reset_returns_to_base() -> None:
    b = Backoff(jitter=0.0)
    for _ in range(5):
        b.next_delay()
    assert b.attempt == 5
    b.reset()
    assert b.attempt == 0
    assert b.next_delay() == 1.0


def test_deterministic_with_same_seed() -> None:
    a = Backoff(seed=99)
    b = Backoff(seed=99)
    assert [a.next_delay() for _ in range(10)] == [b.next_delay() for _ in range(10)]


def test_injected_rng_is_used() -> None:
    rng = random.Random(5)  # noqa: S311
    expected_rng = random.Random(5)  # noqa: S311
    b = Backoff(rng=rng)
    first = b.next_delay()
    spread = 1.0 * 0.2
    assert first == pytest.approx(1.0 + expected_rng.uniform(-spread, spread))


def test_peek_does_not_consume_attempt() -> None:
    b = Backoff(jitter=0.0)
    assert b.peek() == 1.0
    assert b.peek() == 1.0
    assert b.attempt == 0
    assert b.max_s == 60.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"base_s": 0.0},
        {"factor": 0.5},
        {"max_s": 0.5},
        {"jitter": 1.0},
        {"jitter": -0.1},
    ],
)
def test_rejects_invalid_parameters(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        Backoff(**kwargs)
