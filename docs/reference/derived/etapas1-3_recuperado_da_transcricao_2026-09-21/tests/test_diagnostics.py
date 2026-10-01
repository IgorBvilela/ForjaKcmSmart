"""Testes da biblioteca de diagnóstico e da base de casos."""
from __future__ import annotations

from pathlib import Path

import pytest

from forja.diagnostics.cases import cases_for_event, find_case, load_cases
from forja.diagnostics.engine import diagnose, supported_types
from forja.diagnostics.library import LIBRARY, Rank, coverage, entry_for
from forja.events.models import EventType

ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = str(ROOT / "knowledge" / "cases")


# ---------------------------------------------------------------------------
# Cobertura e forma da biblioteca
# ---------------------------------------------------------------------------
def test_every_event_type_has_a_diagnostic_entry():
    c = coverage()
    assert c["missing"] == [], f"tipos de evento sem diagnóstico: {c['missing']}"
    assert c["covered_count"] == len(list(EventType))


def test_every_hypothesis_says_what_confirms_or_rules_it_out():
    for entry in LIBRARY.values():
        for h in entry.hypotheses:
            assert h.discriminator, f"{entry.event_type.value}/{h.id} sem discriminador"
            assert h.statement, f"{entry.event_type.value}/{h.id} sem enunciado"
            assert h.rationale, f"{entry.event_type.value}/{h.id} sem justificativa"


def test_ranking_is_declared_as_investigation_order_not_probability():
    for entry in LIBRARY.values():
        for h in entry.hypotheses:
            assert "não é probabilidade" in h.ranking_basis


def test_every_check_states_what_the_result_means():
    for entry in LIBRARY.values():
        for c in entry.checks:
            assert c.action and c.expected, f"{entry.event_type.value} verificação incompleta"


def test_invasive_checks_never_come_first():
    """Barato e não invasivo primeiro. Mexer em fiação é depois."""
    for entry in LIBRARY.values():
        ordered = sorted(entry.checks, key=lambda c: c.order)
        if ordered and ordered[0].invasive:
            pytest.fail(f"{entry.event_type.value}: a primeira verificação é invasiva")


def test_checks_requiring_stop_carry_a_safety_note():
    for entry in LIBRARY.values():
        for c in entry.checks:
            if c.requires_stop:
                assert c.safety_note, f"{entry.event_type.value} ordem {c.order} sem nota de segurança"


def test_speed_entry_puts_replacing_the_encoder_last():
    """A lição registrada no caso: não trocar o encoder antes de segmentar o sinal."""
    entry = entry_for(EventType.SPEED_FEEDBACK_ANOMALY)
    encoder = next(h for h in entry.hypotheses if h.id == "H-SPEED-ENCODER")
    assert encoder.rank is Rank.LAST
    cable = next(h for h in entry.hypotheses if h.id == "H-SPEED-CABLE")
    assert cable.rank is Rank.FIRST


def test_unknown_event_type_returns_unavailable_instead_of_guessing():
    assert entry_for("NAO_EXISTE") is None
    d = diagnose({"id": 1, "type": "NAO_EXISTE", "context": {}})
    assert d["available"] is False
    assert d["hypotheses"] == []
    assert d["reason"]


def test_supported_types_matches_library():
    assert set(supported_types()) == {t.value for t in LIBRARY}


# ---------------------------------------------------------------------------
# Base de casos
# ---------------------------------------------------------------------------
def test_gtex_case_loads_and_keeps_unknowns():
    case = find_case("GTEX-PHA-KCM-SPEED-001", CASES_DIR)
    assert case is not None
    assert case.confirmed_cause == "UNKNOWN"     # não inventa o que não foi confirmado
    assert case.solution == "UNKNOWN"
    assert case.is_resolved is False
    assert case.symptom
    assert case.lessons


def test_case_matching_is_explicit_not_inferred():
    case = find_case("GTEX-PHA-KCM-SPEED-001", CASES_DIR)
    assert "SPEED_FEEDBACK_ANOMALY" in case.matches_event_types
    matched = cases_for_event("SPEED_FEEDBACK_ANOMALY", CASES_DIR)
    assert any(c.case_id == case.case_id for c in matched)
    # um tipo que o caso não declara não pode casar por semelhança
    assert cases_for_event("INT_CHANNEL_DEGRADED", CASES_DIR) == []


