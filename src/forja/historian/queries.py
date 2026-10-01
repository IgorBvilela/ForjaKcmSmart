"""Vocabulario SQL do historian: codecs (tempo, qualidade), buckets e consultas.

Convencoes do banco:
- tempo: INTEGER epoch ms UTC (``to_ms``/``from_ms``);
- quality: INTEGER pelo mapa fixo ``QUALITY_CODE``. Quanto maior, pior; por isso ``MAX(quality)``
  e a pior qualidade de um bucket. O mapa e igual a ``Quality.rank`` hoje e um teste garante isso;
  se o dominio mudar, a mudanca aqui exige migracao de dados;
- value NULL = sem valor (COMM_ERROR). GAP = bucket sem linha (n=0), quality COMM_ERROR
  (convencao do dominio: conjunto vazio = nada foi lido). Nunca interpolado.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final, Literal

from forja.domain.errors import HistorianError
from forja.domain.ports import SeriesPoint
from forja.domain.quality import Quality
from forja.domain.samples import Sample

# ----------------------------------------------------------------------------- codecs

QUALITY_CODE: Final[dict[Quality, int]] = {
    Quality.GOOD: 0,
    Quality.SIMULATED: 1,
    Quality.UNCERTAIN: 2,
    Quality.STALE: 3,
    Quality.BAD: 4,
    Quality.COMM_ERROR: 5,
}
CODE_QUALITY: Final[dict[int, Quality]] = {code: q for q, code in QUALITY_CODE.items()}
USABLE_MAX_CODE: Final[int] = QUALITY_CODE[Quality.UNCERTAIN]
"""Codigos <= este tem valor utilizavel (GOOD, SIMULATED, UNCERTAIN)."""
GAP_CODE: Final[int] = QUALITY_CODE[Quality.COMM_ERROR]

MINUTE_MS: Final[int] = 60_000
HOUR_MS: Final[int] = 3_600_000

Resolution = Literal["raw", "1m", "1h"]


def _as_int(value: object) -> int:
    """Celula do SQLite -> int (o driver devolve object)."""
    return int(value)  # type: ignore[call-overload,no-any-return]


def _as_float(value: object) -> float:
    return float(value)  # type: ignore[arg-type]


def quality_to_code(quality: Quality) -> int:
    """Quality -> INTEGER do banco."""
    return QUALITY_CODE[quality]


def code_to_quality(code: int) -> Quality:
    """INTEGER do banco -> Quality. Codigo desconhecido e erro de dados."""
    try:
        return CODE_QUALITY[int(code)]
    except KeyError as exc:
        raise HistorianError(f"código de qualidade desconhecido no banco: {code!r}") from exc


def to_ms(when: datetime) -> int:
    """datetime com tz -> epoch ms. Naive e recusado: nunca assumir fuso."""
    if when.tzinfo is None or when.utcoffset() is None:
        raise HistorianError("datetime sem tzinfo; o historian exige UTC explícito")
    return math.floor(when.timestamp() * 1000 + 0.5)


def from_ms(ms: int) -> datetime:
    """epoch ms -> datetime UTC, sem erro de ponto flutuante."""
    seconds, rem = divmod(int(ms), 1000)
    return datetime.fromtimestamp(seconds, UTC) + timedelta(milliseconds=rem)


def floor_ms(ms: int, bucket_ms: int) -> int:
    """Inicio do bucket (alinhado a epoch) que contem ``ms``."""
    return (ms // bucket_ms) * bucket_ms


def sample_from_row(equipment_id: str, row: Sequence[object]) -> Sample:
    """(tag, ts_utc_ms, value, quality, source, raw, reason_pt) -> Sample.

    ts_mono_ns nao e persistido: o relogio monotonico so vale dentro do processo.
    """
    tag, ts, value, quality, source, raw, reason_pt = row
    return Sample(
        ts_utc=from_ms(_as_int(ts)),
        equipment_id=equipment_id,
        tag=str(tag),
        value=None if value is None else _as_float(value),
        quality=code_to_quality(_as_int(quality)),
        source=str(source),
        raw=None if raw is None else bytes(raw),  # type: ignore[call-overload]
        reason_pt=None if reason_pt is None else str(reason_pt),
    )


# ----------------------------------------------------------------------------- SQL: bruto

SQL_INSERT_SAMPLE: Final[str] = """
INSERT INTO samples (equipment_id, tag, ts_utc_ms, value, quality, source, raw, reason_pt)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (equipment_id, tag, ts_utc_ms) DO UPDATE SET
    value = excluded.value, quality = excluded.quality, source = excluded.source,
    raw = excluded.raw, reason_pt = excluded.reason_pt
