"""Escritor unico: uma thread, uma conexao, uma fila. Mais o filtro store-on-change.

Por que uma thread propria e nao ``asyncio.to_thread``: a conexao de escrita pertence a uma
unica thread do inicio ao fim (check_same_thread padrao), sem lock compartilhado e sem
surpresa de pool. O resultado volta ao loop asyncio por ``call_soon_threadsafe``.
Leitores usam conexao propria (``connect_ro``), aberta por chamada.
"""

from __future__ import annotations

import asyncio
import logging
import queue
import sqlite3
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import quote

from forja.domain.errors import HistorianError
from forja.domain.quality import Quality
from forja.domain.samples import Sample
from forja.domain.tags import TAGS
from forja.historian.queries import (
    SQL_INSERT_SAMPLE,
    SQL_LAST_STORED,
    SQL_UPSERT_LATEST,
    quality_to_code,
    to_ms,
)

log = logging.getLogger("forja.historian")

T = TypeVar("T")
_STOP = object()
BUSY_TIMEOUT_MS = 10_000


# ----------------------------------------------------------------------------- conexoes


def connect_rw(path: Path, *, foreign_keys: bool = False) -> sqlite3.Connection:
    """Conexao de escrita: WAL, synchronous=NORMAL, autocommit explicito."""
    conn = sqlite3.connect(path, timeout=BUSY_TIMEOUT_MS / 1000, autocommit=True)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute("PRAGMA foreign_keys = " + ("ON" if foreign_keys else "OFF"))
    return conn


def connect_ro(path: Path) -> sqlite3.Connection:
    """Conexao de leitura: query_only, o SQLite recusa qualquer escrita por ela."""
    if not path.exists():
        raise HistorianError(f"banco não encontrado: {path}")
    conn = sqlite3.connect(path, timeout=BUSY_TIMEOUT_MS / 1000, autocommit=True)
    conn.execute("PRAGMA query_only = 1")
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    return conn


def connect_immutable(path: Path) -> sqlite3.Connection:
    """Abre um arquivo parado (backup) como somente leitura, sem criar -wal/-shm ao lado."""
    if not path.is_file():
        raise HistorianError(f"arquivo não encontrado: {path}")
    uri = "file:///" + quote(path.resolve().as_posix(), safe="/:") + "?mode=ro&immutable=1"
    return sqlite3.connect(uri, uri=True)


# ----------------------------------------------------------------------------- arquivos


def timestamp_label(when: datetime) -> str:
    """2026-01-01T12:00:00Z -> 20260101T120000Z (nome de arquivo)."""
    return when.strftime("%Y%m%dT%H%M%SZ")


def unique_path(directory: Path, name: str) -> Path:
    """``name`` dentro de ``directory``; se ja existir, acrescenta _1, _2, ... antes do sufixo."""
    candidate = directory / name
    stem, suffix = candidate.stem, candidate.suffix
    counter = 1
    while candidate.exists():
        candidate = directory / f"{stem}_{counter}{suffix}"
        counter += 1
    return candidate


# ----------------------------------------------------------------------------- thread escritora


@dataclass(slots=True)
class _Job:
    fn: Callable[[sqlite3.Connection], Any]
    future: asyncio.Future[Any]
    loop: asyncio.AbstractEventLoop


class SqliteWriter:
    """Thread dona da conexao de escrita. ``submit`` enfileira e aguarda o resultado."""

    def __init__(self, connect: Callable[[], sqlite3.Connection], name: str) -> None:
        self._connect = connect
        self._name = name
        self._queue: queue.Queue[_Job | object] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._start_error: BaseException | None = None
        self._closed = False

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and not self._closed

    async def start(self) -> None:
        """Sobe a thread, abre a conexao dentro dela e espera ficar pronta."""
        if self._thread is not None:
            raise HistorianError(f"escritor {self._name} já iniciado")
        self._thread = threading.Thread(target=self._run, name=f"forja-{self._name}", daemon=True)
        self._thread.start()
        await asyncio.to_thread(self._ready.wait)
        if self._start_error is not None:
            raise HistorianError(
                f"falha ao abrir banco ({self._name}): {self._start_error}"
            ) from self._start_error

    async def submit(self, fn: Callable[[sqlite3.Connection], T]) -> T:
        """Executa ``fn(conn)`` na thread escritora e devolve o resultado."""
        if not self.is_running:
            raise HistorianError(f"escritor {self._name} não está aberto")
        loop = asyncio.get_running_loop()
        future: asyncio.Future[T] = loop.create_future()
        self._queue.put(_Job(fn, future, loop))
        return await future

    async def close(self) -> None:
        """Encerra a fila, fecha a conexao e espera a thread terminar."""
        if self._thread is None or self._closed:
            return
        self._closed = True
        self._queue.put(_STOP)
        await asyncio.to_thread(self._thread.join)

    # --- lado da thread -------------------------------------------------------

    def _run(self) -> None:
        try:
            conn = self._connect()
        except BaseException as exc:  # reportado ao start()
            self._start_error = exc
            self._ready.set()
            return
        self._ready.set()
        try:
            while True:
                item = self._queue.get()
                if item is _STOP:
                    break
                self._execute(conn, item)  # type: ignore[arg-type]
        finally:
            self._drain()
            try:
                conn.execute("PRAGMA optimize")
            except sqlite3.Error:  # pragma: no cover - otimizacao e melhor esforco
                log.debug("PRAGMA optimize falhou em %s", self._name, exc_info=True)
            conn.close()

    @staticmethod
    def _execute(conn: sqlite3.Connection, job: _Job) -> None:
        try:
            result = job.fn(conn)
        except BaseException as exc:  # devolvido ao chamador
            job.loop.call_soon_threadsafe(_fail, job.future, exc)
            return
        job.loop.call_soon_threadsafe(_resolve, job.future, result)

    def _drain(self) -> None:
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                return
            if isinstance(item, _Job):
                item.loop.call_soon_threadsafe(
                    _fail, item.future, HistorianError(f"escritor {self._name} fechado")
                )


