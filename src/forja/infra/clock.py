"""Relogio injetavel. STALE, retencao, backoff e janela pre-evento usam ESTE relogio,
nunca time.time() direto. Assim o teste avanca 90 s em 0 ms e o relogio do Windows
pulando nao gera STALE falso (monotonico)."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta


class SystemClock:
    def now_utc(self) -> datetime:
        return datetime.now(UTC)

    def monotonic_ns(self) -> int:
        return time.monotonic_ns()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class FakeClock:
    """Relogio de teste. advance() move os dois relogios juntos; set_wall() move so o de parede
    (simula ajuste do relogio do Windows sem mexer no monotonico)."""

    def __init__(self, start: datetime | None = None) -> None:
        self._wall = start or datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        self._mono_ns = 1_000_000_000
        self._sleepers: list[tuple[float, asyncio.Future[None]]] = []

    def now_utc(self) -> datetime:
        return self._wall

    def monotonic_ns(self) -> int:
        return self._mono_ns

    def advance(self, seconds: float) -> None:
        self._wall = self._wall + timedelta(seconds=seconds)
        self._mono_ns += int(seconds * 1_000_000_000)
        self._wake_sleepers()

    def set_wall(self, when: datetime) -> None:
        self._wall = when

    async def sleep(self, seconds: float) -> None:
        if seconds <= 0:
            await asyncio.sleep(0)
            return
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[None] = loop.create_future()
        deadline = self._mono_ns / 1e9 + seconds
        self._sleepers.append((deadline, fut))
        await fut

    def _wake_sleepers(self) -> None:
        now = self._mono_ns / 1e9
        still: list[tuple[float, asyncio.Future[None]]] = []
        for deadline, fut in self._sleepers:
            if deadline <= now and not fut.done():
                fut.set_result(None)
            elif not fut.done():
                still.append((deadline, fut))
        self._sleepers = still

    @property
    def pending_sleepers(self) -> int:
        return len([f for _, f in self._sleepers if not f.done()])
