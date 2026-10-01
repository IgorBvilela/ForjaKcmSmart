"""Watchdog dos loops de aquisição.

Cada loop marca um tick a cada iteração (inclusive durante o sono de backoff, que é fatiado
em pedaços de poll_interval_s). Se um loop fica mais de 3 × poll_interval_s sem tick, o
watchdog chama o callback de restart: a task é cancelada e recriada; restart_count sobe.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from forja.domain import Clock

logger = logging.getLogger(__name__)

_NS = 1_000_000_000


@dataclass
class WatchedLoop:
    equipment_id: str
    poll_interval_s: float
    last_tick_mono_ns: Callable[[], int | None]
    restart: Callable[[], Awaitable[None]]
    registered_mono_ns: int


class Watchdog:
    def __init__(self, clock: Clock, *, check_interval_s: float = 1.0, factor: float = 3.0) -> None:
        if check_interval_s <= 0:
            raise ValueError("check_interval_s deve ser > 0")
        if factor <= 0:
            raise ValueError("factor deve ser > 0")
        self._clock = clock
        self.check_interval_s = check_interval_s
        self.factor = factor
        self._watched: dict[str, WatchedLoop] = {}
        self.restarts: dict[str, int] = {}

    def watch(
        self,
        equipment_id: str,
        *,
        poll_interval_s: float,
        last_tick: Callable[[], int | None],
        restart: Callable[[], Awaitable[None]],
    ) -> None:
        """Começa a vigiar um loop. Registrar de novo substitui o registro anterior."""
        self._watched[equipment_id] = WatchedLoop(
            equipment_id=equipment_id,
            poll_interval_s=poll_interval_s,
            last_tick_mono_ns=last_tick,
            restart=restart,
            registered_mono_ns=self._clock.monotonic_ns(),
        )

    def unwatch(self, equipment_id: str) -> None:
        self._watched.pop(equipment_id, None)

    def watched(self) -> list[str]:
        return list(self._watched)

    def silence_s(self, equipment_id: str) -> float | None:
        """Quanto tempo o loop está sem tick; None se não é vigiado."""
        w = self._watched.get(equipment_id)
        if w is None:
            return None
        last = w.last_tick_mono_ns()
        ref = w.registered_mono_ns if last is None else max(last, w.registered_mono_ns)
        return max(0.0, (self._clock.monotonic_ns() - ref) / _NS)

    def is_overdue(self, equipment_id: str) -> bool:
        w = self._watched.get(equipment_id)
        silence = self.silence_s(equipment_id)
        if w is None or silence is None:
            return False
        return silence > self.factor * w.poll_interval_s

    async def check_once(self) -> list[str]:
        """Uma rodada de verificação. Devolve os ids reiniciados."""
        restarted: list[str] = []
        for w in list(self._watched.values()):
            if not self.is_overdue(w.equipment_id):
                continue
            logger.warning(
                "watchdog: %s sem tick há %.1f s; reiniciando task",
                w.equipment_id,
                self.silence_s(w.equipment_id) or 0.0,
            )
            try:
                await w.restart()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("watchdog: falha ao reiniciar %s", w.equipment_id)
                continue
            self.restarts[w.equipment_id] = self.restarts.get(w.equipment_id, 0) + 1
            restarted.append(w.equipment_id)
        return restarted

    async def run(self) -> None:
        """Task do watchdog. Só termina por cancelamento."""
        while True:
            await self._clock.sleep(self.check_interval_s)
            try:
                await self.check_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("watchdog: erro inesperado na verificação")
