"""Exportação CSV dos eventos e avisos de um equipamento num período.

Uma linha por evento, com origem (evento da Forja ou aviso antecipado), instantes em UTC e no
horário da planta, duração, estado, qualidade dos dados que o dispararam, a primeira variável a
sair do padrão e o resumo. Mesmos dialetos do histórico (BR com BOM e ';', STD com ',').
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator, Sequence
from datetime import datetime

from forja.domain import Event
from forja.events.pre_event import pre_event_summary
from forja.events.recurrence import ORIGIN_PT
from forja.reports.csv_export import BOM, CsvDialect, fmt_value, iso_utc, local_text

EVENTS_HEADER: tuple[str, ...] = (
    "inicio_utc",
    "inicio_planta",
    "fim_utc",
    "fim_planta",
    "duracao_s",
    "equipamento",
    "origem",
    "tipo",
    "titulo",
    "severidade",
    "estado",
    "qualidade",
    "primeira_variavel",
    "antecedencia_s",
    "reconhecido_por",
    "resumo",
)


def events_csv(
    events: Sequence[Event], *, equipment_id: str, timezone: str, dialect: CsvDialect
) -> Iterator[str]:
    buf = io.StringIO()
    writer = csv.writer(
        buf, delimiter=";" if dialect is CsvDialect.BR else ",", lineterminator="\n"
    )
    if dialect is CsvDialect.BR:
        buf.write(BOM)
    writer.writerow(EVENTS_HEADER)
    for e in sorted(events, key=lambda ev: ev.start_utc):
        pre = pre_event_summary(e)
        writer.writerow(
            (
                iso_utc(e.start_utc),
                local_text(e.start_utc, timezone),
                iso_utc(e.end_utc) if e.end_utc else "",
                local_text(e.end_utc, timezone) if e.end_utc else "",
                fmt_value(e.duration_s, dialect),
                equipment_id,
                ORIGIN_PT.get(e.origin, e.origin),
                e.type,
                e.title_pt,
                e.severity.label_pt,
                e.status.value,
                e.quality.value,
                pre["first_label_pt"] or "",
                fmt_value(pre["lead_s"], dialect),
                e.acked_by or "",
                e.summary_pt,
            )
        )
    yield buf.getvalue()


def in_period(events: Sequence[Event], start: datetime, end: datetime) -> list[Event]:
    return [e for e in events if e.start_utc <= end and (e.end_utc is None or e.end_utc >= start)]


__all__ = ["EVENTS_HEADER", "events_csv", "in_period"]
