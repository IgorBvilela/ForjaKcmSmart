"""Historian local.

Esquema único para duas engines: SQLite no notebook (padrão) e
PostgreSQL + TimescaleDB no Edge permanente (mesmas tabelas; hypertable
criada por migração futura). A camada de acesso esconde a engine.

Regras (A–T seção H): escrita em lote; amostra nunca sobrescrita nem apagada;
`value_text` guarda status crus e enumerações, nunca convertidos.

Três tabelas, três fatos diferentes:
    sample      -> "o valor da tag X neste instante era V" (pode ser STALE)
    read_error  -> "a tentativa de ler a tag X falhou neste instante"
    event       -> "o motor de regras reconheceu uma condição entre t0 e t1"
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (JSON, Column, DateTime, Float, Index, Integer, String,
                        create_engine, func, select, update)
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from forja.domain.models import DataSource, Quality, ReadError, Sample


class Base(DeclarativeBase):
    pass


class SampleRow(Base):
    __tablename__ = "sample"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime(timezone=True), nullable=False)
    equipment_id = Column(String(64), nullable=False)
    tag = Column(String(64), nullable=False)
    value_num = Column(Float, nullable=True)
    value_text = Column(String(128), nullable=True)
    quality = Column(String(16), nullable=False)
    source = Column(String(32), nullable=False)
    # instante da leitura boa que originou o valor; só preenchido quando STALE
    source_ts = Column(DateTime(timezone=True), nullable=True)
    __table_args__ = (Index("ix_sample_eq_tag_ts", "equipment_id", "tag", "ts"),)


class ReadErrorRow(Base):
    """Falha de aquisição. Nunca é valor de tag: é registro de tentativa.

    Separada de `sample` de propósito — ver ReadError no domínio.
    """
    __tablename__ = "read_error"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime(timezone=True), nullable=False)
    equipment_id = Column(String(64), nullable=False)
    tag = Column(String(64), nullable=False)
    source = Column(String(32), nullable=False)
    quality = Column(String(16), nullable=False)       # sempre COMM_ERROR
    error = Column(String(256), nullable=True)
    consecutive = Column(Integer, nullable=False, default=1)
    __table_args__ = (Index("ix_read_error_eq_ts", "equipment_id", "ts"),)


class EventRow(Base):
    """Eventos do motor de regras (Etapa 2)."""
    __tablename__ = "event"
    id = Column(Integer, primary_key=True, autoincrement=True)
    equipment_id = Column(String(64), nullable=False)
    type = Column(String(64), nullable=False)
    severity = Column(String(16), nullable=False)
    ts_start = Column(DateTime(timezone=True), nullable=False)
    ts_end = Column(DateTime(timezone=True), nullable=True)
    rule_id = Column(String(64), nullable=True)
    rule_version = Column(String(16), nullable=True)
    context = Column(JSON, nullable=True)
    ack_by = Column(String(64), nullable=True)
    ack_ts = Column(DateTime(timezone=True), nullable=True)
    resolution = Column(String(512), nullable=True)
    __table_args__ = (Index("ix_event_eq_start", "equipment_id", "ts_start"),)


def _aware(ts: Optional[datetime]) -> Optional[datetime]:
    """SQLite devolve naive; o dado foi sempre gravado em UTC."""
    if ts is None:
        return None
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts


class HistorianRepository:
    def __init__(self, url: str = "sqlite:///./forja_historian.db"):
        self.url = url
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self.engine = create_engine(url, connect_args=connect_args, future=True)
        Base.metadata.create_all(self.engine)
        self._session = sessionmaker(bind=self.engine, expire_on_commit=False)

    # -- escrita: amostras
    def write_samples(self, samples: list[Sample]) -> int:
        if not samples:
            return 0
        rows = []
        for s in samples:
            common = dict(ts=s.ts, equipment_id=s.equipment_id, tag=s.tag,
                          quality=s.quality.value, source=s.source.value, source_ts=s.source_ts)
            if s.is_numeric:
                rows.append(SampleRow(value_num=float(s.value), **common))
            else:
                rows.append(SampleRow(value_text=str(s.value), **common))
        with self._session() as db:
            db.add_all(rows)
            db.commit()
        return len(rows)

    # -- escrita: falhas de aquisição
    def write_read_errors(self, errors: list[ReadError]) -> int:
        if not errors:
            return 0
        rows = [ReadErrorRow(ts=e.ts, equipment_id=e.equipment_id, tag=e.tag,
                             source=e.source.value, quality=e.quality.value,
                             error=e.error[:256], consecutive=e.consecutive) for e in errors]
        with self._session() as db:
            db.add_all(rows)
            db.commit()
        return len(rows)

    def read_errors(self, equipment_id: str, ts_from: Optional[datetime] = None,
                    ts_to: Optional[datetime] = None, limit: int = 1000) -> list[ReadError]:
        stmt = select(ReadErrorRow).where(ReadErrorRow.equipment_id == equipment_id)
        if ts_from is not None:
            stmt = stmt.where(ReadErrorRow.ts >= ts_from)
        if ts_to is not None:
            stmt = stmt.where(ReadErrorRow.ts <= ts_to)
        stmt = stmt.order_by(ReadErrorRow.ts.desc()).limit(limit)
        with self._session() as db:
            rows = db.execute(stmt).scalars().all()
        out = [ReadError(ts=_aware(r.ts), equipment_id=r.equipment_id, tag=r.tag,
                         source=DataSource(r.source), error=r.error or "",
                         consecutive=r.consecutive, quality=Quality(r.quality)) for r in rows]
        out.reverse()
        return out

    def count_read_errors(self, equipment_id: Optional[str] = None) -> int:
        stmt = select(func.count(ReadErrorRow.id))
        if equipment_id:
            stmt = stmt.where(ReadErrorRow.equipment_id == equipment_id)
        with self._session() as db:
            return int(db.execute(stmt).scalar_one())

    # -- escrita: eventos
    def write_event(self, equipment_id: str, type_: str, severity: str, ts_start: datetime,
                    ts_end: Optional[datetime] = None, rule_id: Optional[str] = None,
                    rule_version: Optional[str] = None, context: Optional[dict] = None) -> int:
        row = EventRow(equipment_id=equipment_id, type=type_, severity=severity, ts_start=ts_start,
                       ts_end=ts_end, rule_id=rule_id, rule_version=rule_version, context=context)
        with self._session() as db:
            db.add(row)
            db.commit()
            return int(row.id)

    def close_event(self, event_id: int, ts_end: datetime) -> None:
        with self._session() as db:
            db.execute(update(EventRow).where(EventRow.id == event_id).values(ts_end=ts_end))
            db.commit()

    def events(self, equipment_id: str, ts_from: Optional[datetime] = None,
               ts_to: Optional[datetime] = None, type_: Optional[str] = None,
               limit: int = 500) -> list[dict]:
        stmt = select(EventRow).where(EventRow.equipment_id == equipment_id)
        if ts_from is not None:
            stmt = stmt.where(EventRow.ts_start >= ts_from)
        if ts_to is not None:
            stmt = stmt.where(EventRow.ts_start <= ts_to)
        if type_:
            stmt = stmt.where(EventRow.type == type_)
        stmt = stmt.order_by(EventRow.ts_start.desc()).limit(limit)
        with self._session() as db:
            rows = db.execute(stmt).scalars().all()
        return [self._event_dict(r) for r in rows]

    def event(self, event_id: int) -> Optional[dict]:
        with self._session() as db:
            row = db.get(EventRow, event_id)
            return self._event_dict(row) if row else None

    def count_events(self, equipment_id: Optional[str] = None) -> int:
        stmt = select(func.count(EventRow.id))
        if equipment_id:
            stmt = stmt.where(EventRow.equipment_id == equipment_id)
        with self._session() as db:
            return int(db.execute(stmt).scalar_one())

    @staticmethod
    def _event_dict(r: EventRow) -> dict:
        return {"id": int(r.id), "equipment_id": r.equipment_id, "type": r.type,
                "severity": r.severity, "ts_start": _aware(r.ts_start), "ts_end": _aware(r.ts_end),
                "rule_id": r.rule_id, "rule_version": r.rule_version, "context": r.context or {},
                "ack_by": r.ack_by, "ack_ts": _aware(r.ack_ts), "resolution": r.resolution}

    # -- leitura: amostras
    def samples(self, equipment_id: str, tag: str, ts_from: Optional[datetime] = None,
                ts_to: Optional[datetime] = None, limit: int = 5000) -> list[Sample]:
        stmt = select(SampleRow).where(SampleRow.equipment_id == equipment_id, SampleRow.tag == tag)
        if ts_from is not None:
            stmt = stmt.where(SampleRow.ts >= ts_from)
        if ts_to is not None:
            stmt = stmt.where(SampleRow.ts <= ts_to)
        stmt = stmt.order_by(SampleRow.ts.desc()).limit(limit)
        with self._session() as db:
            rows = db.execute(stmt).scalars().all()
        out = [self._to_sample(r) for r in rows]
        out.reverse()
        return out

    def latest(self, equipment_id: str, tag: str) -> Optional[Sample]:
        stmt = (select(SampleRow).where(SampleRow.equipment_id == equipment_id, SampleRow.tag == tag)
                .order_by(SampleRow.ts.desc()).limit(1))
        with self._session() as db:
            row = db.execute(stmt).scalar_one_or_none()
        return self._to_sample(row) if row else None

    def count(self, equipment_id: Optional[str] = None) -> int:
        stmt = select(func.count(SampleRow.id))
        if equipment_id:
            stmt = stmt.where(SampleRow.equipment_id == equipment_id)
        with self._session() as db:
            return int(db.execute(stmt).scalar_one())

    def tags(self, equipment_id: str) -> list[str]:
        stmt = select(SampleRow.tag).where(SampleRow.equipment_id == equipment_id).distinct()
        with self._session() as db:
            return sorted(db.execute(stmt).scalars().all())

    @staticmethod
    def _to_sample(r: SampleRow) -> Sample:
        from forja.domain.models import DataType, TAG_CATALOG
        value = r.value_num if r.value_num is not None else (r.value_text or "")
        cat = TAG_CATALOG.get(r.tag)
        if cat and r.value_num is not None:
            if cat.data_type == DataType.INT:
                value = int(r.value_num)
            elif cat.data_type == DataType.BOOL:
                value = bool(r.value_num)
        return Sample(ts=_aware(r.ts), equipment_id=r.equipment_id, tag=r.tag, value=value,
                      quality=Quality(r.quality), source=DataSource(r.source),
                      source_ts=_aware(r.source_ts))
