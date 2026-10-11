"""Turnos da planta: a janela de cada turno e o turno em andamento, no fuso da planta.

Os horários vêm da configuração da planta (`config/forja.yaml`, seção `plant.shifts`), nunca do
código. Um turno com fim antes do início termina no dia seguinte; a data de um turno é a do dia
em que ele começa. O início pertence ao turno e o fim ao turno seguinte.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta, tzinfo

from forja.config.models import ShiftConfig


def _clock(hhmm: str) -> time:
    hour, minute = hhmm.split(":")
    return time(int(hour), int(minute))


def shift_window(shift: ShiftConfig, day: date, zone: tzinfo) -> tuple[datetime, datetime]:
    """[início, fim) do turno que começa em `day`, em UTC."""
    start = datetime.combine(day, _clock(shift.start), tzinfo=zone)
    end_day = day + timedelta(days=1) if shift.end < shift.start else day
    end = datetime.combine(end_day, _clock(shift.end), tzinfo=zone)
    return start.astimezone(UTC), end.astimezone(UTC)


def local_day(now_utc: datetime, zone: tzinfo) -> date:
    """O dia de hoje no relógio da planta."""
    return now_utc.astimezone(zone).date()


def current_shift(
    shifts: Sequence[ShiftConfig], now_utc: datetime, zone: tzinfo
) -> tuple[int, date] | None:
    """(índice, data) do turno em andamento; o turno da noite depois da meia-noite é do dia
    anterior. None quando nenhum turno cobre a hora."""
    today = local_day(now_utc, zone)
    for day in (today, today - timedelta(days=1)):
        for index, shift in enumerate(shifts):
            start, end = shift_window(shift, day, zone)
            if start <= now_utc < end:
                return index, day
    return None


__all__ = ["current_shift", "local_day", "shift_window"]
