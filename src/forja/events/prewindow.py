"""Janela deslizante de amostras por equipamento (memoria curta do motor de regras).

Guarda os ultimos buffer_s segundos de amostras, ordenadas por ts_utc, para:
- referencia de janela nas condicoes (queda/subida/taxa);
- pre-janela do evento ('o que aconteceu antes');
- amostras durante e depois do evento.
Nunca interpola: o que nao foi lido simplesmente nao esta aqui.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from datetime import datetime, timedelta

from forja.domain import Quality, Sample, SampleBatch


class SampleBuffer:
    """Buffer limitado em tempo. Uma deque por tag, cada uma ordenada por ts_utc."""

    def __init__(self, buffer_s: int) -> None:
        if buffer_s <= 0:
            raise ValueError("buffer_s deve ser positivo")
        self.buffer_s = buffer_s
        self._by_tag: dict[str, deque[Sample]] = {}
        self._latest_ts: datetime | None = None

    @property
    def latest_ts(self) -> datetime | None:
        return self._latest_ts

    @property
    def tags(self) -> tuple[str, ...]:
        return tuple(self._by_tag.keys())

    def add(self, batch: SampleBatch) -> None:
        """Acrescenta as amostras de um lote e descarta o que ficou mais velho que buffer_s."""
        for s in batch.samples:
            dq = self._by_tag.setdefault(s.tag, deque())
            if dq and dq[-1].ts_utc > s.ts_utc:
                self._insert_sorted(dq, s)
            else:
                dq.append(s)
        if self._latest_ts is None or batch.ts_utc > self._latest_ts:
            self._latest_ts = batch.ts_utc
        self._evict()

    @staticmethod
    def _insert_sorted(dq: deque[Sample], sample: Sample) -> None:
        items = list(dq)
        idx = len(items)
        while idx > 0 and items[idx - 1].ts_utc > sample.ts_utc:
            idx -= 1
        items.insert(idx, sample)
        dq.clear()
        dq.extend(items)

    def _evict(self) -> None:
        if self._latest_ts is None:
            return
        limit = self._latest_ts - timedelta(seconds=self.buffer_s)
        for dq in self._by_tag.values():
            while dq and dq[0].ts_utc < limit:
                dq.popleft()

    def between(
        self,
        start: datetime,
        end: datetime,
        tags: Iterable[str] | None = None,
        include_end: bool = True,
    ) -> tuple[Sample, ...]:
        """Amostras com start <= ts < end (ou <= end), ordenadas por (ts, tag)."""
        wanted = tuple(tags) if tags is not None else self.tags
        out: list[Sample] = []
        for tag in wanted:
            for s in self._by_tag.get(tag, ()):
                if s.ts_utc < start:
                    continue
                if s.ts_utc > end or (s.ts_utc == end and not include_end):
                    break
                out.append(s)
        out.sort(key=lambda s: (s.ts_utc, s.tag))
        return tuple(out)

    def tag_values(
        self,
        tag: str,
        start: datetime,
        end: datetime,
        allowed: frozenset[Quality],
        include_end: bool = False,
    ) -> list[Sample]:
        """Amostras utilizaveis de uma tag na janela [start, end) (ou [start, end])."""
        out: list[Sample] = []
        for s in self._by_tag.get(tag, ()):
            if s.ts_utc < start:
                continue
            if s.ts_utc > end or (s.ts_utc == end and not include_end):
                break
            if s.value is not None and s.quality in allowed:
                out.append(s)
        return out

    def previous(self, tag: str, before: datetime, allowed: frozenset[Quality]) -> Sample | None:
        """Ultima amostra utilizavel da tag com ts < before."""
        dq = self._by_tag.get(tag)
        if not dq:
            return None
        for s in reversed(dq):
            if s.ts_utc < before and s.value is not None and s.quality in allowed:
                return s
        return None

    def pre_window(
        self, start: datetime, pre_window_s: int, tags: Iterable[str] | None = None
    ) -> tuple[Sample, ...]:
        """Amostras em [start - pre_window_s, start): o que aconteceu antes do evento."""
        begin = start - timedelta(seconds=pre_window_s)
        return self.between(begin, start, tags=tags, include_end=False)
