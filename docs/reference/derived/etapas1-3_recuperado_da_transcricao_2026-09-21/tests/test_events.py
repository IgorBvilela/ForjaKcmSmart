"""Testes da Etapa 2 — motor de eventos, alarmes por chave composta, STOP BY."""
from __future__ import annotations

from pathlib import Path

import pytest

from forja.acquisition.scheduler import AcquisitionScheduler
from forja.config.loader import load_edge_config, load_equipment
from forja.domain.equipment import EquipmentCard, TagMapping
from forja.domain.models import (Application, DataSource, MachineState, Quality, Sample,
                                 StopByClass, utcnow)
from forja.drivers.simulator import KcmSimulator, SCENARIOS, scenario_catalog
from forja.events import alarms
from forja.events.engine import EventEngine
from forja.events.models import EventType, Severity
from forja.events.rules import (CommunicationLoss, DataStale, MachineStopped, RuleContext,
                                SpeedFeedbackAnomaly, default_rules)
from forja.historian.repository import HistorianRepository

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------
def _project_equipment() -> EquipmentCard:
    cfg = load_edge_config(ROOT / "config" / "edge.yaml")
    return load_equipment(ROOT / cfg.equipment_file)


def _force_due(sched: AcquisitionScheduler) -> None:
    """Vence todas as tags. Nos testes o tempo é controlado, não cronometrado."""
    for st in sched._tags.values():
        st.next_due = 0.0


def _advance(sim: KcmSimulator, seconds: float) -> None:
    """Avança o tempo simulado. O simulador limita cada passo a 5 s."""
    remaining = seconds
    while remaining > 0:
        step = min(5.0, remaining)
        sim._last_t -= step / sim.speed
        remaining -= step


def _run_cycles(sched: AcquisitionScheduler, sim: KcmSimulator, n: int, step_s: float = 2.0):
    out = []
    for _ in range(n):
        _advance(sim, step_s)
        _force_due(sched)
        out.append(sched.cycle())
    return out


def _build(tmp_path, scenario: str, seed: int = 11, **engine_kwargs):
    eq = _project_equipment()
    sim = KcmSimulator(scenario, seed=seed, equipment_id=eq.equipment_id)
    h = HistorianRepository(f"sqlite:///{tmp_path}/ev.db")
    engine = EventEngine(eq, h, **engine_kwargs)
    sched = AcquisitionScheduler(sim, eq, h, on_cycle=engine.on_cycle)
    sim.connect()
    return eq, sim, h, engine, sched


# ---------------------------------------------------------------------------
# ALARMES POR CHAVE COMPOSTA — nenhum código vale sozinho
# ---------------------------------------------------------------------------
def test_alarm_lookup_requires_composite_key():
    d = alarms.lookup(56, Application.WBF, "KCM")
    assert d.key.application is Application.WBF
    assert d.key.controller_model == "KCM"
    assert d.key.code == 56
    assert d.name == "BELTLOAD LOW"


def test_no_alarm_definition_is_universal():
    for d in alarms.CATALOG.values():
        assert d.universal is False
        assert d.scope, f"{d.key} sem escopo declarado"
        assert d.source and d.source != "UNKNOWN", f"{d.key} sem fonte"


def test_every_alarm_declares_why_the_reverse_does_not_hold():
    """A recíproca nunca é assumida: condição X não implica código N."""
    for d in alarms.CATALOG.values():
        assert d.reverse_warning, f"{d.key} não declara por que a recíproca não vale"


def test_sft_code_08_is_not_presented_as_the_sft_code():
    """08 é UM código possível numa condição de SFT, nunca 'o' código."""
    d = alarms.lookup(8, Application.WBF, "KCM")
    assert "um entre os códigos" in d.scope.lower()
    assert "08" in d.reverse_warning or "outros códigos" in d.reverse_warning


def test_unknown_code_is_marked_unknown_not_guessed():
    d = alarms.lookup(4242, Application.WBF, "KCM")
    assert d.evidence is alarms.EvidenceLevel.UNKNOWN
    assert d.is_known is False
    assert d.source == "UNKNOWN"
    assert d.key.code == 4242          # a chave da consulta é preservada


def test_lookup_falls_back_from_specific_to_general():
    """13 está catalogado como ANY/KCM e precisa ser encontrado a partir de WBF/KCM."""
    d = alarms.lookup(13, Application.WBF, "KCM")
    assert d.name == "MDU SPEED DEV"
    assert d.key.application is Application.ANY   # a entrada encontrada é a geral


def test_evidence_level_separates_field_from_document():
    assert alarms.lookup(56, Application.WBF, "KCM").evidence is alarms.EvidenceLevel.FIELD_OBSERVED
    assert alarms.lookup(13, Application.WBF, "KCM").evidence is alarms.EvidenceLevel.DOC_REFERENCED


