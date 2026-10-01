"""DiagnosisEngine, biblioteca de diagnostico, caso GTEX e i18n."""

from __future__ import annotations

import asyncio
import json
import os

import pytest
from pydantic import ValidationError

from forja.diagnostics.engine import DiagnosisEngine, diagnosis_id_for
from forja.diagnostics.library import (
    DiagnosisEntry,
    DiagnosisLibrary,
    FieldCase,
    load_cases,
    load_library,
)
from forja.diagnostics.translator import load_translator, render_diagnosis_pt
from forja.domain import (
    MANDATORY_CAVEAT_PT,
    OFFICIAL_SECTIONS_PT,
    UNKNOWN,
    Diagnosis,
    Event,
    EventContext,
    EvidenceLevel,
    Hypothesis,
    KnowledgeState,
    NextCheck,
    Quality,
    Severity,
    SourceRef,
)
from forja.events.rules import load_rules
from forja.infra.clock import FakeClock
from tests.fixtures.synthetic_batches import (
    CASES_DIR,
    DIAGNOSTICS_DIR,
    GOLDEN_PATH,
    I18N_DIR,
    RULES_DIR,
    T0,
    at,
    open_beltload_low_event,
)

SPEC_BELTLOAD_PT = (
    "O KCM está aumentando o esforço para tentar compensar a redução de material sobre a correia."
)
SPEC_SPEED_PT = (
    "A máquina apresenta comando de acionamento, mas o sistema deixou de receber feedback de "
    "velocidade."
)
FIELD_SEQUENCE_PT = [
    "alimentação",
    "frequência",
    "cabo",
    "conector",
    "gap",
    "SIB",
    "entrada",
    "PICK UP TEETH",
]


@pytest.fixture(scope="module")
def library() -> DiagnosisLibrary:
    return load_library(DIAGNOSTICS_DIR)


@pytest.fixture(scope="module")
def beltload_event() -> Event:
    _, event, _ = asyncio.run(open_beltload_low_event(FakeClock(T0)))
    return event


@pytest.fixture(scope="module")
def diagnosis(library: DiagnosisLibrary, beltload_event: Event) -> Diagnosis:
    clock = FakeClock(T0)
    clock.set_wall(at(125))
    engine = DiagnosisEngine(library, clock, load_translator(I18N_DIR))
    return engine.diagnose(beltload_event)


def test_seven_sections_in_official_order(diagnosis: Diagnosis) -> None:
    data = json.loads(diagnosis.model_dump_json())
    official = [key for key, _ in OFFICIAL_SECTIONS_PT]
    present = [key for key in data if key in official]
    assert present == official
    assert [label for _, label in OFFICIAL_SECTIONS_PT] == [
        "RESUMO",
        "EVIDÊNCIAS",
        "O QUE MUDOU",
        "HIPÓTESES",
        "PRÓXIMAS VERIFICAÇÕES",
        "FONTES",
        "RESSALVAS",
    ]


def test_schema_version_is_1_0(diagnosis: Diagnosis) -> None:
    assert diagnosis.diagnosis_schema_version == "1.0"
    assert json.loads(diagnosis.model_dump_json())["diagnosis_schema_version"] == "1.0"
    assert diagnosis.engine_version.startswith("forja-")


def test_mandatory_caveat_and_simulated_caveat(diagnosis: Diagnosis) -> None:
    texts = [c.text_pt for c in diagnosis.caveats]
    assert MANDATORY_CAVEAT_PT in texts
    assert any("SIMULADOS" in t for t in texts)
    assert any("regras Forja" in t for t in texts)
    assert any("causa confirmada permanece desconhecida" in t for t in texts)
    # codigo tecnico nao e voz do produto: fica em 'Detalhes tecnicos', nunca na ressalva
    assert not any("UNKNOWN" in t or "FORJA_RULE" in t for t in texts)
    assert len(texts) == len(set(texts))


def test_summary_is_portuguese_with_spec_text(diagnosis: Diagnosis, beltload_event: Event) -> None:
    assert diagnosis.summary.title_pt == "Pouco material sobre a correia"
    assert diagnosis.summary.internal_code == "BELT_LOAD_LOW"
    assert diagnosis.summary.severity == Severity.ATTENTION
    assert SPEC_BELTLOAD_PT in diagnosis.summary.text_pt
    assert diagnosis.summary.text_pt.startswith(beltload_event.summary_pt)
    assert diagnosis.event_id == beltload_event.id
    assert diagnosis.equipment_id == beltload_event.equipment_id
    assert diagnosis.generated_at_utc == at(125)


