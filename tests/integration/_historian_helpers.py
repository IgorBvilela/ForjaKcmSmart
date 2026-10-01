"""Fabricas compartilhadas pelos testes do Bloco 2 (historian, core store, backup).

Nao e arquivo de teste (nao comeca com test_). Tudo aqui e dado de teste: valores sao
inventados e marcados SIMULATED ou GOOD conforme o cenario pede.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from forja.domain import (
    MANDATORY_CAVEAT_PT,
    Caveat,
    Diagnosis,
    DiagnosisSummary,
    Event,
    EventContext,
    EventStatus,
    EvidenceItem,
    EvidenceLevel,
    Hypothesis,
    NextCheck,
    Quality,
    Sample,
    Severity,
    SourceRef,
    TimelinePoint,
    WhatChangedItem,
)
from forja.infra.clock import FakeClock

EQ = "EQ_TESTE"
SRC = "sim:NORMAL_OPERATION"
RULE_ID = "R-BELTLOAD-001"

RULE_SOURCE = SourceRef(
    id=RULE_ID,
    kind="rule",
    title="Pouco material sobre a correia",
    reference=f"{RULE_ID} v1",
    evidence_level=EvidenceLevel.FORJA_RULE,
)


def sample(
    when: datetime | FakeClock,
    tag: str = "mass_flow",
    value: float | None = 100.0,
    quality: Quality = Quality.GOOD,
    equipment_id: str = EQ,
    raw: bytes | None = None,
    reason_pt: str | None = None,
    source: str = SRC,
) -> Sample:
    ts = when.now_utc() if isinstance(when, FakeClock) else when
    return Sample(
        ts_utc=ts,
        equipment_id=equipment_id,
        tag=tag,
        value=value,
        quality=quality,
        source=source,
        raw=raw,
        reason_pt=reason_pt,
    )


def series_1hz(
    start: datetime,
    seconds: int,
    tag: str = "mass_flow",
    values: float | Callable[[int], float] = 100.0,
    quality: Quality = Quality.GOOD,
    equipment_id: str = EQ,
) -> list[Sample]:
    """Uma amostra por segundo em [start, start + seconds)."""
    out: list[Sample] = []
    for i in range(seconds):
        v = values(i) if callable(values) else values
        out.append(sample(start + timedelta(seconds=i), tag, v, quality, equipment_id=equipment_id))
    return out


def raw_conn(path: Path) -> sqlite3.Connection:
    """Conexao direta para inspecionar o arquivo. Quem abre fecha."""
    return sqlite3.connect(path)


def table_count(path: Path, table: str) -> int:
    conn = raw_conn(path)
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])  # noqa: S608
    finally:
        conn.close()


def fetch_all(path: Path, sql: str, params: tuple[object, ...] = ()) -> list[tuple[object, ...]]:
    conn = raw_conn(path)
    try:
        return [tuple(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def make_event(
    clock: FakeClock,
    equipment_id: str = EQ,
    dedupe_key: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    rule_id: str = RULE_ID,
    type_: str = "BELT_LOAD_LOW",
) -> Event:
    start_utc = start or clock.now_utc()
    pre = sample(
        start_utc - timedelta(seconds=30), "belt_load", 2.0, Quality.SIMULATED, equipment_id
    )
    changed = WhatChangedItem(
        tag="belt_load",
        label_pt="Material na correia",
        unit="kg/m",
        before=2.0,
        now=1.2,
        delta=-40.0,
        delta_kind="pct",
        changed_first=True,
        ts_start_utc=start_utc - timedelta(seconds=20),
        text_pt="Caiu de 2,0 para 1,2 kg/m",
    )
    return Event(
        equipment_id=equipment_id,
        type=type_,
        title_pt="Pouco material sobre a correia",
        start_utc=start_utc,
        end_utc=end,
        severity=Severity.ATTENTION,
        summary_pt="Material na correia caiu 40% em 60 s enquanto o acionamento subiu.",
        rule_id=rule_id,
        context=EventContext(
            pre_window_s=60,
            post_window_s=30,
            pre_samples=(pre,),
            what_changed=(changed,),
            timeline=(TimelinePoint(ts_utc=start_utc, text_pt="Forja detectou pouco material"),),
        ),
        sources=(RULE_SOURCE,),
        quality=Quality.SIMULATED,
        status=EventStatus.RESOLVED if end is not None else EventStatus.OPEN,
        dedupe_key=dedupe_key or f"{equipment_id}:{rule_id}",
        diagnosis_ref="belt_load_low",
    )


def make_diagnosis(event: Event, clock: FakeClock) -> Diagnosis:
    evidence = (
        EvidenceItem(
            id="e1",
            text_pt="Material na correia caiu de 2,0 para 1,2 kg/m.",
            tag="belt_load",
            value=1.2,
            unit="kg/m",
            quality=Quality.SIMULATED,
            evidence_level=EvidenceLevel.FORJA_RULE,
            ts_utc=event.start_utc,
        ),
    )
    hypotheses = (
        Hypothesis(
            id="h1",
            text_pt="Comportamento compatível com falta de material na entrada do dosador.",
            evidence_level=EvidenceLevel.HYPOTHESIS,
            rationale_pt="A carga caiu e o acionamento subiu para manter a vazão.",
            verification_ids=("c1",),
            source_ids=(RULE_ID,),
        ),
    )
    next_checks = (
        NextCheck(
            id="c1",
            order=1,
            text_pt="Verificar alimentação do dosador.",
            how_pt="Observar a tremonha e a entrada de material.",
            evidence_level=EvidenceLevel.TECHNICAL_OPINION,
        ),
    )
    sources = (RULE_SOURCE,)
    return Diagnosis(
        event_id=event.id,
        equipment_id=event.equipment_id,
        generated_at_utc=clock.now_utc(),
        summary=DiagnosisSummary(
            title_pt=event.title_pt,
            text_pt=event.summary_pt,
            internal_code=event.type,
            severity=event.severity,
        ),
        evidence=evidence,
        what_changed=event.context.what_changed,
        hypotheses=hypotheses,
        next_checks=next_checks,
        sources=sources,
        caveats=(Caveat(text_pt=MANDATORY_CAVEAT_PT),),
        evidence_summary=Diagnosis.build_evidence_summary(
            evidence, hypotheses, next_checks, sources
        ),
    )
