"""Exportação CSV: timestamp, valor, unidade e qualidade sempre juntos; buraco nunca vira número."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta

import pytest

from forja.domain import Quality, Series, SeriesPoint
from forja.historian.sqlite import ExportRow
from forja.reports.csv_export import (
    CsvDialect,
    aggregated_csv,
    export_filename,
    raw_csv,
)

pytestmark = pytest.mark.unit

T0 = datetime(2026, 10, 1, 17, 0, 0, tzinfo=UTC)


def _parse(text: str, delimiter: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text.lstrip("﻿")), delimiter=delimiter))


def _rows() -> list[ExportRow]:
    return [
        ExportRow("mass_flow", T0, 1300.5, Quality.SIMULATED, "sim:NORMAL", None),
        ExportRow(
            "mass_flow", T0 + timedelta(seconds=1), None, Quality.COMM_ERROR, "x", "Tempo esgotado"
        ),
        ExportRow("belt_load", T0, 2.0, Quality.UNCERTAIN, "driver:modbus_tcp:m@1", None),
    ]


def test_csv_brasileiro_usa_ponto_e_virgula_virgula_decimal_e_bom() -> None:
    text = "".join(
        raw_csv(_rows(), equipment_id="EQ", timezone="America/Sao_Paulo", dialect=CsvDialect.BR)
    )
    assert text.startswith("﻿")
    rows = _parse(text, ";")
    header = rows[0]
    for col in ("data_hora_utc", "valor", "unidade", "qualidade"):
        assert col in header
    first = dict(zip(header, rows[1], strict=True))
    assert first["valor"] == "1300,5"
    assert first["unidade"] == "kg/h"
    assert first["qualidade"] == "SIMULATED"
    assert first["qualidade_texto"] == "Simulado"
    assert first["data_hora_utc"] == "2026-10-01T17:00:00.000Z"
    assert first["data_hora_planta"] == "2026-10-01 14:00:00.000"


def test_csv_padrao_usa_virgula_e_ponto() -> None:
    text = "".join(raw_csv(_rows(), equipment_id="EQ", timezone="UTC", dialect=CsvDialect.STD))
    assert not text.startswith("﻿")
    rows = _parse(text, ",")
    first = dict(zip(rows[0], rows[1], strict=True))
    assert first["valor"] == "1300.5"


def test_falha_de_comunicacao_sai_com_valor_vazio_e_motivo() -> None:
    text = "".join(raw_csv(_rows(), equipment_id="EQ", timezone="UTC", dialect=CsvDialect.STD))
    rows = _parse(text, ",")
    second = dict(zip(rows[0], rows[2], strict=True))
    assert second["valor"] == ""
    assert second["qualidade"] == "COMM_ERROR"
    assert second["motivo"] == "Tempo esgotado"


def test_csv_resumido_tem_media_minimo_maximo_e_pior_qualidade() -> None:
    series = Series(
        equipment_id="EQ",
        tag="mass_flow",
        resolution="1m",
        bucket_s=60,
        points=(
            SeriesPoint(
                ts_utc=T0, value=1300.0, quality=Quality.GOOD, min=1290.0, max=1310.0, n=60
            ),
            SeriesPoint(
                ts_utc=T0 + timedelta(minutes=1), value=None, quality=Quality.COMM_ERROR, n=0
            ),
        ),
        downsampled=True,
    )
    text = "".join(
        aggregated_csv([series], equipment_id="EQ", timezone="UTC", dialect=CsvDialect.STD)
    )
    rows = _parse(text, ",")
    header = rows[0]
    a = dict(zip(header, rows[1], strict=True))
    b = dict(zip(header, rows[2], strict=True))
    assert (a["media"], a["minimo"], a["maximo"], a["leituras"]) == (
        "1300.0",
        "1290.0",
        "1310.0",
        "60",
    )
    assert a["intervalo_s"] == "60"
    assert b["media"] == ""
    assert b["leituras"] == "0"
    assert b["pior_qualidade"] == "COMM_ERROR"


def test_nome_do_arquivo_e_seguro() -> None:
    name = export_filename("GTEX_PHA_PO_BASE", T0, T0 + timedelta(hours=1), "raw")
    assert name == "forja_GTEX_PHA_PO_BASE_20261001T170000Z_20261001T180000Z_bruto.csv"