def test_what_changed_comes_from_event(diagnosis: Diagnosis, beltload_event: Event) -> None:
    assert diagnosis.what_changed == beltload_event.context.what_changed
    assert diagnosis.what_changed[0].tag == "belt_load"
    assert diagnosis.what_changed[0].changed_first is True


def test_evidence_items_follow_quality(diagnosis: Diagnosis) -> None:
    ids = [e.id for e in diagnosis.evidence]
    assert ids[0] == "EV-RULE"
    assert "EV-BELT_LOAD" in ids
    assert "EV-DRIVE_COMMAND" in ids
    assert "EV-KCM-1" in ids
    # estado da maquina nao mudou no cenario: discreta sem mudanca nao vira evidencia
    assert "EV-MACHINE_STATE" not in ids
    for item in diagnosis.evidence:
        if item.tag is not None:
            assert item.quality == Quality.SIMULATED
            assert item.evidence_level == EvidenceLevel.FORJA_RULE
    kcm = next(e for e in diagnosis.evidence if e.id == "EV-KCM-1")
    assert "56" in kcm.text_pt
    alarm = next(e for e in diagnosis.evidence if e.id == "EV-ALARM_CODE")
    assert alarm.text_pt == (
        "Código de alarme: passou de nenhum alarme para alarme 56 (Pouco material sobre a correia)"
    )


def test_rule_evidence_uses_plant_time_and_keeps_utc_in_fields(
    library: DiagnosisLibrary, beltload_event: Event
) -> None:
    """Texto no fuso da planta (America/Sao_Paulo = UTC-3 em janeiro); ts_utc segue ISO UTC."""
    clock = FakeClock(T0)
    clock.set_wall(at(125))
    diagnosis = DiagnosisEngine(library, clock).diagnose(beltload_event)
    rule_ev = diagnosis.evidence[0]
    assert rule_ev.text_pt == (
        "Regra Forja 'Pouco material sobre a correia' atendida a partir de 09:01:53."
    )
    assert rule_ev.ts_utc == beltload_event.start_utc
    assert rule_ev.ts_utc is not None
    assert rule_ev.ts_utc.utcoffset() is not None
    assert "R-BELTLOAD-001" not in rule_ev.text_pt
    assert "T12:" not in rule_ev.text_pt
    assert "+00:00" not in rule_ev.text_pt
    # dia diferente da referencia: o dia entra no texto
    clock.set_wall(at(125 + 86_400))
    later = DiagnosisEngine(library, clock).diagnose(beltload_event)
    assert later.evidence[0].text_pt.endswith("a partir de 1 de jan., 09:01:53.")
    # fuso explicito UTC marca o texto para nao enganar
    utc = DiagnosisEngine(library, FakeClock(at(125)), timezone="UTC").diagnose(beltload_event)
    assert utc.evidence[0].text_pt.endswith("a partir de 12:01:53 UTC.")
    # fuso desconhecido nao derruba o motor: cai para UTC marcado
    odd = DiagnosisEngine(library, FakeClock(at(125)), timezone="Planeta/Inexistente")
    assert odd.diagnose(beltload_event).evidence[0].text_pt.endswith("12:01:53 UTC.")


def test_no_hypothesis_claims_cause(diagnosis: Diagnosis, library: DiagnosisLibrary) -> None:
    for h in diagnosis.hypotheses:
        assert "causa" not in h.text_pt.lower()
        assert h.text_pt.startswith("Comportamento compatível com")
    for entry in library.entries:
        for h in entry.hypotheses:
            assert "causa" not in h.text_pt.lower(), (entry.ref, h.id)
            assert "causa" not in h.rationale_pt.lower(), (entry.ref, h.id)
            assert h.text_pt.startswith("Comportamento compatível com"), (entry.ref, h.id)
            assert h.evidence_level == EvidenceLevel.HYPOTHESIS


def test_library_rejects_hypothesis_with_cause_word() -> None:
    src = SourceRef(
        id="S", kind="opinion", title="o", evidence_level=EvidenceLevel.TECHNICAL_OPINION
    )
    with pytest.raises(ValidationError, match="causa"):
        DiagnosisEntry(
            ref="teste_causa",
            internal_code="TESTE_X",
            title_pt="Teste",
            text_pt="Texto de teste longo.",
            sources=[src],
            hypotheses=[
                Hypothesis(
                    id="H1",
                    text_pt="Comportamento compatível com causa: encoder queimado.",
                    evidence_level=EvidenceLevel.HYPOTHESIS,
                    rationale_pt="x",
                    source_ids=("S",),
                )
            ],
        )