"""

SQL_UPSERT_LATEST: Final[str] = """
INSERT INTO samples_latest (equipment_id, tag, ts_utc_ms, value, quality, source, raw, reason_pt)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (equipment_id, tag) DO UPDATE SET
    ts_utc_ms = excluded.ts_utc_ms, value = excluded.value, quality = excluded.quality,
    source = excluded.source, raw = excluded.raw, reason_pt = excluded.reason_pt
WHERE excluded.ts_utc_ms >= samples_latest.ts_utc_ms
"""

SQL_LAST_STORED: Final[str] = """
SELECT ts_utc_ms, value, quality FROM samples
WHERE equipment_id = ? AND tag = ?
ORDER BY ts_utc_ms DESC LIMIT 1
"""

SQL_LATEST_ALL: Final[str] = """
SELECT tag, ts_utc_ms, value, quality, source, raw, reason_pt
FROM samples_latest WHERE equipment_id = ?
"""

SQL_RAW_RANGE: Final[str] = """
SELECT ts_utc_ms, value, quality FROM samples
WHERE equipment_id = ? AND tag = ? AND ts_utc_ms >= ? AND ts_utc_ms <= ?
ORDER BY ts_utc_ms
"""

SQL_COUNT_ALL: Final[str] = "SELECT COUNT(*) FROM samples"
SQL_COUNT_EQ: Final[str] = "SELECT COUNT(*) FROM samples WHERE equipment_id = ?"

SQL_FIRST_SAMPLE_MS: Final[str] = """
SELECT MIN(first_ms) FROM (
    SELECT (SELECT MIN(s.ts_utc_ms) FROM samples s
            WHERE s.equipment_id = l.equipment_id AND s.tag = l.tag) AS first_ms
    FROM samples_latest l
)
"""

SQL_PAIRS: Final[str] = "SELECT equipment_id, tag FROM samples_latest ORDER BY equipment_id, tag"


def sql_latest_tags(n_tags: int) -> str:
    """SELECT de samples_latest restrito a N tags (placeholders posicionais)."""
    marks = ", ".join("?" for _ in range(n_tags))
    return f"{SQL_LATEST_ALL} AND tag IN ({marks})"


# ----------------------------------------------------------------------------- SQL: comm_log

SQL_INSERT_COMM: Final[str] = """
INSERT INTO comm_log (ts_utc_ms, equipment_id, level, kind, message_pt, detail_json)
VALUES (?, ?, ?, ?, ?, ?)
"""


def sql_comm_log(with_equipment: bool, with_since: bool) -> str:
    """SELECT de comm_log, mais recente primeiro, com filtros opcionais."""
    where = ["1 = 1"]
    if with_equipment:
        where.append("equipment_id = ?")
    if with_since:
        where.append("ts_utc_ms >= ?")
    clause = " AND ".join(where)
    select = "SELECT ts_utc_ms, equipment_id, level, kind, message_pt, detail_json FROM comm_log"
    return f"{select} WHERE {clause} ORDER BY ts_utc_ms DESC, id DESC LIMIT ?"


# ----------------------------------------------------------------------------- SQL: marca d'agua

SQL_GET_WATERMARK: Final[str] = "SELECT watermark_ms FROM rollup_state WHERE name = ?"
SQL_SET_WATERMARK: Final[str] = """
INSERT INTO rollup_state (name, watermark_ms) VALUES (?, ?)
ON CONFLICT (name) DO UPDATE SET watermark_ms = excluded.watermark_ms
"""


# ----------------------------------------------------------------------------- buckets


@dataclass(frozen=True, slots=True)
class Bucket:
    """Agregado de um intervalo [start_ms, start_ms + bucket_ms). n=0 e GAP."""

    start_ms: int
    n: int
    n_good: int
    n_comm_error: int
    n_bad: int
    min: float | None
    max: float | None
    avg: float | None
    first: float | None
    last: float | None
    worst_quality: int

    @property
    def is_gap(self) -> bool:
        return self.n == 0


def empty_bucket(start_ms: int) -> Bucket:
    """Bucket sem linha: GAP. Qualidade COMM_ERROR (nada foi lido)."""
    return Bucket(start_ms, 0, 0, 0, 0, None, None, None, None, None, GAP_CODE)


AGG_COLUMNS: Final[str] = (
    "equipment_id, tag, bucket_start_ms, n, n_good, n_comm_error, n_bad, "
    "min, max, avg, first, last, worst_quality"
)

_AGG_TABLES: Final[frozenset[str]] = frozenset({"samples_agg_1m", "samples_agg_1h"})


def _scope_clause(scoped: bool, alias: str) -> str:
    if scoped:
        return f"{alias}.equipment_id = :equipment_id AND {alias}.tag = :tag AND "
    return ""


def _from_clause(table: str, ts_col: str, scoped: bool) -> str:
    """Bruto ou agregado, restrito a um par (PK) ou percorrendo os pares de samples_latest."""
    if scoped:
        return (
            f"FROM {table} s WHERE {_scope_clause(True, 's')}"
            f"s.{ts_col} >= :from_ms AND s.{ts_col} < :until_ms"
        )
    return (
        f"FROM samples_latest l JOIN {table} s "
        f"ON s.equipment_id = l.equipment_id AND s.tag = l.tag "
        f"AND s.{ts_col} >= :from_ms AND s.{ts_col} < :until_ms"
    )


def _final_select(firsts_order: str, lasts_order: str, value_col: str) -> str:
    return f"""