def _resolve(future: asyncio.Future[Any], result: Any) -> None:
    if not future.done():
        future.set_result(result)


def _fail(future: asyncio.Future[Any], exc: BaseException) -> None:
    if not future.done():
        future.set_exception(exc)


# ----------------------------------------------------------------------------- store-on-change


@dataclass(frozen=True, slots=True)
class LastStored:
    """Ultima linha gravada de um par (equipment_id, tag)."""

    ts_ms: int
    value: float | None
    quality: int


def default_deadband(tag: str) -> float:
    """Metade do ultimo digito exibido da tag (TAGS.decimals). Tag desconhecida: 0 (grava tudo).

    Mudanca que nao altera o valor exibido nao gera linha. Nao e limite de processo:
    e resolucao de exibicao, e vale igual para qualquer equipamento.
    """
    tag_def = TAGS.get(tag)
    if tag_def is None:
        return 0.0
    return 0.5 * (10.0 ** (-tag_def.decimals))


def should_store(
    last: LastStored | None,
    ts_ms: int,
    value: float | None,
    quality: int,
    deadband: float,
    forced_every_ms: int,
) -> bool:
    """Decide se a amostra vira linha. Grava quando: primeira do par; qualidade mudou;
    valor apareceu/sumiu; |delta| > deadband; passou o intervalo forcado; ou ts voltou no tempo."""
    if last is None:
        return True
    if quality != last.quality:
        return True
    if ts_ms < last.ts_ms or ts_ms - last.ts_ms >= forced_every_ms:
        return True
    if (value is None) != (last.value is None):
        return True
    if value is None or last.value is None:
        return False
    return abs(value - last.value) > deadband


class ChangeFilter:
    """Estado do store-on-change por par. So e tocado na thread escritora."""

    def __init__(
        self,
        enabled: bool,
        forced_every_s: int,
        deadband: Callable[[str], float] = default_deadband,
    ) -> None:
        self.enabled = enabled
        self.forced_every_ms = max(1, int(forced_every_s)) * 1000
        self._deadband = deadband
        self._last: dict[tuple[str, str], LastStored] = {}

    def decide(
        self,
        conn: sqlite3.Connection,
        key: tuple[str, str],
        ts_ms: int,
        value: float | None,
        quality: int,
    ) -> bool:
        if not self.enabled:
            return True
        last = self._last.get(key)
        if last is None:
            last = _load_last(conn, key)
        return should_store(
            last, ts_ms, value, quality, self._deadband(key[1]), self.forced_every_ms
        )

    def mark_stored(
        self, key: tuple[str, str], ts_ms: int, value: float | None, quality: int
    ) -> None:
        self._last[key] = LastStored(ts_ms, value, quality)

    def forget(self) -> None:
        self._last.clear()


def _load_last(conn: sqlite3.Connection, key: tuple[str, str]) -> LastStored | None:
    row = conn.execute(SQL_LAST_STORED, key).fetchone()
    if row is None:
        return None
    ts, value, quality = row
    return LastStored(int(ts), None if value is None else float(value), int(quality))


# ----------------------------------------------------------------------------- escrita de lote


def write_batch(conn: sqlite3.Connection, samples: Sequence[Sample], filt: ChangeFilter) -> int:
    """Grava um lote em uma transacao. Devolve linhas gravadas em ``samples``.

    - STALE nunca vira linha nem atualiza samples_latest (e estado derivado, nao leitura);
    - COMM_ERROR grava value NULL mesmo que a amostra traga numero;
    - samples_latest recebe toda leitura; samples so o que o store-on-change deixa passar.
    """
    stored = 0
    conn.execute("BEGIN IMMEDIATE")
    try:
        for s in samples:
            if s.quality is Quality.STALE:
                continue
            key = (s.equipment_id, s.tag)
            ts_ms = to_ms(s.ts_utc)
            q = quality_to_code(s.quality)
            value = None if s.quality is Quality.COMM_ERROR else s.value
            params = (s.equipment_id, s.tag, ts_ms, value, q, s.source, s.raw, s.reason_pt)
            conn.execute(SQL_UPSERT_LATEST, params)
            if filt.decide(conn, key, ts_ms, value, q):
                conn.execute(SQL_INSERT_SAMPLE, params)
                filt.mark_stored(key, ts_ms, value, q)
                stored += 1
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return stored
