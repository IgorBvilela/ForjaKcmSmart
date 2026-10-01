"""Horario da planta em texto (pt-BR).

Todo horario que entra em texto para o usuario (*_pt) sai no fuso da planta, lido de
config/forja.yaml (edge.timezone). Os campos ts_utc continuam ISO UTC: a UI formata.

No Windows a zoneinfo depende do pacote `tzdata`. Se a zona nao resolver, a Forja NAO finge hora
local: cai para UTC, avisa no log e marca o texto com 'UTC'.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "America/Sao_Paulo"
MONTHS_ABBR_PT: tuple[str, ...] = (
    "jan.",
    "fev.",
    "mar.",
    "abr.",
    "maio",
    "jun.",
    "jul.",
    "ago.",
    "set.",
    "out.",
    "nov.",
    "dez.",
)


def resolve_zone(name: str | tzinfo | None) -> tzinfo:
    """Nome IANA -> tzinfo. Nome vazio = fuso padrao. Zona desconhecida = UTC, com aviso."""
    if isinstance(name, tzinfo):
        return name
    key = (name or DEFAULT_TIMEZONE).strip()
    if key.upper() == "UTC":
        return UTC
    try:
        return ZoneInfo(key)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning(
            "fuso %r não encontrado (pacote tzdata instalado?); horários em texto sairão em UTC",
            key,
        )
        return UTC


def is_utc(zone: tzinfo) -> bool:
    return zone is UTC or zone == UTC


def zone_note_pt(zone: tzinfo) -> str:
    return "horário UTC" if is_utc(zone) else "horário da planta"


def fmt_time_pt(ts: datetime, zone: tzinfo, reference: datetime | None = None) -> str:
    """'10:44:54' no fuso da planta; '1 de out., 10:44:54' quando o dia difere da referencia.

    `reference` e o instante em relacao ao qual o texto sera lido (ex.: geracao do diagnostico).
    Sem referencia, so a hora. Em UTC (fallback), o texto termina em 'UTC' para nao enganar.
    """
    local = _local(ts, zone)
    clock = local.strftime("%H:%M:%S")
    if reference is not None and _local(reference, zone).date() != local.date():
        clock = f"{local.day} de {MONTHS_ABBR_PT[local.month - 1]}, {clock}"
    return _with_suffix(clock, zone)


def fmt_datetime_pt(ts: datetime, zone: tzinfo) -> str:
    """'1 de out. de 2026, 10:44:54' no fuso da planta."""
    local = _local(ts, zone)
    text = (
        f"{local.day} de {MONTHS_ABBR_PT[local.month - 1]} de {local.year}, "
        f"{local.strftime('%H:%M:%S')}"
    )
    return _with_suffix(text, zone)


def _with_suffix(text: str, zone: tzinfo) -> str:
    return f"{text} UTC" if is_utc(zone) else text


def _local(ts: datetime, zone: tzinfo) -> datetime:
    if ts.tzinfo is None:
        raise ValueError("horário sem fuso: todo ts da Forja é UTC com tzinfo")
    return ts.astimezone(zone)


__all__ = [
    "DEFAULT_TIMEZONE",
    "fmt_datetime_pt",
    "fmt_time_pt",
    "is_utc",
    "resolve_zone",
    "zone_note_pt",
]