firsts AS (
    SELECT equipment_id, tag, b, {value_col} AS v FROM (
        SELECT equipment_id, tag, b, {value_col},
               ROW_NUMBER() OVER (PARTITION BY equipment_id, tag, b ORDER BY {firsts_order}) AS rn
        FROM base WHERE {value_col} IS NOT NULL
    ) WHERE rn = 1
),
lasts AS (
    SELECT equipment_id, tag, b, {value_col} AS v FROM (
        SELECT equipment_id, tag, b, {value_col},
               ROW_NUMBER() OVER (PARTITION BY equipment_id, tag, b ORDER BY {lasts_order}) AS rn
        FROM base WHERE {value_col} IS NOT NULL
    ) WHERE rn = 1
)
SELECT a.equipment_id, a.tag, a.b, a.n, a.n_good, a.n_comm_error, a.n_bad,
       a.vmin, a.vmax, a.vavg, f.v, l.v, a.worst
FROM agg a
LEFT JOIN firsts f ON f.equipment_id = a.equipment_id AND f.tag = a.tag AND f.b = a.b
LEFT JOIN lasts  l ON l.equipment_id = a.equipment_id AND l.tag = a.tag AND l.b = a.b
WHERE true
"""  # noqa: S608 - identificadores fixos, valores só por parâmetro


def sql_bucket_raw(scoped: bool) -> str:
    """SELECT (AGG_COLUMNS) agregando ``samples`` em buckets de :bucket_ms em [:from_ms, :until_ms).

    Parametros nomeados: bucket_ms, from_ms, until_ms, usable_max, q_comm, q_bad
    e, se ``scoped``, equipment_id e tag.
    """
    return f"""
