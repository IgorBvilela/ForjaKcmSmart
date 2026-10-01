"""RuleEngine: OPEN/UPDATE/CLOSE deterministicos sobre lotes sinteticos com FakeClock."""

from __future__ import annotations

from datetime import UTC, timedelta

import pytest

from forja.domain import EventStatus, EvidenceLevel, Quality, Severity, SourceRef
from forja.events.engine import RuleEngine
from forja.events.rules import Condition, Rule
from forja.infra.clock import FakeClock
from tests.fixtures.synthetic_batches import (
    EQ,
    GTEX_ID,
    T0,
    at,
    beltload_low_values,
    build_engine,
    comm_error_batch,
    feed,
    gtex_profile,
    make_batch,
    normal_values,
    open_beltload_low_event,
    opens,
    series,
    stopped_values,
)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(T0)


async def test_beltload_low_opens_with_what_changed_belt_load_first(clock: FakeClock) -> None:
    _, event, transitions = await open_beltload_low_event(clock)
    assert event.type == "BELT_LOAD_LOW"
    assert event.title_pt == "Pouco material sobre a correia"
    assert event.severity == Severity.ATTENTION
    assert event.dedupe_key == f"{GTEX_ID}:R-BELTLOAD-001"
    assert event.status == EventStatus.OPEN
    assert event.quality == Quality.SIMULATED
    assert event.diagnosis_ref == "belt_load_low"
    # so a regra de pouco material abriu neste cenario
    assert [e.type for e in opens(transitions)] == ["BELT_LOAD_LOW"]

    wc = event.context.what_changed
    assert wc, "what_changed vazio"
    assert wc[0].tag == "belt_load"
    assert wc[0].changed_first is True
    assert sum(1 for i in wc if i.changed_first) == 1
    starts = [i.ts_start_utc for i in wc if i.ts_start_utc is not None]
    assert starts == sorted(starts)
    belt = wc[0]
    assert belt.delta_kind == "pct"
    assert belt.delta is not None
    assert belt.delta <= -35
    drive = next(i for i in wc if i.tag == "drive_command")
    assert drive.delta_kind == "points"
    assert drive.delta is not None
    assert drive.delta >= 15
    assert belt.ts_start_utc is not None
    assert drive.ts_start_utc is not None
    assert belt.ts_start_utc < drive.ts_start_utc


async def test_beltload_low_summary_is_filled_portuguese(clock: FakeClock) -> None:
    _, event, _ = await open_beltload_low_event(clock)
    assert "{" not in event.summary_pt
    assert "UNKNOWN" not in event.summary_pt
    assert "Primeiro a mudar: Material na correia" in event.summary_pt
    assert "," in event.summary_pt  # virgula decimal


async def test_beltload_low_context_pre_window_and_timeline(clock: FakeClock) -> None:
    _, event, _ = await open_beltload_low_event(clock)
    ctx = event.context
    assert ctx.pre_window_s == 60
    assert ctx.pre_samples
    span = ctx.pre_samples[-1].ts_utc - ctx.pre_samples[0].ts_utc
    assert span <= timedelta(seconds=60)
    assert all(s.ts_utc < event.start_utc for s in ctx.pre_samples)
    assert all(s.ts_utc >= event.start_utc for s in ctx.during_samples)
    assert ctx.gap_count == 0
    assert ctx.comm_error_count == 0

    ts = [p.ts_utc for p in ctx.timeline]
    assert ts == sorted(ts)
    texts = [p.text_pt for p in ctx.timeline]
    assert any(t.startswith("Primeiro a mudar: Material na correia") for t in texts)
    kcm = [p for p in ctx.timeline if p.kind == "kcm"]
    assert len(kcm) == 1
    assert "56" in kcm[0].text_pt
    assert "observado nesta aplicação" in kcm[0].text_pt
    assert (
        "Pouco material sobre a correia · alarme do KCM · observado nesta aplicação"
        in kcm[0].text_pt
    )
    # a regra aparece pelo titulo; o id fica em event.rule_id ('Detalhes tecnicos')
    assert "Regra Forja 'Pouco material sobre a correia' atendida" in texts
    assert any(
        t.startswith("Forja abriu o evento 'Pouco material sobre a correia' após 10 s")
        for t in texts
    )
    assert not any("R-BELTLOAD-001" in t for t in texts)
    assert event.rule_id == "R-BELTLOAD-001"
    # o alarme so fala na voz do KCM: sem ponto duplicado da Forja para alarm_code
    assert sum(1 for p in ctx.timeline if p.tag == "alarm_code") == 1


