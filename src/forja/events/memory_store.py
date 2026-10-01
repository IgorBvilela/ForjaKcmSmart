"""Repositorios em memoria (EventRepository e DiagnosisRepository) para testes e CLI offline.

Mesma semantica do core store SQLite: save e upsert por id; list vem do mais novo para o mais
antigo; find_open devolve o evento aberto de uma dedupe_key.
"""

from __future__ import annotations

from datetime import datetime

from forja.domain import Diagnosis, Event


class InMemoryEventRepository:
    def __init__(self) -> None:
        self._events: dict[str, Event] = {}

    async def save(self, event: Event) -> None:
        self._events[event.id] = event

    async def get(self, event_id: str) -> Event | None:
        return self._events.get(event_id)

    async def list(
        self,
        equipment_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        open_only: bool = False,
        limit: int = 200,
    ) -> list[Event]:
        out = [
            e
            for e in self._events.values()
            if (equipment_id is None or e.equipment_id == equipment_id)
            and (since is None or e.start_utc >= since)
            and (until is None or e.start_utc <= until)
            and (not open_only or e.is_open)
        ]
        out.sort(key=lambda e: (e.start_utc, e.id), reverse=True)
        return out[: max(0, limit)]

    async def find_open(self, equipment_id: str, dedupe_key: str) -> Event | None:
        for e in self._events.values():
            if e.equipment_id == equipment_id and e.dedupe_key == dedupe_key and e.is_open:
                return e
        return None

    def __len__(self) -> int:
        return len(self._events)


class InMemoryDiagnosisRepository:
    def __init__(self) -> None:
        self._by_event: dict[str, Diagnosis] = {}

    async def save(self, diagnosis: Diagnosis) -> None:
        self._by_event[diagnosis.event_id] = diagnosis

    async def get_for_event(self, event_id: str) -> Diagnosis | None:
        return self._by_event.get(event_id)

    async def list(self, equipment_id: str | None = None, limit: int = 100) -> list[Diagnosis]:
        out = [
            d
            for d in self._by_event.values()
            if equipment_id is None or d.equipment_id == equipment_id
        ]
        out.sort(key=lambda d: (d.generated_at_utc, d.diagnosis_id), reverse=True)
        return out[: max(0, limit)]

    def __len__(self) -> int:
        return len(self._by_event)