WITH base AS (
    SELECT s.equipment_id, s.tag, (s.ts_utc_ms / :bucket_ms) * :bucket_ms AS b,
           s.ts_utc_ms, s.quality,
           CASE WHEN s.quality <= :usable_max AND s.value IS NOT NULL THEN s.value END AS v
    {_from_clause("samples", "ts_utc_ms", scoped)}
),
agg AS (
    SELECT equipment_id, tag, b,
           COUNT(*) AS n,
           COALESCE(SUM(v IS NOT NULL), 0) AS n_good,
           COALESCE(SUM(quality = :q_comm), 0) AS n_comm_error,
           COALESCE(SUM(quality = :q_bad), 0) AS n_bad,
           MIN(v) AS vmin, MAX(v) AS vmax, AVG(v) AS vavg,
           MAX(quality) AS worst
    FROM base GROUP BY equipment_id, tag, b
),
{_final_select("ts_utc_ms ASC", "ts_utc_ms DESC", "v")}
"""  # noqa: S608 - identificadores fixos, valores só por parâmetro


def sql_bucket_agg(source: str, scoped: bool) -> str:
    """SELECT (AGG_COLUMNS) re-agregando ``source`` (agg_1m/agg_1h) em buckets de :bucket_ms.

    avg ponderado por n_good; first/last pelo bucket de origem mais antigo/mais novo.
    """
    if source not in _AGG_TABLES:
        raise HistorianError(f"tabela de agregado desconhecida: {source}")
    return f"""
WITH base AS (
    SELECT s.equipment_id, s.tag, (s.bucket_start_ms / :bucket_ms) * :bucket_ms AS b,
           s.bucket_start_ms, s.n, s.n_good, s.n_comm_error, s.n_bad,
           s.min, s.max, s.avg, s.first, s.last, s.worst_quality
    {_from_clause(source, "bucket_start_ms", scoped)}
),
agg AS (
    SELECT equipment_id, tag, b,
           SUM(n) AS n, SUM(n_good) AS n_good,
           SUM(n_comm_error) AS n_comm_error, SUM(n_bad) AS n_bad,
           MIN(min) AS vmin, MAX(max) AS vmax,
           CASE WHEN SUM(n_good) > 0 THEN SUM(avg * n_good) / SUM(n_good) END AS vavg,
           MAX(worst_quality) AS worst
    FROM base GROUP BY equipment_id, tag, b
),
firsts AS (
    SELECT equipment_id, tag, b, first AS v FROM (
        SELECT equipment_id, tag, b, first,
               ROW_NUMBER() OVER (
                   PARTITION BY equipment_id, tag, b ORDER BY bucket_start_ms ASC
               ) AS rn
        FROM base WHERE first IS NOT NULL
    ) WHERE rn = 1
),
lasts AS (
    SELECT equipment_id, tag, b, last AS v FROM (
        SELECT equipment_id, tag, b, last,
               ROW_NUMBER() OVER (
                   PARTITION BY equipment_id, tag, b ORDER BY bucket_start_ms DESC
               ) AS rn
        FROM base WHERE last IS NOT NULL
    ) WHERE rn = 1
)
SELECT a.equipment_id, a.tag, a.b, a.n, a.n_good, a.n_comm_error, a.n_bad,
       a.vmin, a.vmax, a.vavg, f.v, l.v, a.worst
FROM agg a
LEFT JOIN firsts f ON f.equipment_id = a.equipment_id AND f.tag = a.tag AND f.b = a.b
LEFT JOIN lasts  l ON l.equipment_id = a.equipment_id AND l.tag = a.tag AND l.b = a.b
WHERE true
"""  # noqa: S608 - identificadores de allowlist, valores só por parâmetro


def sql_rollup_insert(target: str, select_sql: str) -> str:
    """INSERT ... SELECT ... ON CONFLICT que atualiza o bucket (recalculo idempotente)."""
    if target not in _AGG_TABLES:
        raise HistorianError(f"tabela de agregado desconhecida: {target}")
    return f"""