def test_next_checks_ordered_with_plant_safety(
    diagnosis: Diagnosis, library: DiagnosisLibrary
) -> None:
    orders = [c.order for c in diagnosis.next_checks]
    assert orders == sorted(orders)
    assert len(set(orders)) == len(orders)
    for entry in library.entries:
        assert entry.next_checks, entry.ref
        for check in entry.next_checks:
            assert check.safety_pt.startswith("Conforme procedimento da planta"), entry.ref
            assert check.evidence_level == EvidenceLevel.TECHNICAL_OPINION


def test_speed_feedback_checks_follow_field_sequence(library: DiagnosisLibrary) -> None:
    entry = library.get("speed_feedback")
    assert entry.internal_code == "SPEED_FEEDBACK_ANOMALY"
    assert SPEC_SPEED_PT in entry.text_pt
    texts = [c.text_pt for c in sorted(entry.next_checks, key=lambda c: c.order)]
    assert "girando" in texts[0]
    positions = []
    for keyword in FIELD_SEQUENCE_PT:
        idx = next(i for i, t in enumerate(texts) if keyword.lower() in t.lower())
        positions.append(idx)
    assert positions == sorted(positions), positions
    assert any(
        "possível problema na cadeia de feedback de velocidade" in h.text_pt
        for h in entry.hypotheses
    )


def test_evidence_levels_never_exceed_sources(
    diagnosis: Diagnosis, library: DiagnosisLibrary
) -> None:
    def check(items: list[Hypothesis] | list[NextCheck], sources: list[SourceRef]) -> None:
        by_id = {s.id: s for s in sources}
        for item in items:
            if item.source_ids:
                cap = max(by_id[s].evidence_level.strength for s in item.source_ids)
                assert item.evidence_level.strength <= cap, item.id
            else:
                assert not item.evidence_level.is_stronger_than(EvidenceLevel.TECHNICAL_OPINION)

    check(list(diagnosis.hypotheses), list(diagnosis.sources))
    check(list(diagnosis.next_checks), list(diagnosis.sources))
    for entry in library.entries:
        check(entry.hypotheses, entry.sources)
        check(entry.next_checks, entry.sources)
    levels = {s.evidence_level for s in diagnosis.sources}
    assert EvidenceLevel.FORJA_RULE in levels
    assert EvidenceLevel.FIELD_OBSERVED in levels
    assert EvidenceLevel.TECHNICAL_OPINION in levels
    assert EvidenceLevel.MANUFACTURER_DOC not in levels


def test_library_rejects_promoted_hypothesis() -> None:
    src = SourceRef(
        id="S", kind="opinion", title="o", evidence_level=EvidenceLevel.TECHNICAL_OPINION
    )
    with pytest.raises(ValidationError, match="acima da fonte"):
        DiagnosisEntry(
            ref="teste_promocao",
            internal_code="TESTE_Y",
            title_pt="Teste",
            text_pt="Texto de teste longo.",
            sources=[src],
            hypotheses=[
                Hypothesis(
                    id="H1",
                    text_pt="Comportamento compatível com algo.",
                    evidence_level=EvidenceLevel.FIELD_CONFIRMED,
                    rationale_pt="x",
                    source_ids=("S",),
                )
            ],
        )


def test_golden_json_belt_load_low(diagnosis: Diagnosis) -> None:
    data = json.loads(diagnosis.model_dump_json())
    if os.environ.get("FORJA_UPDATE_GOLDEN") == "1":
        GOLDEN_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    assert GOLDEN_PATH.exists(), "rode com FORJA_UPDATE_GOLDEN=1 para gerar o golden"
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    assert data == golden


def test_diagnosis_id_is_deterministic(library: DiagnosisLibrary, beltload_event: Event) -> None:
    engine = DiagnosisEngine(library, FakeClock(T0))
    first = engine.diagnose(beltload_event)
    second = engine.diagnose(beltload_event)
    assert first.diagnosis_id == second.diagnosis_id == diagnosis_id_for(beltload_event.id)


def test_evidence_summary_counts_every_item(diagnosis: Diagnosis) -> None:
    total = (
        len(diagnosis.evidence)
        + len(diagnosis.hypotheses)
        + len(diagnosis.next_checks)
        + len(diagnosis.sources)
    )
    assert sum(diagnosis.evidence_summary.counts.values()) == total
    assert diagnosis.evidence_summary.weakest_level == EvidenceLevel.HYPOTHESIS
    assert diagnosis.evidence_summary.strongest_level == EvidenceLevel.FIELD_OBSERVED