async def test_beltload_low_discrete_tags_in_words(clock: FakeClock) -> None:
    _, event, _ = await open_beltload_low_event(clock)
    wc = {i.tag: i for i in event.context.what_changed}
    # estado da maquina nao mudou (sempre em operacao): nao entra em 'O que mudou'
    assert "machine_state" not in wc
    alarm = wc["alarm_code"]
    assert alarm.delta_kind == "none"
    assert alarm.delta is None
    assert (
        alarm.text_pt == "passou de nenhum alarme para alarme 56 (Pouco material sobre a correia)"
    )
    assert alarm.ts_start_utc == at(110)
    for item in event.context.what_changed:
        assert "1,00" not in item.text_pt or item.tag in ("belt_load", "mass_flow")


async def test_open_happens_only_after_persistence(clock: FakeClock) -> None:
    engine = build_engine(clock)
    transitions = await feed(engine, series(beltload_low_values, 125, equipment_id=GTEX_ID), clock)
    event = opens(transitions, "BELT_LOAD_LOW")[0]
    detect_ts = event.context.during_samples[-1].ts_utc
    assert detect_ts - event.start_utc >= timedelta(seconds=10)
    assert event.start_utc > at(100)


async def test_does_not_open_with_comm_error_quality(clock: FakeClock) -> None:
    engine = build_engine(clock)
    batches = series(beltload_low_values, 125, equipment_id=GTEX_ID, quality=Quality.COMM_ERROR)
    transitions = await feed(engine, batches, clock)
    assert opens(transitions, "BELT_LOAD_LOW") == []
    only_comm = [comm_error_batch(at(t)) for t in range(126)]
    engine2 = build_engine(FakeClock(T0))
    transitions2 = await feed(engine2, only_comm)
    assert opens(transitions2, "BELT_LOAD_LOW") == []


@pytest.mark.parametrize("quality", [Quality.BAD, Quality.STALE])
async def test_does_not_open_with_bad_or_stale_quality(quality: Quality) -> None:
    engine = build_engine(FakeClock(T0))
    transitions = await feed(engine, series(beltload_low_values, 125, quality=quality))
    assert transitions == []


async def test_update_while_persisting_then_close_after_clear(clock: FakeClock) -> None:
    engine = build_engine(clock)
    anomaly = series(beltload_low_values, 130, equipment_id=GTEX_ID)
    recovery = series(normal_values, 200, first=131, equipment_id=GTEX_ID)
    transitions = await feed(engine, [*anomaly, *recovery], clock)
    kinds = [t.kind for t in transitions if t.event.type == "BELT_LOAD_LOW"]
    assert kinds[0] == "OPEN"
    assert "UPDATE" in kinds
    assert kinds.count("CLOSE") == 1
    assert kinds[-1] == "CLOSE"

    # A regra e um detector de transicao (queda >= 35% dentro de 60 s): quando a janela deslizante
    # deixa a rampa para tras, a condicao limpa mesmo com belt_load ainda baixo. O fechamento vem
    # close_when_clear_for_s (30 s) depois do primeiro lote em que a condicao deixou de valer.
    last_update = max(
        t.event.context.during_samples[-1].ts_utc for t in transitions if t.kind == "UPDATE"
    )
    cleared_at = last_update + timedelta(seconds=1)
    closed = next(t.event for t in transitions if t.kind == "CLOSE")
    assert closed.end_utc == cleared_at
    assert closed.end_utc <= at(131)
    assert closed.status == EventStatus.RESOLVED
    assert closed.resolution is not None
    assert closed.resolution.resolved_by == "forja"
    assert closed.resolution.resolution_class == "UNKNOWN"
    assert closed.resolution.resolved_at_utc == cleared_at + timedelta(seconds=30)
    assert closed.context.post_samples
    assert all(s.ts_utc < cleared_at for s in closed.context.during_samples)
    texts = [p.text_pt for p in closed.context.timeline]
    assert "Regra Forja 'Pouco material sobre a correia' deixou de ser atendida" in texts
    assert "Forja encerrou o evento após 30 s sem a condição" in texts
    # horario em texto no fuso da planta (12:02:05Z = 09:02:05 em Sao Paulo); end_utc segue UTC
    assert closed.resolution.note_pt == (
        "Encerrado automaticamente: a condição deixou de ser observada a partir de 09:02:05."
    )
    assert closed.end_utc == at(125)
    assert engine.open_events(GTEX_ID) == []


