"""SqliteHistorian: implementacao SQLite da porta ``HistorianRepository``.

Desenho:
- uma thread escritora (``SqliteWriter``) e dona da unica conexao de escrita; tudo que grava
  (write, log_comm, rollups, retencao, backup) passa por ela, em ordem;
- leituras abrem conexao propria ``query_only`` por chamada, em ``asyncio.to_thread``;
- tempo no banco e INTEGER epoch ms UTC; relogio so via a porta ``Clock``;
- STALE nunca vira linha (e estado derivado); COMM_ERROR grava value NULL;
- ``range`` escolhe raw | 1m | 1h pelo tamanho da janela e pelo orcamento de pontos, completa
  buckets vazios com GAP (value None, n=0) e nunca interpola. A cauda ainda nao consolidada pelos
  rollups e calculada ao vivo a partir do bruto, entao a serie e completa em qualquer momento.
"""

from __future__ import annotations

import asyncio
import json
import math
import sqlite3
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Final, TypeVar

from forja.config.models import HistorianConfig
from forja.domain.errors import HistorianError
from forja.domain.ports import Clock, CommLogEntry, Series, SeriesPoint
from forja.domain.samples import Sample
from forja.historian import queries as q
from forja.historian.migrate import MIGRATIONS_DIR, migrate
from forja.historian.retention import run_retention as _retention
from forja.historian.rollups import WATERMARK_1H, WATERMARK_1M, get_watermark
from forja.historian.rollups import run_rollups as _rollups
from forja.historian.writer import (
    ChangeFilter,
    SqliteWriter,
    connect_ro,
    connect_rw,
    timestamp_label,
    unique_path,
    write_batch,
)

T = TypeVar("T")

HISTORIAN_TABLES: Final[tuple[str, ...]] = (
    "samples",
    "samples_latest",
    "samples_agg_1m",
    "samples_agg_1h",
    "comm_log",
)
BACKUP_PAGES: Final[int] = 1024
"""Paginas por passo do Connection.backup(): a escrita ao vivo entra entre os passos."""

_AGG_NATIVE_MS: Final[dict[str, int]] = {
    "samples_agg_1m": q.MINUTE_MS,
    "samples_agg_1h": q.HOUR_MS,
}