def test_i18n_covers_all_rule_codes_and_library_titles(library: DiagnosisLibrary) -> None:
    translator = load_translator(I18N_DIR)
    rules = load_rules(RULES_DIR)
    assert len(rules) == 6
    for rule in rules:
        assert translator.has_code(rule.internal_code), rule.internal_code
        assert translator.code_title(rule.internal_code) == rule.title_pt
        assert translator.code_title(rule.internal_code) != rule.internal_code
    for entry in library.entries:
        assert translator.code_title(entry.internal_code) == entry.title_pt, entry.ref
    with pytest.raises(KeyError):
        translator.code_title("CODIGO_INEXISTENTE")
    assert translator.section("summary") == "RESUMO"
    assert translator.transition("OPEN") == "Aberto"


def test_library_matches_rules(library: DiagnosisLibrary) -> None:
    assert len(library) == 7
    rules = load_rules(RULES_DIR)
    for rule in rules:
        entry = library.get(rule.diagnosis_ref)
        assert entry.internal_code == rule.internal_code
        assert rule.id in entry.related_rules
        assert any(s.id == f"SRC-RULE-{rule.id}" for s in entry.sources)
    assert library.get("sft_status").internal_code == "SFT_STATUS_CHANGED"
    with pytest.raises(KeyError):
        library.get("nao_existe")


def test_render_text_has_seven_sections_and_is_not_json(diagnosis: Diagnosis) -> None:
    text = render_diagnosis_pt(diagnosis, load_translator(I18N_DIR))
    for _, label in OFFICIAL_SECTIONS_PT:
        assert f"== {label} ==" in text
    assert "← primeiro a mudar" in text
    assert "Detalhes técnicos: código interno BELT_LOAD_LOW" in text
    assert f"evento {diagnosis.event_id}" in text.splitlines()[-1]
    # cabecalho no fuso da planta; nada de ISO UTC cru no texto
    assert "Gerado em: 1 de jan. de 2026, 09:02:05 (horário da planta)" in text
    assert "+00:00" not in text
    assert "T12:" not in text
    assert "Evento:" not in text.splitlines()[1]
    with pytest.raises(json.JSONDecodeError):
        json.loads(text)


def test_fallback_entry_when_library_has_no_match(library: DiagnosisLibrary) -> None:
    event = Event(
        equipment_id="EQ_X",
        type="EVENTO_SEM_ENTRADA",
        title_pt="Evento sem entrada",
        start_utc=at(0),
        severity=Severity.INFO,
        summary_pt="Resumo sintético.",
        rule_id="R-X-001",
        context=EventContext(pre_window_s=60, post_window_s=30),
        quality=Quality.GOOD,
        dedupe_key="EQ_X:R-X-001",
        diagnosis_ref="nao_existe",
    )
    result = DiagnosisEngine(library, FakeClock(T0)).diagnose(event)
    assert result.hypotheses == ()
    assert len(result.next_checks) == 1
    assert any("Sem entrada na biblioteca" in c.text_pt for c in result.caveats)
    assert any(c.text_pt == MANDATORY_CAVEAT_PT for c in result.caveats)
    assert result.summary.title_pt == "Evento sem entrada"


def test_gtex_case_is_field_observed_with_unknown_cause() -> None:
    cases = load_cases(CASES_DIR)
    assert [c.id for c in cases] == ["CASE-2026-09-GTEX-PHA-PO-BASE-VELOCIDADE"]
    case = cases[0]
    assert case.confirmed_cause == UNKNOWN
    assert case.evidence == KnowledgeState.FIELD_OBSERVED
    assert case.plant == "GTEX"
    assert case.application == "WBF"
    values = {m.what_pt: m for m in case.measurements}
    assert "4,9 V" in values["Alimentação do encoder"].value
    assert "0,125 mm" in values["Gap do sensor de velocidade"].value
    assert "não é limite" in values["Alimentação do encoder"].nature_pt.lower()
    assert "não é valor universal" in values["Gap do sensor de velocidade"].nature_pt.lower()
    assert values["PICK UP TEETH"].value == UNKNOWN
    for m in case.measurements:
        assert "threshold" not in m.what_pt.lower()
        assert m.evidence in (KnowledgeState.FIELD_OBSERVED, KnowledgeState.UNKNOWN)
    assert any("RPM indicada em 0" in f for f in case.observed_facts_pt)
    assert "R-SPEED-001" in case.related_rules
    assert all(s.evidence_level == EvidenceLevel.FIELD_OBSERVED for s in case.sources)


def test_case_rejects_short_confirmed_cause() -> None:
    with pytest.raises(ValidationError, match="confirmed_cause"):
        FieldCase(id="CASE-TESTE-X", title_pt="t", confirmed_cause="encoder")
