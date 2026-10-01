"""Rollups: agg_1m a partir do bruto, agg_1h a partir de agg_1m. Roda na thread escritora.

Marca d'agua (rollup_state): inicio do primeiro bucket ainda nao consolidado. So minutos
fechados entram (bucket_end <= agora). Os ultimos RECOMPUTE_MINUTES antes da marca sao
recalculados a cada rodada para absorver escrita atrasada. A hora so fecha quando todos os
seus minutos ja estao em agg_1m.
"""

from __future__ import annotations

import sqlite3
from typing import Final

from forja.historian.queries import (
    HOUR_MS,
    MINUTE_MS,
    SQL_FIRST_SAMPLE_MS,
    SQL_GET_WATERMARK,
    SQL_SET_WATERMARK,
    bucket_params,
    floor_ms,
    sql_bucket_agg,
    sql_bucket_raw,
    sql_rollup_insert,
)

WATERMARK_1M: Final[str] = "agg_1m"
WATERMARK_1H: Final[str] = "agg_1h"
RECOMPUTE_MINUTES: Final[int] = 5
RECOMPUTE_HOURS: Final[int] = 2


def get_watermark(conn: sqlite3.Connection, name: str) -> int | None:
    """Marca d'agua de um rollup ou None se nunca rodou."""
    row = conn.execute(SQL_GET_WATERMARK, (name,)).fetchone()
    return None if row is None else int(row[0])


def set_watermark(conn: sqlite3.Connection, name: str, watermark_ms: int) -> None:
    conn.execute(SQL_SET_WATERMARK, (name, watermark_ms))


def _first_sample_minute(conn: sqlite3.Connection) -> int | None:
    row = conn.execute(SQL_FIRST_SAMPLE_MS).fetchone()
    if row is None or row[0] is None:
        return None
    return floor_ms(int(row[0]), MINUTE_MS)


def _first_agg_1m_hour(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT MIN(bucket_start_ms) FROM samples_agg_1m").fetchone()
    if row is None or row[0] is None:
        return None
    return floor_ms(int(row[0]), HOUR_MS)


def _run_insert(
    conn: sqlite3.Connection, sql: str, params: dict[str, int | str | None], name: str, wm: int
) -> int:
    """Executa o INSERT de rollup e avanca a marca d'agua, na mesma transacao."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        cur = conn.execute(sql, params)
        changed = max(cur.rowcount, 0)
        set_watermark(conn, name, wm)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return changed


def rollup_1m(conn: sqlite3.Connection, now_ms: int) -> tuple[int, int | None]:
    """Consolida minutos fechados em agg_1m. Devolve (linhas afetadas, marca d'agua nova)."""
    closed_until = floor_ms(now_ms, MINUTE_MS)
    wm = get_watermark(conn, WATERMARK_1M)
    if wm is None:
        start = _first_sample_minute(conn)
        if start is None:
            return 0, None
    else:
        start = wm - RECOMPUTE_MINUTES * MINUTE_MS
    new_wm = max(closed_until, wm or 0)
    if start >= new_wm:
        return 0, wm
    sql = sql_rollup_insert("samples_agg_1m", sql_bucket_raw(scoped=False))
    changed = _run_insert(conn, sql, bucket_params(MINUTE_MS, start, new_wm), WATERMARK_1M, new_wm)
    return changed, new_wm


def rollup_1h(conn: sqlite3.Connection, now_ms: int, wm_1m: int | None) -> tuple[int, int | None]:
    """Consolida horas fechadas (e ja cobertas por agg_1m) em agg_1h."""
    if wm_1m is None:
        return 0, get_watermark(conn, WATERMARK_1H)
    closed_until = min(floor_ms(now_ms, HOUR_MS), floor_ms(wm_1m, HOUR_MS))
    wm = get_watermark(conn, WATERMARK_1H)
    if wm is None:
        start = _first_agg_1m_hour(conn)
        if start is None:
            return 0, None
    else:
        start = wm - RECOMPUTE_HOURS * HOUR_MS
    new_wm = max(closed_until, wm or 0)
    if start >= new_wm:
        return 0, wm
    sql = sql_rollup_insert("samples_agg_1h", sql_bucket_agg("samples_agg_1m", scoped=False))
    changed = _run_insert(conn, sql, bucket_params(HOUR_MS, start, new_wm), WATERMARK_1H, new_wm)
    return changed, new_wm


def run_rollups(conn: sqlite3.Connection, now_ms: int) -> dict[str, int]:
    """Roda 1m e depois 1h.

    Chaves: agg_1m, agg_1h (linhas afetadas) e watermark_1m_ms/watermark_1h_ms (-1 se nenhuma).
    """
    n_1m, wm_1m = rollup_1m(conn, now_ms)
    n_1h, wm_1h = rollup_1h(conn, now_ms, wm_1m)
    return {
        "agg_1m": n_1m,
        "agg_1h": n_1h,
        "watermark_1m_ms": -1 if wm_1m is None else wm_1m,
        "watermark_1h_ms": -1 if wm_1h is None else wm_1h,
    }