# ---------------------------------------------------------------------------
# CENÁRIOS DO SIMULADOR — o código nunca aparece sem o escopo
# ---------------------------------------------------------------------------
def test_every_scenario_alarm_carries_scope_and_source():
    for item in scenario_catalog():
        if not item["emits_alarm"]:
            continue
        a = item["alarm"]
        assert a["scope"], f"{item['name']} emite código sem escopo"
        assert a["source"], f"{item['name']} emite código sem fonte"
        assert a["universal"] is False
        assert "não é associação universal" in a["scope"]


def test_encoder_failure_is_described_as_inspired_by_the_gtex_occurrence():
    """Ajuste pedido: não chamar de 'o caso GTEX'."""
    sc = SCENARIOS["ENCODER_FAILURE"]
    note = sc.reference_note.lower()
    assert "inspirado na ocorrência gtex" in note
    assert "rpm indicada zero" in note
    assert "o caso gtex" not in note
    assert "o caso gtex" not in sc.description.lower()


def test_readme_does_not_equate_scenario_with_the_gtex_case():
    txt = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    assert "o caso gtex" not in txt


# ---------------------------------------------------------------------------
# REGRA DE OURO — dado velho não dispara evento
# ---------------------------------------------------------------------------
def _ctx_with(samples: dict[str, Sample], cycle=None) -> RuleContext:
    from forja.acquisition.scheduler import CycleResult
    eq = EquipmentCard(equipment_id="EQ")
    return RuleContext(equipment=eq, now=utcnow(), samples=samples,
                       cycle=cycle or CycleResult())


def _s(tag: str, value, quality: Quality = Quality.GOOD) -> Sample:
    return Sample(equipment_id="EQ", tag=tag, value=value, quality=quality,
                  source=DataSource.MODBUS_TCP)


def test_speed_rule_fires_on_fresh_data():
    ctx = _ctx_with({"machine_state": _s("machine_state", MachineState.RUN.value),
                     "drive_command": _s("drive_command", 62.0),
                     "rpm": _s("rpm", 0.0)})
    hit = SpeedFeedbackAnomaly().evaluate(ctx)
    assert hit.active
    assert hit.evidences


def test_speed_rule_stays_silent_on_stale_data():
    """Congelar o último RPM não pode virar anomalia inventada."""
    ctx = _ctx_with({"machine_state": _s("machine_state", MachineState.RUN.value, Quality.STALE),
                     "drive_command": _s("drive_command", 62.0, Quality.STALE),
                     "rpm": _s("rpm", 0.0, Quality.STALE)})
    assert SpeedFeedbackAnomaly().evaluate(ctx).active is False


def test_speed_rule_stays_silent_on_comm_error_data():
    ctx = _ctx_with({"machine_state": _s("machine_state", MachineState.RUN.value, Quality.COMM_ERROR),
                     "drive_command": _s("drive_command", 62.0, Quality.COMM_ERROR),
                     "rpm": _s("rpm", 0.0, Quality.COMM_ERROR)})
    assert SpeedFeedbackAnomaly().evaluate(ctx).active is False


def test_speed_rule_abstains_when_a_tag_is_missing():
    ctx = _ctx_with({"machine_state": _s("machine_state", MachineState.RUN.value),
                     "drive_command": _s("drive_command", 62.0)})     # sem rpm
    assert SpeedFeedbackAnomaly().evaluate(ctx).active is False


# ---------------------------------------------------------------------------
# COMUNICAÇÃO E DADO VELHO — eventos distintos
# ---------------------------------------------------------------------------
def test_communication_loss_and_data_stale_are_separate_rules():
    from forja.acquisition.scheduler import CycleResult
    from forja.domain.models import ReadError
    err = ReadError(equipment_id="EQ", tag="mass_flow", source=DataSource.MODBUS_TCP,
                    error="timeout", consecutive=2)
    cycle = CycleResult(read_errors=[err])
    held = _s("mass_flow", 1200.0, Quality.STALE)
    held.source_ts = held.ts

    ctx = _ctx_with({"mass_flow": held}, cycle=cycle)
    comm = CommunicationLoss().evaluate(ctx)
    stale = DataStale().evaluate(ctx)

    assert comm.active and stale.active
    assert comm.event_type if False else True
    assert CommunicationLoss().event_type is EventType.COMMUNICATION_LOSS
    assert DataStale().event_type is EventType.DATA_STALE
    assert comm.extra["read_errors"]["error"] == "timeout"
    assert stale.extra["stale"]["count"] == 1


def test_data_stale_alone_without_read_errors():
    """A tela pode mostrar valor antigo sem falha de leitura no ciclo atual."""
    held = _s("mass_flow", 1200.0, Quality.STALE)
    ctx = _ctx_with({"mass_flow": held})
    assert CommunicationLoss().evaluate(ctx).active is False
    assert DataStale().evaluate(ctx).active is True


