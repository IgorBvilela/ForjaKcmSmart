"""Exportacao CSV do historico.

Toda linha leva instante (UTC e horario da planta), valor, unidade e qualidade. Leitura sem
valor (COMM_ERROR, BAD) sai com valor vazio e o motivo: nunca vira zero nem e preenchida.

Dois dialetos:
- BR: separador ';', virgula decimal e BOM UTF-8 (abre direto no Excel em portugues);
- STD: separador ',', ponto decimal, sem BOM (ferramentas e scripts).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Iterator, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from forja.domain import TAGS, Quality, Series
from forja.events.plant_time import resolve_zone

BOM = "﻿"
ROWS_PER_CHUNK = 2000

RAW_HEADER: tuple[str, ...] = (
    "data_hora_utc",
    "data_hora_planta",
    "equipamento",
    "tag",
    "variavel",
    "valor",
    "unidade",
    "qualidade",
    "qualidade_texto",
    "origem",
    "motivo",
)

AGG_HEADER: tuple[str, ...] = (
    "inicio_utc",
    "inicio_planta",
    "intervalo_s",
    "equipamento",
    "tag",
    "variavel",
    "media",
    "minimo",
    "maximo",
    "leituras",
    "unidade",
    "pior_qualidade",
    "qualidade_texto",
)


class CsvDialect(StrEnum):
    BR = "br"
    STD = "std"


class RowLike(Protocol):
    """Linha bruta do historian (ExportRow)."""

    @property
    def tag(self) -> str: ...
    @property
    def ts_utc(self) -> datetime: ...
    @property
    def value(self) -> float | None: ...
    @property
    def quality(self) -> Quality: ...
    @property
    def source(self) -> str: ...
    @property
    def reason_pt(self) -> str | None: ...


def _delimiter(dialect: CsvDialect) -> str:
    return ";" if dialect is CsvDialect.BR else ","


def fmt_value(value: float | None, dialect: CsvDialect) -> str:
    """repr curto do float (sem perder casas); virgula decimal no dialeto BR; None vira vazio."""
    if value is None:
        return ""
    text = repr(float(value))
    return text.replace(".", ",") if dialect is CsvDialect.BR else text


def iso_utc(ts: datetime) -> str:
    """2026-10-01T17:00:00.000Z"""
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.") + f"{ts.microsecond // 1000:03d}Z"


def local_text(ts: datetime, timezone: str) -> str:
    """2026-10-01 14:00:00.000 no fuso da planta (sem sufixo: a coluna diz o que e)."""
    local = ts.astimezone(resolve_zone(timezone))
    return local.strftime("%Y-%m-%d %H:%M:%S.") + f"{local.microsecond // 1000:03d}"


def _chunks(
    header: Sequence[str], rows: Iterable[Sequence[str]], dialect: CsvDialect
) -> Iterator[str]:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=_delimiter(dialect), lineterminator="\r\n")
    if dialect is CsvDialect.BR:
        buf.write(BOM)
    writer.writerow(header)
    n = 0
    for row in rows:
        writer.writerow(row)
        n += 1
        if n % ROWS_PER_CHUNK == 0:
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)
    tail = buf.getvalue()
    if tail:
        yield tail


def raw_csv(
    rows: Iterable[RowLike], *, equipment_id: str, timezone: str, dialect: CsvDialect
) -> Iterator[str]:
    """Pontos exatamente como gravados no historian."""

    def lines() -> Iterator[Sequence[str]]:
        for r in rows:
            meta = TAGS.get(r.tag)
            yield (
                iso_utc(r.ts_utc),
                local_text(r.ts_utc, timezone),
                equipment_id,
                r.tag,
                meta.label_pt if meta else r.tag,
                fmt_value(r.value, dialect),
                meta.unit if meta else "",
                r.quality.value,
                r.quality.label_pt,
                r.source,
                r.reason_pt or "",
            )

    return _chunks(RAW_HEADER, lines(), dialect)


def aggregated_csv(
    series: Iterable[Series], *, equipment_id: str, timezone: str, dialect: CsvDialect
) -> Iterator[str]:
    """Um intervalo por linha: media, minimo, maximo, numero de leituras e pior qualidade."""

    def lines() -> Iterator[Sequence[str]]:
        for s in series:
            meta = TAGS.get(s.tag)
            for p in s.points:
                yield (
                    iso_utc(p.ts_utc),
                    local_text(p.ts_utc, timezone),
                    str(s.bucket_s),
                    equipment_id,
                    s.tag,
                    meta.label_pt if meta else s.tag,
                    fmt_value(p.value, dialect),
                    fmt_value(p.min, dialect),
                    fmt_value(p.max, dialect),
                    str(p.n),
                    meta.unit if meta else "",
                    p.quality.value,
                    p.quality.label_pt,
                )

    return _chunks(AGG_HEADER, lines(), dialect)


def export_filename(equipment_id: str, start: datetime, end: datetime, kind: str) -> str:
    """forja_<eq>_<inicio>_<fim>_<bruto|resumido>.csv (so caracteres seguros)."""
    label = "bruto" if kind == "raw" else "resumido"
    fmt = "%Y%m%dT%H%M%SZ"
    safe_eq = "".join(c for c in equipment_id if c.isalnum() or c == "_")[:64]
    return (
        f"forja_{safe_eq}_{start.astimezone(UTC).strftime(fmt)}_"
        f"{end.astimezone(UTC).strftime(fmt)}_{label}.csv"
    )


__all__ = [
    "AGG_HEADER",
    "RAW_HEADER",
    "CsvDialect",
    "RowLike",
    "aggregated_csv",
    "export_filename",
    "fmt_value",
    "raw_csv",
]