def test_every_case_declares_its_scope():
    for c in load_cases(CASES_DIR):
        assert c.summary()["scope_note"], f"{c.case_id} sem limite de validade"
        assert c.sources, f"{c.case_id} sem fonte"


def test_missing_cases_dir_is_not_a_crash():
    assert load_cases("caminho/que/nao/existe") == []


# ---------------------------------------------------------------------------
# Montagem do diagnóstico
# ---------------------------------------------------------------------------
def _fake_event(**context):
    base = {"rule": {"id": "R-SPEED-001", "version": "1.0", "description": "teste"},
            "evidences": [{"tag": "rpm", "label": "Velocidade do motor", "value": 0.0,
                           "unit": "rpm", "ts": "2026-09-21T12:00:00+00:00", "quality": "GOOD"}],
            "before": {"available": True, "values": {}},
            "changed": {"rpm": {"label": "Velocidade do motor", "unit": "rpm",
                                "before": 700.0, "after": 0.0, "delta": -700.0}}}
    base.update(context)
    return {"id": 1, "type": "SPEED_FEEDBACK_ANOMALY", "severity": "ALARM",
            "ts_start": None, "context": base}


def test_simulated_origin_is_always_flagged():
    ev = _fake_event(evidences=[{"tag": "rpm", "label": "RPM", "value": 0.0,
                                 "quality": "SIMULATED", "ts": None}])
    d = diagnose(ev, cases_dir=CASES_DIR)
    assert d["data_origin"] == "SIMULADO"
    assert any("SIMULAD" in c.upper() for c in d["caveats"])


def test_real_origin_is_not_flagged_as_simulated():
    d = diagnose(_fake_event(), cases_dir=CASES_DIR)
    assert d["data_origin"] == "leitura do equipamento"
    assert not any("SIMULAD" in c.upper() for c in d["caveats"])


def test_missing_before_context_is_declared():
    d = diagnose(_fake_event(before={"available": False, "values": {}}), cases_dir=CASES_DIR)
    assert any("contexto anterior indisponível" in c for c in d["caveats"])


def test_alarm_scope_and_reverse_warning_reach_the_diagnosis():
    ev = _fake_event(alarm={"code": 8, "key": "ANY/KCM/8", "name": "BAD SFT STATUS",
                            "meaning": "x", "evidence_level": "documentado",
                            "scope": "um entre os códigos possíveis",
                            "source": "guia", "reverse_warning": "a recíproca não vale",
                            "universal": False})
    ev["type"] = "KCM_ALARM"
    d = diagnose(ev, cases_dir=CASES_DIR)
    assert any("escopo" in c.lower() for c in d["caveats"])
    assert any("recíproca" in c.lower() for c in d["caveats"])
    top = d["hypotheses"][0]
    assert top["id"] == "H-ALARM-CATALOG"
    assert top["scope"]


def test_unknown_alarm_code_is_declared_in_the_diagnosis():
    ev = _fake_event(alarm={"code": 4242, "key": "WBF/KCM/4242", "name": "CÓDIGO 4242",
                            "meaning": "não catalogado", "evidence_level": "desconhecido",
                            "scope": "sem entrada", "source": "UNKNOWN",
                            "reverse_warning": "nada pode ser concluído", "universal": False})
    ev["type"] = "KCM_ALARM"
    d = diagnose(ev, cases_dir=CASES_DIR)
    assert any("não consta do catálogo" in c for c in d["caveats"])


def test_diagnosis_always_carries_the_read_only_note():
    d = diagnose(_fake_event(), cases_dir=CASES_DIR)
    assert "nunca escreve no controlador" in d["read_only_note"]


def test_diagnosis_does_not_mutate_the_event():
    ev = _fake_event()
    import copy
    snapshot = copy.deepcopy(ev)
    diagnose(ev, cases_dir=CASES_DIR)
    assert ev == snapshot, "o diagnóstico é derivado: não altera o evento gravado"