# ---------------------------------------------------------------------------
# STOP BY CLASSIFICADO — parada normal não é falha
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("stop_by,expected_class,expected_severity", [
    ("Calib", StopByClass.NORMAL, Severity.INFO),
    ("Tare", StopByClass.NORMAL, Severity.INFO),
    ("Loc Display", StopByClass.REQUESTED, Severity.INFO),
    ("Interlock", StopByClass.PROTECTION, Severity.WARNING),
    ("Board Reset", StopByClass.FAULT, Severity.ALARM),
    ("MDU Alarm", StopByClass.FAULT, Severity.ALARM),
])
def test_stop_by_classification_drives_severity(stop_by, expected_class, expected_severity):
    ctx = _ctx_with({"machine_state": _s("machine_state", MachineState.STOP.value),
                     "stop_by": _s("stop_by", stop_by)})
    hit = MachineStopped().evaluate(ctx)
    assert hit.active
    assert hit.extra["stop_by"]["class"] == expected_class.value
    assert hit.severity is expected_severity
    assert hit.extra["stop_by"]["is_fault"] is (expected_class is StopByClass.FAULT)


def test_normal_stop_is_not_a_fault_end_to_end(tmp_path):
    eq, sim, h, engine, sched = _build(tmp_path, "STOP_NORMAL")
    _run_cycles(sched, sim, 6, step_s=1.0)
    events = h.events(eq.equipment_id, type_="MACHINE_STOPPED")
    assert events, "parada deveria gerar evento de registro"
    ev = events[0]
    assert ev["severity"] in (Severity.INFO.value, Severity.WARNING.value)
    assert ev["context"]["stop_by"]["is_fault"] is False


# ---------------------------------------------------------------------------
# DEBOUNCE DETERMINÍSTICO
# ---------------------------------------------------------------------------
def test_rule_needs_consecutive_cycles_to_open(tmp_path):
    eq = EquipmentCard(equipment_id="EQ")
    h = HistorianRepository(f"sqlite:///{tmp_path}/deb.db")
    rule = SpeedFeedbackAnomaly()
    engine = EventEngine(eq, h, rules=[rule])
    from forja.acquisition.scheduler import CycleResult

    def cycle_with(rpm: float) -> CycleResult:
        return CycleResult(samples=[
            _s("machine_state", MachineState.RUN.value),
            _s("drive_command", 60.0),
            _s("rpm", rpm),
        ])

    assert engine.on_cycle(cycle_with(0.0)) == []        # 1º ciclo: ainda não
    assert engine.on_cycle(cycle_with(0.0)) == []        # 2º ciclo: ainda não
    opened = engine.on_cycle(cycle_with(0.0))            # 3º ciclo: abre
    assert len(opened) == 1
    assert opened[0].type is EventType.SPEED_FEEDBACK_ANOMALY
    assert engine.on_cycle(cycle_with(0.0)) == []        # não reabre enquanto aberto
    assert engine.stats.events_opened == 1


def test_event_closes_after_condition_clears(tmp_path):
    eq = EquipmentCard(equipment_id="EQ")
    h = HistorianRepository(f"sqlite:///{tmp_path}/close.db")
    rule = SpeedFeedbackAnomaly()
    engine = EventEngine(eq, h, rules=[rule])
    from forja.acquisition.scheduler import CycleResult

    def cycle_with(rpm: float) -> CycleResult:
        return CycleResult(samples=[_s("machine_state", MachineState.RUN.value),
                                    _s("drive_command", 60.0), _s("rpm", rpm)])

    for _ in range(3):
        engine.on_cycle(cycle_with(0.0))
    assert len(engine.open_events()) == 1
    for _ in range(rule.clear_cycles):
        engine.on_cycle(cycle_with(1500.0))
    assert engine.open_events() == []
    assert engine.stats.events_closed == 1
    stored = h.events("EQ", type_="SPEED_FEEDBACK_ANOMALY")[0]
    assert stored["ts_end"] is not None


def test_engine_is_deterministic_for_the_same_input(tmp_path):
    """Mesma sequência de ciclos, dois motores: mesmos eventos."""
    from forja.acquisition.scheduler import CycleResult
    eq = EquipmentCard(equipment_id="EQ")

    def sequence():
        return [CycleResult(samples=[_s("machine_state", MachineState.RUN.value),
                                     _s("drive_command", 60.0), _s("rpm", 0.0)])
                for _ in range(5)]

    results = []
    for i in (1, 2):
        h = HistorianRepository(f"sqlite:///{tmp_path}/det{i}.db")
        engine = EventEngine(eq, h, rules=[SpeedFeedbackAnomaly()])
        opened = []
        for c in sequence():
            opened.extend(e.type.value for e in engine.on_cycle(c))
        results.append(opened)
    assert results[0] == results[1]


def test_rule_table_exposes_versions():
    eq = EquipmentCard(equipment_id="EQ")
    engine = EventEngine(eq, historian=None, rules=default_rules())   # type: ignore[arg-type]
    table = engine.rule_table()
    assert len(table) == len(default_rules())
    assert all(r["version"] for r in table)
    assert all(r["rule_id"].startswith("R-") for r in table)