async def test_cooldown_blocks_reopen_until_expiry() -> None:
    rule = Rule(
        id="R-TEST-001",
        internal_code="TESTE_ESFORCO_ALTO",
        title_pt="Teste de esforço alto",
        severity=Severity.ATTENTION,
        conditions=[Condition(tag="drive_command", op="gt", value=85)],
        cooldown_s=60,
        close_when_clear_for_s=5,
        diagnosis_ref="drive_command_high",
        sources=[
            SourceRef(
                id="SRC-T", kind="rule", title="teste", evidence_level=EvidenceLevel.FORJA_RULE
            )
        ],
        summary_template_pt="Esforço {drive_command_now}%",
    )
    clock = FakeClock(T0)
    engine = build_engine(clock, rules=[rule])

    def dc(value: float) -> dict[str, float]:
        return {"drive_command": value, "machine_state": 1}

    batches = [make_batch(at(0), dc(90.0))]
    batches += [make_batch(at(t), dc(50.0)) for t in range(1, 7)]
    batches += [make_batch(at(t), dc(90.0)) for t in range(10, 70)]
    transitions = await feed(engine, batches, clock)
    kinds = [(t.kind, t.event.start_utc) for t in transitions]
    assert kinds[0] == ("OPEN", at(0))
    close_idx = next(i for i, k in enumerate(kinds) if k[0] == "CLOSE")
    assert kinds[close_idx][1] == at(0)
    reopen = [k for k in kinds[close_idx + 1 :] if k[0] == "OPEN"]
    assert len(reopen) == 1
    # reabre so quando o cooldown (6 s + 60 s) termina, mas o inicio e quando a condicao voltou
    reopened = next(t.event for t in transitions[close_idx + 1 :] if t.kind == "OPEN")
    assert reopened.context.during_samples[-1].ts_utc == at(66)
    assert reopened.start_utc == at(10)


async def test_comm_degraded_opens_after_15s_of_comm_error(clock: FakeClock) -> None:
    engine = build_engine(clock)
    good = series(normal_values, 10)
    failing = [comm_error_batch(at(t)) for t in range(11, 40)]
    transitions = await feed(engine, [*good, *failing], clock)
    found = opens(transitions, "COMM_DEGRADED")
    assert len(found) == 1
    event = found[0]
    assert event.start_utc == at(11)
    detect_ts = event.context.during_samples[-1].ts_utc
    assert detect_ts == at(26)
    assert event.quality == Quality.COMM_ERROR
    assert event.context.comm_error_count > 0
    flow = next(i for i in event.context.what_changed if i.tag == "mass_flow")
    assert flow.before == 1300.0
    assert flow.now is None
    assert flow.delta_kind == "none"
    assert "Última vazão conhecida antes da falha: 1300 kg/h." in event.summary_pt
    assert "Agora: sem leitura" in flow.text_pt


async def test_comm_degraded_without_any_prior_reading_says_so_in_words() -> None:
    """Falha desde a primeira leitura: nada a comparar, e o resumo diz 'sem leitura', nunca '—'."""
    engine = build_engine(FakeClock(T0))
    transitions = await feed(engine, [comm_error_batch(at(t)) for t in range(0, 40)])
    (event,) = opens(transitions, "COMM_DEGRADED")
    assert "Última vazão conhecida antes da falha: sem leitura." in event.summary_pt
    assert "—" not in event.summary_pt
    assert "kg/h" not in event.summary_pt
    # continua sem nenhuma leitura utilizavel (antes ou agora) fica fora de 'O que mudou'
    assert [i.tag for i in event.context.what_changed] == []


