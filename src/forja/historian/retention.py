"""Retencao: apaga so o que passou do prazo, em lotes pequenos, par a par pela PK.

Regras:
- bruto: > raw_retention_days; SIMULATED > raw_simulated_retention_days;
  nunca apaga bruto com ts >= marca d'agua de agg_1m (ainda nao consolidado). Sem marca d'agua,
  nenhum bruto e apagado;
- agg_1m: > rollup_1m_retention_days e nunca alem da marca d'agua de agg_1h;
- agg_1h: > rollup_1h_retention_days quando configurado (None = guarda para sempre);
- comm_log: acompanha raw_retention_days.
Cada lote e uma transacao curta (autocommit): a escrita ao vivo nao espera a limpeza inteira.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from typing import Final

from forja.config.models import HistorianConfig
from forja.domain.quality import Quality
from forja.historian.queries import SQL_PAIRS, quality_to_code
from forja.historian.rollups import WATERMARK_1H, WATERMARK_1M, get_watermark

DAY_MS: Final[int] = 86_400_000
CHUNK: Final[int] = 20_000

_SQL_DELETE_RAW = """
DELETE FROM samples WHERE (equipment_id, tag, ts_utc_ms) IN (
    SELECT equipment_id, tag, ts_utc_ms FROM samples
    WHERE equipment_id = ? AND tag = ? AND ts_utc_ms < ? AND quality {op} ?
    ORDER BY ts_utc_ms LIMIT ?
)
"""
_SQL_DELETE_AGG = """
DELETE FROM {table} WHERE (equipment_id, tag, bucket_start_ms) IN (
    SELECT equipment_id, tag, bucket_start_ms FROM {table}
    WHERE equipment_id = ? AND tag = ? AND bucket_start_ms < ?
    ORDER BY bucket_start_ms LIMIT ?
)
"""
_SQL_DELETE_COMM = (
    "DELETE FROM comm_log WHERE id IN (SELECT id FROM comm_log WHERE ts_utc_ms < ? LIMIT ?)"
)


def _delete_chunked(conn: sqlite3.Connection, sql: str, params: Sequence[object]) -> int:
    """Repete o DELETE em lotes ate nao sobrar linha elegivel."""
    total = 0
    while True:
        cur = conn.execute(sql, (*params, CHUNK))
        n = max(cur.rowcount, 0)
        total += n
        if n < CHUNK:
            return total


def _cutoff(now_ms: int, days: int | None, watermark_ms: int | None) -> int | None:
    """Limite de apagamento: o menor entre o prazo e a marca d'agua. None = nao apaga."""
    if days is None:
        return None
    by_age = now_ms - days * DAY_MS
    if watermark_ms is None:
        return None
    return min(by_age, watermark_ms)


def _pairs(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    return [(str(e), str(t)) for e, t in conn.execute(SQL_PAIRS).fetchall()]


def run_retention(conn: sqlite3.Connection, config: HistorianConfig, now_ms: int) -> dict[str, int]:
    """Aplica a retencao configurada. Devolve linhas apagadas por tabela."""
    wm_1m = get_watermark(conn, WATERMARK_1M)
    wm_1h = get_watermark(conn, WATERMARK_1H)
    sim = quality_to_code(Quality.SIMULATED)
    raw_cut = _cutoff(now_ms, config.raw_retention_days, wm_1m)
    sim_cut = _cutoff(now_ms, config.raw_simulated_retention_days, wm_1m)
    agg_1m_cut = _cutoff(now_ms, config.rollup_1m_retention_days, wm_1h)
    agg_1h_cut = (
        None
        if config.rollup_1h_retention_days is None
        else now_ms - config.rollup_1h_retention_days * DAY_MS
    )
    comm_cut = now_ms - config.raw_retention_days * DAY_MS

    out = {"samples": 0, "samples_simulated": 0, "samples_agg_1m": 0, "samples_agg_1h": 0}
    sql_raw_other = _SQL_DELETE_RAW.format(op="<>")
    sql_raw_sim = _SQL_DELETE_RAW.format(op="=")
    sql_agg_1m = _SQL_DELETE_AGG.format(table="samples_agg_1m")
    sql_agg_1h = _SQL_DELETE_AGG.format(table="samples_agg_1h")
    for eq, tag in _pairs(conn):
        if raw_cut is not None:
            out["samples"] += _delete_chunked(conn, sql_raw_other, (eq, tag, raw_cut, sim))
        if sim_cut is not None:
            out["samples_simulated"] += _delete_chunked(conn, sql_raw_sim, (eq, tag, sim_cut, sim))
        if agg_1m_cut is not None:
            out["samples_agg_1m"] += _delete_chunked(conn, sql_agg_1m, (eq, tag, agg_1m_cut))
        if agg_1h_cut is not None:
            out["samples_agg_1h"] += _delete_chunked(conn, sql_agg_1h, (eq, tag, agg_1h_cut))
    out["comm_log"] = _delete_chunked(conn, _SQL_DELETE_COMM, (comm_cut,))
    return out
