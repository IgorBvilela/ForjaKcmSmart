"""Bus pub/sub assincrono in-process. Um topico, N assinantes, cada um com fila propria.
Assinante lento perde mensagens antigas (fila limitada), nunca trava o produtor."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any


class AsyncBus:
    def __init__(self, maxsize: int = 1000) -> None:
        self._subs: dict[str, list[asyncio.Queue[Any]]] = {}
        self._maxsize = maxsize
        self.dropped = 0

    async def publish(self, topic: str, payload: Any) -> None:
        for q in list(self._subs.get(topic, ())):
            if q.full():
                try:
                    q.get_nowait()
                    self.dropped += 1
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(payload)

    def subscribe(self, topic: str) -> AsyncIterator[Any]:
        q: asyncio.Queue[Any] = asyncio.Queue(maxsize=self._maxsize)
        self._subs.setdefault(topic, []).append(q)

        async def _gen() -> AsyncIterator[Any]:
            try:
                while True:
                    yield await q.get()
            finally:
                subs = self._subs.get(topic, [])
                if q in subs:
                    subs.remove(q)

        return _gen()

    def subscriber_count(self, topic: str) -> int:
        return len(self._subs.get(topic, ()))