async def test_machine_stopped_opens_on_transition_and_closes_next_batch(clock: FakeClock) -> None:
    engine = build_engine(clock)
    running = series(normal_values, 5)
    stopped = series(stopped_values, 10, first=6)
    transitions = await feed(engine, [*running, *stopped], clock)
    stop = [t for t in transitions if t.event.type == "MACHINE_STOPPED"]
    assert [t.kind for t in stop] == ["OPEN", "CLOSE"]
    event = stop[0].event
    assert event.severity == Severity.INFO
    assert event.start_utc == at(6)
    assert "Motivo desconhecido" in event.summary_pt
    assert "STOP BY" in event.summary_pt
    assert "código 3" in event.summary_pt
    assert "UNKNOWN" not in event.summary_pt
    kcm = [p for p in event.context.timeline if p.kind == "kcm"]
    assert len(kcm) == 1
    assert kcm[0].text_pt == (
        "KCM informou motivo da parada (STOP BY): código 3 · Motivo desconhecido "
        "(a Forja ainda não tem fonte para classificar este motivo)"
    )
    # estado da maquina mudou: primeiro a mudar, em palavras
    first = event.context.what_changed[0]
    assert first.tag == "machine_state"
    assert first.changed_first is True
    assert first.text_pt == "passou de Em operação para Parado"
    assert first.delta_kind == "none"
    stop_item = next(i for i in event.context.what_changed if i.tag == "stop_by")
    assert stop_item.text_pt == "passou de nenhum para código 3 (Motivo desconhecido)"
    texts = [p.text_pt for p in event.context.timeline]
    assert "Primeiro a mudar: Estado da máquina passou de Em operação para Parado" in texts
    # STOP BY fala so na voz do KCM
    assert sum(1 for p in event.context.timeline if p.tag == "stop_by") == 1
    assert (
        "Forja abriu o evento 'Equipamento parado' na primeira leitura em que a condição apareceu"
        in texts
    )
    closed_texts = [p.text_pt for p in stop[1].event.context.timeline]
    assert "Forja encerrou o evento na primeira leitura sem a condição" in closed_texts
    assert stop[1].event.end_utc == at(7)
    # outras regras nao abrem com a maquina parada
    assert {e.type for e in opens(transitions)} == {"MACHINE_STOPPED"}


async def test_engine_is_deterministic() -> None:
    results = []
    for _ in range(2):
        engine = build_engine(FakeClock(T0))
        batches = series(beltload_low_values, 130, equipment_id=GTEX_ID)
        transitions = await feed(engine, batches)
        results.append(
            [(t.kind, t.event.id, t.event.start_utc, t.event.summary_pt) for t in transitions]
        )
    assert results[0] == results[1]
    assert results[0]


def test_alarm_lookup_uses_profile_key_and_code_variants(clock: FakeClock) -> None:
    engine = build_engine(clock)
    profile = gtex_profile()
    hit = engine.alarm_lookup(profile, "56")
    assert hit.definition is not None
    assert hit.definition.evidence == EvidenceLevel.FIELD_OBSERVED
    assert hit.qualifier_pt == "Observado nesta aplicação"
    miss = engine.alarm_lookup(None, "56")
    assert miss.definition is None
    assert miss.qualifier_pt == "Não catalogado"
    candidate = engine.alarm_lookup(profile, "8")
    assert candidate.definition is None
    assert [c.key.code for c in candidate.candidates] == ["8"]  # código normalizado pelo domínio


def test_buffer_must_cover_pre_window(clock: FakeClock) -> None:
    with pytest.raises(ValueError, match="buffer_s"):
        build_engine(clock, pre_window_s=60, buffer_s=30)


async def test_open_events_lists_only_this_equipment(clock: FakeClock) -> None:
    engine, event, _ = await open_beltload_low_event(clock)
    assert [e.id for e in engine.open_events(GTEX_ID)] == [event.id]
    assert engine.open_events(EQ) == []


def test_engine_signature_matches_contract() -> None:
    clock = FakeClock(T0)
    engine = RuleEngine([], build_engine(clock).alarms, build_engine(clock).stop_by, clock)
    assert engine.pre_window_s == 60
    assert engine.post_window_s == 30
    assert engine.buffer_s == 180
    # fuso da planta: padrao America/Sao_Paulo, configuravel por nome IANA
    assert getattr(engine.zone, "key", None) == "America/Sao_Paulo"
    utc_engine = RuleEngine([], engine.alarms, engine.stop_by, clock, timezone="UTC")
    assert utc_engine.zone is UTC
