"""Catalogo de alarmes com chave composta: 56 so casa com a chave WBF da GTEX."""

from __future__ import annotations

from forja.config.loader import load_alarm_catalog
from forja.domain import UNKNOWN, AlarmKey, EvidenceLevel
from tests.fixtures.synthetic_batches import ALARMS_DIR, gtex_profile

HYPOTHESIS_CODES = ["06", "07", "08", "09", "13", "16", "17", "39", "43", "44", "45", "46", "47"]


def key_for(application: str, code: str, software_version: str = UNKNOWN) -> AlarmKey:
    profile = gtex_profile()
    return AlarmKey(
        manufacturer=profile.controller.manufacturer,
        controller=profile.controller.model,
        application=application,
        software_version=software_version,
        code=code,
    )


def test_catalog_loads_fourteen_definitions() -> None:
    catalog = load_alarm_catalog(ALARMS_DIR)
    assert len(catalog.definitions) == 14
    codes = sorted(d.key.code for d in catalog.definitions)
    # AlarmKey normaliza o código: "06" e "6" são o mesmo alarme.
    assert codes == sorted(str(int(c)) for c in [*HYPOTHESIS_CODES, "56"])


def test_56_matches_only_wbf_key_as_field_observed() -> None:
    catalog = load_alarm_catalog(ALARMS_DIR)
    hit = catalog.lookup(key_for("WBF", "56"))
    assert hit.definition is not None
    assert hit.definition.text == "BELTLOAD LOW"
    assert hit.definition.evidence == EvidenceLevel.FIELD_OBSERVED
    assert hit.definition.source == "foto da tela do KCM, GTEX, 09/2026"
    assert hit.definition.observed_only is True
    assert hit.title_pt == "Pouco material sobre a correia"
    assert hit.qualifier_pt == "Observado nesta aplicação"


def test_56_in_another_application_is_not_catalogued() -> None:
    catalog = load_alarm_catalog(ALARMS_DIR)
    miss = catalog.lookup(key_for("LWF", "56"))
    assert miss.definition is None
    assert miss.candidates == ()
    assert miss.qualifier_pt == "Não catalogado"
    assert "não catalogado" in miss.title_pt
    unknown_app = catalog.lookup(key_for(UNKNOWN, "56"))
    assert unknown_app.definition is None


def test_56_with_known_software_version_is_not_exact_but_candidate() -> None:
    catalog = load_alarm_catalog(ALARMS_DIR)
    result = catalog.lookup(key_for("WBF", "56", software_version="2.5"))
    assert result.definition is None
    assert [c.key.software_version for c in result.candidates] == [UNKNOWN]


def test_hypothesis_codes_are_candidates_never_exact_for_real_profiles() -> None:
    catalog = load_alarm_catalog(ALARMS_DIR)
    for code in HYPOTHESIS_CODES:
        result = catalog.lookup(key_for("WBF", code))
        assert result.definition is None, code
        assert len(result.candidates) == 1, code
        candidate = result.candidates[0]
        assert candidate.evidence == EvidenceLevel.HYPOTHESIS
        assert candidate.source == "referência técnica sem documento identificado"
        assert candidate.key.application == UNKNOWN
        assert candidate.title_pt.upper() != candidate.text.upper()


def test_profile_key_fields_are_used_verbatim() -> None:
    profile = gtex_profile()
    assert profile.application == "WBF"
    assert profile.controller.software_version == UNKNOWN
    key = key_for(profile.application, "56")
    assert key.manufacturer == "Coperion K-Tron"
    assert key.controller == "KCM"
    assert load_alarm_catalog(ALARMS_DIR).lookup(key).definition is not None