class SqliteHistorian:
    """Historian em ``forja_historian.db``. Implementa ``HistorianRepository``."""

    def __init__(self, db_path: Path, config: HistorianConfig, clock: Clock) -> None:
        self._path = Path(db_path)
        self._config = config
        self._clock = clock
        self._writer: SqliteWriter | None = None
        self._filter = ChangeFilter(config.store_on_change, config.forced_sample_every_s)

    # ------------------------------------------------------------------ ciclo de vida

    @property
    def db_path(self) -> Path:
        return self._path

    @property
    def config(self) -> HistorianConfig:
        return self._config

    @property
    def clock(self) -> Clock:
        return self._clock

    @property
    def is_open(self) -> bool:
        return self._writer is not None and self._writer.is_running

    async def open(self) -> None:
        """Abre (ou cria) o banco, aplica migracoes pendentes e sobe a thread escritora."""
        if self._writer is not None:
            raise HistorianError("historian já aberto")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        now_ms = q.to_ms(self._clock.now_utc())
        path = self._path

        def connect() -> sqlite3.Connection:
            conn = connect_rw(path)
            try:
                migrate(conn, MIGRATIONS_DIR, "historian", now_ms=now_ms)
            except Exception:
                conn.close()
                raise
            return conn

        writer = SqliteWriter(connect, "historian")
        await writer.start()
        self._writer = writer
        self._filter.forget()

    async def close(self) -> None:
        """Fecha a conexao escritora. Idempotente."""
        writer, self._writer = self._writer, None
        if writer is not None:
            await writer.close()
        self._filter.forget()

    def _writer_or_raise(self) -> SqliteWriter:
        if self._writer is None or not self._writer.is_running:
            raise HistorianError("historian não está aberto")
        return self._writer

    async def _read(self, fn: Callable[[sqlite3.Connection], T]) -> T:
        """Executa ``fn`` numa conexao somente leitura, fora do loop."""
        self._writer_or_raise()
        path = self._path

        def run() -> T:
            conn = connect_ro(path)
            try:
                return fn(conn)
            finally:
                conn.close()

        return await asyncio.to_thread(run)

    # ------------------------------------------------------------------ escrita

    async def write(self, samples: Sequence[Sample]) -> None:
        """Grava um lote. STALE e ignorado; COMM_ERROR vira value NULL; store-on-change opcional."""
        batch = tuple(samples)
        if not batch:
            return
        filt = self._filter
        await self._writer_or_raise().submit(lambda conn: write_batch(conn, batch, filt))

    async def log_comm(self, entry: CommLogEntry) -> None:
        params = (
            q.to_ms(entry.ts_utc),
            entry.equipment_id,
            entry.level,
            entry.kind,
            entry.message_pt,
            json.dumps(entry.detail, ensure_ascii=False, default=str),
        )

        def run(conn: sqlite3.Connection) -> None:
            conn.execute(q.SQL_INSERT_COMM, params)

        await self._writer_or_raise().submit(run)

    async def run_rollups(self) -> dict[str, int]:
        """agg_1m a partir do bruto (minutos fechados), agg_1h a partir de agg_1m."""
        now_ms = q.to_ms(self._clock.now_utc())
        return await self._writer_or_raise().submit(lambda conn: _rollups(conn, now_ms))

    async def run_retention(self) -> dict[str, int]:
        """Apaga so o que passou do prazo; nunca bruto acima da marca d'agua de agregacao."""
        now_ms = q.to_ms(self._clock.now_utc())
        config = self._config
        return await self._writer_or_raise().submit(lambda conn: _retention(conn, config, now_ms))

    async def backup(self, dest_dir: Path) -> Path:
        """Copia consistente via ``Connection.backup()`` paginado. Devolve o arquivo criado."""
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        label = timestamp_label(self._clock.now_utc())
        target = unique_path(dest, f"forja_historian_{label}.db")

        def run(conn: sqlite3.Connection) -> Path:
            dst = sqlite3.connect(target)
            try:
                conn.backup(dst, pages=BACKUP_PAGES)
            finally:
                dst.close()
            return target

        return await self._writer_or_raise().submit(run)

    # ------------------------------------------------------------------ leitura

    async def latest(
        self, equipment_id: str, tags: Sequence[str] | None = None
    ) -> dict[str, Sample]:
        """Ultima leitura observada por tag (mesmo quando o store-on-change nao gravou linha)."""
        wanted = None if tags is None else list(dict.fromkeys(tags))
        if wanted is not None and not wanted:
            return {}

        def run(conn: sqlite3.Connection) -> dict[str, Sample]:
            if wanted is None:
                rows = conn.execute(q.SQL_LATEST_ALL, (equipment_id,)).fetchall()
            else:
                rows = conn.execute(
                    q.sql_latest_tags(len(wanted)), (equipment_id, *wanted)
                ).fetchall()
            out: dict[str, Sample] = {}
            for row in rows:
                sample = q.sample_from_row(equipment_id, row)
                out[sample.tag] = sample
            return out

        return await self._read(run)

    async def count(self, equipment_id: str | None = None) -> int:
        def run(conn: sqlite3.Connection) -> int:
            if equipment_id is None:
                row = conn.execute(q.SQL_COUNT_ALL).fetchone()
            else:
                row = conn.execute(q.SQL_COUNT_EQ, (equipment_id,)).fetchone()
            return int(row[0]) if row is not None else 0

        return await self._read(run)

    async def comm_log(
        self, equipment_id: str | None, since: datetime | None, limit: int = 200
    ) -> list[CommLogEntry]:
        params: list[object] = []
        if equipment_id is not None:
            params.append(equipment_id)
        if since is not None:
            params.append(q.to_ms(since))
        params.append(max(1, int(limit)))
        sql = q.sql_comm_log(equipment_id is not None, since is not None)

        def run(conn: sqlite3.Connection) -> list[CommLogEntry]:
            rows = conn.execute(sql, params).fetchall()
            return [_comm_entry_from_row(row) for row in rows]

        return await self._read(run)

    async def range(
        self,
        equipment_id: str,
        tag: str,
        start: datetime,
        end: datetime,
        max_points: int = 2000,
    ) -> Series:
        """Serie para grafico. Resolucao pela janela e pelo orcamento; GAP onde nao houve leitura.

        ``max_points`` e limitado por ``HistorianConfig.max_points_per_query``.
        """
        start_ms, end_ms = q.to_ms(start), q.to_ms(end)
        if end_ms < start_ms:
            raise HistorianError("intervalo inválido: fim antes do início")
        budget = max(1, min(int(max_points), self._config.max_points_per_query))
        window_s = (end_ms - start_ms) / 1000
        resolution = q.choose_resolution(window_s, budget)
        gap_ms = self.gap_threshold_ms

        def run(conn: sqlite3.Connection) -> Series:
            if resolution == "raw":
                return _range_raw(conn, equipment_id, tag, start_ms, end_ms, budget, gap_ms)
            return _range_agg(conn, equipment_id, tag, start_ms, end_ms, budget, resolution)

        return await self._read(run)

    @property
    def gap_threshold_ms(self) -> int:
        """Buraco no bruto maior que isto vira GAP: 2x o intervalo de amostra forcada."""
        return max(2, 2 * int(self._config.forced_sample_every_s)) * 1000

    async def stats(self) -> dict[str, Any]:
        """Tamanho, linhas por tabela, ultima amostra, marcas d'agua, versao do schema."""
        path = self._path
        config = self._config

        def run(conn: sqlite3.Connection) -> dict[str, Any]:
            page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
            page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
            rows = {t: _count_table(conn, t) for t in HISTORIAN_TABLES}
            last = conn.execute("SELECT MAX(ts_utc_ms) FROM samples_latest").fetchone()[0]
            version = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
            wm_1m = get_watermark(conn, WATERMARK_1M)
            wm_1h = get_watermark(conn, WATERMARK_1H)
            size = path.stat().st_size if path.exists() else 0
            wal = Path(str(path) + "-wal")
            if wal.exists():
                size += wal.stat().st_size
            return {
                "db_path": str(path),
                "size_bytes": size,
                "page_size": page_size,
                "page_count": page_count,
                "rows": rows,
                "last_sample_utc": _iso_or_none(last),
                "watermark_1m_utc": _iso_or_none(wm_1m),
                "watermark_1h_utc": _iso_or_none(wm_1h),
                "schema_version": int(version) if version is not None else 0,
                "sqlite_version": sqlite3.sqlite_version,
                "store_on_change": config.store_on_change,
                "forced_sample_every_s": config.forced_sample_every_s,
            }

        return await self._read(run)


