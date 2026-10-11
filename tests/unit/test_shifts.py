"""Turnos da planta: configuração, janela de cada turno no fuso da planta e turno em andamento.

Os horários são de exemplo do teste; os da planta vêm de `config/forja.yaml` (`plant.shifts`).
America/Sao_Paulo não tem horário de verão desde 2019: o fuso é UTC-3 o ano todo.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from forja.config.models import ForjaConfig, PlantConfig, ShiftConfig
from forja.reports.shifts import current_shift, local_day, shift_window

ZONE = ZoneInfo("America/Sao_Paulo")
DAY = date(2026, 10, 11)
MORNING = ShiftConfig(name="Turno 1", start="06:00", end="14:00")
AFTERNOON = ShiftConfig(name="Turno 2", start="14:00", end="22:00")
NIGHT = ShiftConfig(name="Turno 3", start="22:00", end="06:00")
ALL = [MORNING, AFTERNOON, NIGHT]


def utc(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=UTC)


def test_day_shift_window_is_in_plant_time() -> None:
    assert shift_window(MORNING, DAY, ZONE) == (utc(11, 9), utc(11, 17))


def test_night_shift_ends_on_the_next_day() -> None:
    assert shift_window(NIGHT, DAY, ZONE) == (utc(12, 1), utc(12, 9))


def test_current_shift_is_the_one_running_now() -> None:
    assert current_shift(ALL, utc(11, 18, 30), ZONE) == (1, DAY)


def test_after_midnight_the_night_shift_belongs_to_the_day_it_started() -> None:
    assert current_shift(ALL, utc(12, 5), ZONE) == (2, DAY)


def test_shift_start_belongs_to_it_and_its_end_to_the_next() -> None:
    assert current_shift(ALL, utc(11, 17), ZONE) == (1, DAY)


def test_no_current_shift_when_no_shift_covers_the_hour() -> None:
    assert current_shift([MORNING], utc(11, 20), ZONE) is None
    assert current_shift([], utc(11, 20), ZONE) is None


def test_local_day_follows_the_plant_zone() -> None:
    assert local_day(utc(12, 2), ZONE) == DAY


def test_plant_without_shifts_by_default() -> None:
    assert ForjaConfig().plant.shifts == []


@pytest.mark.parametrize("hhmm", ["24:00", "6:00", "06:60", "0600", "", "06:00:00"])
def test_shift_hours_are_hh_mm(hhmm: str) -> None:
    with pytest.raises(ValidationError):
        ShiftConfig(name="Turno 1", start=hhmm, end="14:00")


def test_shift_needs_a_name_and_different_start_and_end() -> None:
    with pytest.raises(ValidationError):
        ShiftConfig(name="  ", start="06:00", end="14:00")
    with pytest.raises(ValidationError):
        ShiftConfig(name="Turno 1", start="06:00", end="06:00")


def test_shift_names_are_unique() -> None:
    with pytest.raises(ValidationError):
        PlantConfig(shifts=[MORNING, MORNING])
