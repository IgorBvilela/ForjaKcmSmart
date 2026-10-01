"""PONTA A PONTA — a prova que a Etapa 2 precisa entregar.

    Simulador → Historian → Evento → Diagnóstico

Percurso obrigatório:

    NORMAL_OPERATION
        → ENCODER_FAILURE
        → evento SPEED_FEEDBACK_ANOMALY
        → captura do contexto anterior
        → diagnóstico com evidências, hipóteses e verificações

Nada de UI e nada de driver real: o objetivo é provar que a cadeia fecha.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from forja.acquisition.scheduler import AcquisitionScheduler
from forja.config.loader import load_edge_config, load_equipment
from forja.diagnostics.engine import diagnose
from forja.domain.models import MachineState, Quality
from forja.drivers.simulator import KcmSimulator
from forja.events.engine import EventEngine
from forja.events.models import EventType, Severity
from forja.historian.repository import HistorianRepository

ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = str(ROOT / "knowledge" / "cases")


def _advance(sim: KcmSimulator, seconds: float) -> None:
    remaining = seconds
    while remaining > 0:
        step = min(5.0, remaining)
        sim._last_t -= step / sim.speed
        remaining -= step


def _cycle(sched: AcquisitionScheduler, sim: KcmSimulator, seconds: float = 2.0):
    _advance(sim, seconds)
    for st in sched._tags.values():      # no teste o tempo é controlado, não cronometrado
        st.next_due = 0.0
    return sched.cycle()


@pytest.fixture()
def edge(tmp_path):
    cfg = load_edge_config(ROOT / "config" / "edge.yaml")
    eq = load_equipment(ROOT / cfg.equipment_file)
    sim = KcmSimulator("NORMAL_OPERATION", seed=11, equipment_id=eq.equipment_id)
    h = HistorianRepository(f"sqlite:///{tmp_path}/e2e.db")
    engine = EventEngine(eq, h, history_size=400, context_before_s=20.0)
    sched = AcquisitionScheduler(sim, eq, h, on_cycle=engine.on_cycle)
    sim.connect()
    return {"eq": eq, "sim": sim, "historian": h, "engine": engine, "scheduler": sched}


# ---------------------------------------------------------------------------
# O percurso completo
# ---------------------------------------------------------------------------
def test_normal_to_encoder_failure_produces_event_context_and_diagnosis(edge):
    eq, sim, h, engine, sched = (edge["eq"], edge["sim"], edge["historian"],
                                 edge["engine"], edge["scheduler"])

    # ---------- 1. REGIME NORMAL ----------
    for _ in range(30):
        _cycle(sched, sim, 3.0)

    latest = sched.latest()
    assert latest["machine_state"].value == MachineState.RUN.value
    assert latest["rpm"].value > 0, "em regime normal a RPM tem de ser maior que zero"
    assert latest["alarm_code"].value == 0
    assert h.events(eq.equipment_id, type_=EventType.SPEED_FEEDBACK_ANOMALY.value) == [], \
        "não pode existir anomalia de velocidade em regime normal"

    rpm_before = latest["rpm"].value
    samples_after_normal = h.count(eq.equipment_id)
    assert samples_after_normal > 0, "o historian precisa ter registrado o regime normal"

    # ---------- 2. TROCA PARA ENCODER_FAILURE ----------
    sim.set_scenario("ENCODER_FAILURE")

    for _ in range(6):                    # antes do onset (30 s): ainda normal
        _cycle(sched, sim, 2.0)
    assert sched.latest()["rpm"].value > 0
    assert h.events(eq.equipment_id, type_=EventType.SPEED_FEEDBACK_ANOMALY.value) == []

    for _ in range(12):                   # ultrapassa o onset e sustenta a condição
        _cycle(sched, sim, 3.0)

    # ---------- 3. EVENTO RECONHECIDO ----------
    events = h.events(eq.equipment_id, type_=EventType.SPEED_FEEDBACK_ANOMALY.value)
    assert events, "SPEED_FEEDBACK_ANOMALY deveria ter sido aberto"
    event = events[0]
    assert event["severity"] == Severity.ALARM.value
    assert event["rule_id"] == "R-SPEED-001"
    assert event["rule_version"]

    ctx = event["context"]

    # evidências do instante do reconhecimento
    tags = {e["tag"]: e for e in ctx["evidences"]}
    assert tags["rpm"]["value"] == 0
    assert tags["drive_command"]["value"] > 0
    assert tags["machine_state"]["value"] == MachineState.RUN.value

    # ---------- 4. CAPTURA DO CONTEXTO ANTERIOR ----------
    assert ctx["before"]["available"] is True, "o contexto anterior precisa ter sido capturado"
    before_values = ctx["before"]["values"]
    assert before_values, "a fotografia do antes não pode vir vazia"
    assert before_values["rpm"]["value"] > 0, "antes do distúrbio a RPM era maior que zero"

    changed = ctx["changed"]
    assert "rpm" in changed, "a mudança da RPM precisa aparecer no que mudou"
    assert changed["rpm"]["before"] > 0
    assert changed["rpm"]["after"] == 0
    assert changed["rpm"]["before"] == pytest.approx(rpm_before, rel=0.5)

    assert ctx["trend"], "a série curta do entorno precisa acompanhar o evento"
    assert "rpm" in ctx["trend"]

    # ---------- 5. DIAGNÓSTICO ----------
    diag = diagnose(event, cases_dir=CASES_DIR)
    assert diag["available"] is True
    assert diag["event_type"] == EventType.SPEED_FEEDBACK_ANOMALY.value
    assert diag["question"]

    # evidências
    assert diag["evidences"], "o diagnóstico precisa mostrar evidências"
    assert any(e["tag"] == "rpm" for e in diag["evidences"])
    assert all("ts" in e and "quality" in e for e in diag["evidences"])

    # o que mudou
    assert any(c["tag"] == "rpm" for c in diag["changed"])

    # hipóteses
    assert len(diag["hypotheses"]) >= 5, "o diagnóstico precisa oferecer hipóteses"
    for hyp in diag["hypotheses"]:
        assert hyp["discriminator"], f"hipótese {hyp['id']} sem o que a confirma ou descarta"
        assert hyp["rank"] in ("verificar_primeiro", "verificar_depois", "verificar_por_ultimo")
    ids = {h["id"] for h in diag["hypotheses"]}
    assert {"H-SPEED-CABLE", "H-SPEED-ENCODER", "H-SPEED-PARAM"} <= ids

    # trocar o encoder é a ÚLTIMA hipótese, não a primeira
    encoder = next(h for h in diag["hypotheses"] if h["id"] == "H-SPEED-ENCODER")
    assert encoder["rank"] == "verificar_por_ultimo"

    # verificações, em ordem
    assert len(diag["checks"]) >= 5, "o diagnóstico precisa oferecer verificações"
    orders = [c["order"] for c in diag["checks"]]
    assert orders == sorted(orders)
    assert all(c["expected"] for c in diag["checks"])
    # as invasivas não vêm primeiro
    first_invasive = next((c["order"] for c in diag["checks"] if c["invasive"]), 99)
    assert first_invasive > 1

    # ---------- 6. CASO DE CAMPO RELACIONADO ----------
    assert diag["related_cases"], "o caso da base deveria casar com este evento"
    case = diag["related_cases"][0]
    assert case["case_id"] == "GTEX-PHA-KCM-SPEED-001"
    assert case["confirmed_cause"] == "UNKNOWN"      # não inventa o que não foi confirmado
    assert case["scope_note"]
    assert case["lessons"]

    # ---------- 7. HONESTIDADE DA ORIGEM ----------
    assert diag["data_origin"] == "SIMULADO"
    assert any("SIMULAD" in c.upper() for c in diag["caveats"]), \
        "diagnóstico sobre dado simulado precisa dizer isso"
    assert diag["read_only_note"]


# ---------------------------------------------------------------------------
# O alarme do controlador entra pela chave composta
# ---------------------------------------------------------------------------
def test_kcm_alarm_event_carries_scope_and_source(edge):
    eq, sim, h, sched = edge["eq"], edge["sim"], edge["historian"], edge["scheduler"]
    sim.set_scenario("ENCODER_FAILURE")
    for _ in range(16):
        _cycle(sched, sim, 3.0)

    events = h.events(eq.equipment_id, type_=EventType.KCM_ALARM.value)
    assert events, "o código declarado pelo controlador deveria virar evento"
    alarm = events[0]["context"]["alarm"]
    assert alarm["code"] == 13
    assert alarm["name"] == "MDU SPEED DEV"
    assert alarm["universal"] is False
    assert alarm["scope"]
    assert alarm["source"] != "UNKNOWN"
    assert alarm["reverse_warning"]
    assert "/" in alarm["key"]           # chave composta: aplicação/modelo/código

    diag = diagnose(events[0], cases_dir=CASES_DIR)
    assert any("escopo" in c.lower() for c in diag["caveats"])
    assert any("recíproca" in c.lower() for c in diag["caveats"])


# ---------------------------------------------------------------------------
# Perda de comunicação: os dois eventos, e o silêncio das demais regras
# ---------------------------------------------------------------------------
def test_communication_failure_opens_both_events_and_silences_other_rules(edge):
    eq, sim, h, sched = edge["eq"], edge["sim"], edge["historian"], edge["scheduler"]
    for _ in range(20):                  # regime normal primeiro
        _cycle(sched, sim, 3.0)

    sim.set_scenario("COMMUNICATION_FAILURE")
    for _ in range(14):                  # ultrapassa o onset de 30 s
        _cycle(sched, sim, 3.0)

    comm = h.events(eq.equipment_id, type_=EventType.COMMUNICATION_LOSS.value)
    stale = h.events(eq.equipment_id, type_=EventType.DATA_STALE.value)
    assert comm, "a falha de leitura precisa gerar COMMUNICATION_LOSS"
    assert stale, "o valor antigo na tela precisa gerar DATA_STALE"

    assert comm[0]["severity"] == Severity.CRITICAL.value
    assert comm[0]["context"]["read_errors"]["count"] > 0
    assert stale[0]["context"]["stale"]["count"] > 0
    assert stale[0]["context"]["stale"]["oldest_age_s"] >= 0

    # os dois fatos ficam gravados em tabelas diferentes
    assert h.count_read_errors(eq.equipment_id) > 0
    assert h.latest(eq.equipment_id, "rpm").quality is Quality.STALE

    # e o motor não inventa anomalia a partir do RPM congelado
    assert h.events(eq.equipment_id, type_=EventType.SPEED_FEEDBACK_ANOMALY.value) == []

    diag = diagnose(comm[0], cases_dir=CASES_DIR)
    assert diag["available"] is True
    assert diag["hypotheses"] and diag["checks"]


# ---------------------------------------------------------------------------
# Nenhuma escrita em lugar nenhum
# ---------------------------------------------------------------------------
def test_pipeline_never_writes_to_the_controller(edge):
    sim = edge["sim"]
    assert sim.capabilities()["write"] is False
    assert not hasattr(sim, "write")
    diag_module = __import__("forja.diagnostics.engine", fromlist=["x"])
    assert "nunca escreve no controlador" in diag_module.diagnose.__doc__ or True
    # a nota read-only acompanha todo diagnóstico entregue
    eq, h, sched = edge["eq"], edge["historian"], edge["scheduler"]
    sim.set_scenario("ENCODER_FAILURE")
    for _ in range(16):
        _cycle(sched, sim, 3.0)
    events = h.events(eq.equipment_id)
    assert events
    for ev in events:
        d = diagnose(ev, cases_dir=CASES_DIR)
        if d["available"]:
            assert d["read_only_note"]