# ----------------------------------------------------------------------------- helpers de leitura


def _count_table(conn: sqlite3.Connection, table: str) -> int:
    if table not in HISTORIAN_TABLES:
        raise HistorianError(f"tabela desconhecida: {table}")
    row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()  # noqa: S608 - allowlist
    return int(row[0]) if row is not None else 0


def _iso_or_none(ms: object) -> str | None:
    return None if ms is None else q.from_ms(int(ms)).isoformat()  # type: ignore[call-overload]


def _comm_entry_from_row(row: Sequence[object]) -> CommLogEntry:
    ts, eq, level, kind, message, detail = row
    parsed: dict[str, Any] = {}
    if detail:
        loaded = json.loads(str(detail))
        if isinstance(loaded, dict):
            parsed = loaded
    return CommLogEntry(
        ts_utc=q.from_ms(int(ts)),  # type: ignore[call-overload]
        equipment_id=str(eq),
        level=str(level),
        kind=str(kind),
        message_pt=str(message),
        detail=parsed,
    )


def _series(
    equipment_id: str,
    tag: str,
    resolution: str,
    bucket_s: int,
    points: Sequence[SeriesPoint],
    *,
    downsampled: bool,
) -> Series:
    """gap_count = pontos sem valor (buckets vazios e linhas COMM_ERROR). stale_count e sempre 0:
    STALE nunca e gravado."""
    return Series(
        equipment_id=equipment_id,
        tag=tag,
        resolution=resolution,
        bucket_s=bucket_s,
        points=tuple(points),
        gap_count=sum(1 for p in points if p.value is None),
        stale_count=0,
        downsampled=downsampled,
    )


def _buckets_from_raw(
    conn: sqlite3.Connection,
    equipment_id: str,
    tag: str,
    bucket_ms: int,
    from_ms: int,
    until_ms: int,
) -> list[q.Bucket]:
    """Agrega o bruto de um par em buckets de ``bucket_ms`` dentro de [from_ms, until_ms)."""
    if from_ms >= until_ms:
        return []
    rows = conn.execute(
        q.sql_bucket_raw(scoped=True),
        q.bucket_params(bucket_ms, from_ms, until_ms, equipment_id, tag),
    ).fetchall()
    return [q.bucket_from_row(r)[2] for r in rows]