INSERT INTO {target} ({AGG_COLUMNS})
{select_sql}
ON CONFLICT (equipment_id, tag, bucket_start_ms) DO UPDATE SET
    n = excluded.n, n_good = excluded.n_good, n_comm_error = excluded.n_comm_error,
    n_bad = excluded.n_bad, min = excluded.min, max = excluded.max, avg = excluded.avg,
    first = excluded.first, last = excluded.last, worst_quality = excluded.worst_quality
"""


def sql_agg_range(table: str) -> str:
    """Leitura direta de buckets ja consolidados de um par, em [from, until)."""
    if table not in _AGG_TABLES:
        raise HistorianError(f"tabela de agregado desconhecida: {table}")
    return (
        f"SELECT {AGG_COLUMNS} FROM {table} "  # noqa: S608 - identificadores de allowlist
        "WHERE equipment_id = ? AND tag = ? AND bucket_start_ms >= ? AND bucket_start_ms < ? "
        "ORDER BY bucket_start_ms"
    )


def bucket_params(
    bucket_ms: int,
    from_ms: int,
    until_ms: int,
    equipment_id: str | None = None,
    tag: str | None = None,
) -> dict[str, int | str | None]:
    """Parametros nomeados das consultas de bucket."""
    return {
        "bucket_ms": bucket_ms,
        "from_ms": from_ms,
        "until_ms": until_ms,
        "usable_max": USABLE_MAX_CODE,
        "q_comm": QUALITY_CODE[Quality.COMM_ERROR],
        "q_bad": QUALITY_CODE[Quality.BAD],
        "equipment_id": equipment_id,
        "tag": tag,
    }


def bucket_from_row(row: Sequence[object]) -> tuple[str, str, Bucket]:
    """Linha no formato AGG_COLUMNS -> (equipment_id, tag, Bucket)."""
    eq, tag, b, n, n_good, n_comm, n_bad, vmin, vmax, vavg, first, last, worst = row
    return (
        str(eq),
        str(tag),
        Bucket(
            start_ms=_as_int(b),
            n=_as_int(n),
            n_good=_as_int(n_good),
            n_comm_error=_as_int(n_comm),
            n_bad=_as_int(n_bad),
            min=_opt_float(vmin),
            max=_opt_float(vmax),
            avg=_opt_float(vavg),
            first=_opt_float(first),
            last=_opt_float(last),
            worst_quality=_as_int(worst),
        ),
    )


def _opt_float(value: object) -> float | None:
    return None if value is None else _as_float(value)


def combine_buckets(parts: Sequence[Bucket], start_ms: int) -> Bucket:
    """Funde buckets em um so. Partes vazias nao contam para a pior qualidade:
    GAP e so quando o conjunto inteiro nao tem linha."""
    filled = [p for p in parts if p.n > 0]
    if not filled:
        return empty_bucket(start_ms)
    n_good = sum(p.n_good for p in filled)
    weighted = [p.avg * p.n_good for p in filled if p.avg is not None and p.n_good > 0]
    mins = [p.min for p in filled if p.min is not None]
    maxs = [p.max for p in filled if p.max is not None]
    firsts = [p.first for p in filled if p.first is not None]
    lasts = [p.last for p in filled if p.last is not None]
    return Bucket(
        start_ms=start_ms,
        n=sum(p.n for p in filled),
        n_good=n_good,
        n_comm_error=sum(p.n_comm_error for p in filled),
        n_bad=sum(p.n_bad for p in filled),
        min=min(mins) if mins else None,
        max=max(maxs) if maxs else None,
        avg=(sum(weighted) / n_good) if n_good > 0 and weighted else None,
        first=firsts[0] if firsts else None,
        last=lasts[-1] if lasts else None,
        worst_quality=max(p.worst_quality for p in filled),
    )


def bucket_span(start_ms: int, end_ms: int, bucket_ms: int) -> tuple[int, int]:
    """[inicio do bucket de start, fim exclusivo do bucket de end)."""
    return floor_ms(start_ms, bucket_ms), floor_ms(end_ms, bucket_ms) + bucket_ms


def fill_buckets(
    found: Mapping[int, Bucket], first_ms: int, until_ms: int, bucket_ms: int
) -> list[Bucket]:
    """Lista densa: um bucket por intervalo; ausente vira GAP (nunca interpolado)."""
    return [found.get(b) or empty_bucket(b) for b in range(first_ms, until_ms, bucket_ms)]


def merge_buckets(dense: Sequence[Bucket], bucket_ms: int, k: int) -> list[Bucket]:
    """Re-bucket: funde k buckets vizinhos alinhados em um de k*bucket_ms."""
    if k <= 1:
        return list(dense)
    wide = bucket_ms * k
    groups: dict[int, list[Bucket]] = {}
    for b in dense:
        groups.setdefault(floor_ms(b.start_ms, wide), []).append(b)
    return [combine_buckets(parts, start) for start, parts in sorted(groups.items())]


def index_by_start(parts: Iterable[Bucket]) -> dict[int, Bucket]:
    """Agrupa por start_ms fundindo repetidos (mesmo bucket vindo de duas fontes)."""
    by_start: dict[int, list[Bucket]] = {}
    for b in parts:
        by_start.setdefault(b.start_ms, []).append(b)
    return {
        s: (lst[0] if len(lst) == 1 else combine_buckets(lst, s)) for s, lst in by_start.items()
    }


def bucket_to_point(b: Bucket) -> SeriesPoint:
    """Bucket -> ponto de serie. value = avg (None em GAP ou so COMM_ERROR)."""
    return SeriesPoint(
        ts_utc=from_ms(b.start_ms),
        value=b.avg,
        quality=code_to_quality(b.worst_quality),
        min=b.min,
        max=b.max,
        n=b.n,
    )


def gap_point(ts_ms: int) -> SeriesPoint:
    """Ponto GAP sintetico (n=0): nao houve leitura."""
    return SeriesPoint(ts_utc=from_ms(ts_ms), value=None, quality=Quality.COMM_ERROR, n=0)


# ----------------------------------------------------------------------------- resolucao


def choose_resolution(window_s: float, max_points: int) -> Resolution:
    """raw se a janela cabe em max_points segundos; 1m se cabe em minutos; senao 1h."""
    if window_s <= max_points:
        return "raw"
    if window_s / 60 <= max_points:
        return "1m"
    return "1h"


def raw_points(
    rows: Sequence[Sequence[object]], start_ms: int, end_ms: int, gap_threshold_ms: int
) -> list[SeriesPoint]:
    """Pontos brutos em ordem, com GAP sintetico onde o buraco passa do limiar.

    Linhas COMM_ERROR ja vem com value None (n=1). O GAP (n=0) entra no inicio, no fim e
    entre vizinhos quando a distancia supera ``gap_threshold_ms``. Nada e interpolado.
    """
    if not rows:
        return [gap_point(start_ms)]
    points: list[SeriesPoint] = []
    first_ts = _as_int(rows[0][0])
    if first_ts - start_ms > gap_threshold_ms:
        points.append(gap_point(start_ms))
    prev_ts: int | None = None
    for ts, value, quality in rows:
        ts_i = _as_int(ts)
        if prev_ts is not None and ts_i - prev_ts > gap_threshold_ms:
            points.append(gap_point(prev_ts + gap_threshold_ms))
        points.append(
            SeriesPoint(
                ts_utc=from_ms(ts_i),
                value=None if value is None else _as_float(value),
                quality=code_to_quality(_as_int(quality)),
                n=1,
            )
        )
        prev_ts = ts_i
    if prev_ts is not None and end_ms - prev_ts > gap_threshold_ms:
        points.append(gap_point(prev_ts + gap_threshold_ms))
    return points