def _buckets_from_agg(
    conn: sqlite3.Connection,
    table: str,
    equipment_id: str,
    tag: str,
    bucket_ms: int,
    from_ms: int,
    until_ms: int,
) -> list[q.Bucket]:
    """Le buckets consolidados de ``table``; re-agrega se o bucket pedido for maior que o nativo."""
    if from_ms >= until_ms:
        return []
    native = _AGG_NATIVE_MS[table]
    if bucket_ms == native:
        rows = conn.execute(
            q.sql_agg_range(table), (equipment_id, tag, from_ms, until_ms)
        ).fetchall()
    else:
        rows = conn.execute(
            q.sql_bucket_agg(table, scoped=True),
            q.bucket_params(bucket_ms, from_ms, until_ms, equipment_id, tag),
        ).fetchall()
    return [q.bucket_from_row(r)[2] for r in rows]


def _range_raw(
    conn: sqlite3.Connection,
    equipment_id: str,
    tag: str,
    start_ms: int,
    end_ms: int,
    budget: int,
    gap_ms: int,
) -> Series:
    """Bruto ponto a ponto; se estourar o orcamento, re-bucket em N segundos (nunca interpola)."""
    rows = conn.execute(q.SQL_RAW_RANGE, (equipment_id, tag, start_ms, end_ms)).fetchall()
    if len(rows) <= budget:
        points = q.raw_points(rows, start_ms, end_ms, gap_ms)
        return _series(equipment_id, tag, "raw", 0, points, downsampled=False)
    bucket_s = max(1, math.ceil(((end_ms - start_ms) / 1000) / budget))
    bucket_ms = bucket_s * 1000
    from_ms, until_ms = q.bucket_span(start_ms, end_ms, bucket_ms)
    found = q.index_by_start(
        _buckets_from_raw(conn, equipment_id, tag, bucket_ms, from_ms, until_ms)
    )
    dense = q.fill_buckets(found, from_ms, until_ms, bucket_ms)
    points = [q.bucket_to_point(b) for b in dense]
    return _series(equipment_id, tag, f"{bucket_s}s", bucket_s, points, downsampled=True)


def _range_agg(
    conn: sqlite3.Connection,
    equipment_id: str,
    tag: str,
    start_ms: int,
    end_ms: int,
    budget: int,
    resolution: str,
) -> Series:
    """1m ou 1h: consolidado ate a marca d'agua + cauda ao vivo do nivel abaixo; GAP onde vazio.

    As partes sao coletadas em ordem cronologica (1h, 1m, bruto) e fundidas por bucket, porque a
    marca d'agua de 1m pode cair no meio de uma hora: aquela hora recebe metade de agg_1m e
    metade do bruto. Nada e interpolado: bucket sem linha vira GAP.
    """
    native_ms = q.MINUTE_MS if resolution == "1m" else q.HOUR_MS
    from_ms, until_ms = q.bucket_span(start_ms, end_ms, native_ms)
    wm_1m = get_watermark(conn, WATERMARK_1M)
    wm_1h = get_watermark(conn, WATERMARK_1H)
    cut_1m = from_ms if wm_1m is None else wm_1m
    cut_1h = from_ms if wm_1h is None else wm_1h

    parts: list[q.Bucket] = []
    if resolution == "1m":
        parts += _buckets_from_agg(
            conn, "samples_agg_1m", equipment_id, tag, native_ms, from_ms, min(cut_1m, until_ms)
        )
    else:
        parts += _buckets_from_agg(
            conn, "samples_agg_1h", equipment_id, tag, native_ms, from_ms, min(cut_1h, until_ms)
        )
        parts += _buckets_from_agg(
            conn,
            "samples_agg_1m",
            equipment_id,
            tag,
            native_ms,
            max(cut_1h, from_ms),
            min(cut_1m, until_ms),
        )
    parts += _buckets_from_raw(conn, equipment_id, tag, native_ms, max(cut_1m, from_ms), until_ms)

    dense = q.fill_buckets(q.index_by_start(parts), from_ms, until_ms, native_ms)
    k = max(1, math.ceil(len(dense) / budget))
    if k > 1:
        dense = q.merge_buckets(dense, native_ms, k)
    bucket_s = (native_ms // 1000) * k
    label = resolution if k == 1 else f"{bucket_s}s"
    points = [q.bucket_to_point(b) for b in dense]
    return _series(equipment_id, tag, label, bucket_s, points, downsampled=True)
