"""Catalogo STOP BY: parada nao e falha; sem fonte, tudo e UNKNOWN."""

from __future__ import annotations

from forja.config.loader import load_stop_by_catalog
from forja.domain import UNKNOWN, KnowledgeState, StopByClass
from tests.fixtures.synthetic_batches import STOP_BY_DIR

EXPECTED_LABELS = [
    "Board Reset",
    "Loc Display",
    "Ext Display",
    "ALS Input",
    "DginRunEna",
    "Stop Input",
    "MDU DrvEna",
    "Zero SP",
    "Emptying",
    "Interlock",
    "Calib",
    "Tare",
    "FeedFactBad",
    "MDUInterlock",
    "MDU Alarm",
]


def test_catalog_has_the_fifteen_reference_labels() -> None:
    catalog = load_stop_by_catalog(STOP_BY_DIR)
    assert [e.raw_label for e in catalog.entries] == EXPECTED_LABELS


def test_every_entry_is_unknown_without_source() -> None:
    catalog = load_stop_by_catalog(STOP_BY_DIR)
    for entry in catalog.entries:
        assert entry.classification == StopByClass.UNKNOWN, entry.raw_label
        assert entry.evidence == KnowledgeState.UNKNOWN, entry.raw_label
        assert entry.source == UNKNOWN, entry.raw_label
        assert entry.note_pt


def test_calib_and_tare_are_procedure_candidates() -> None:
    catalog = load_stop_by_catalog(STOP_BY_DIR)
    for label in ("Calib", "Tare"):
        entry = catalog.classify(label)
        assert entry.classification == StopByClass.UNKNOWN
        assert entry.classification.label_pt == "Motivo desconhecido"
        assert entry.note_pt == "candidato a PROCEDURE, decisão do chefe"


def test_classify_is_case_insensitive() -> None:
    catalog = load_stop_by_catalog(STOP_BY_DIR)
    assert catalog.classify("stop input").raw_label == "Stop Input"
    assert catalog.classify("INTERLOCK").classification == StopByClass.UNKNOWN


def test_unknown_or_empty_label_is_unknown() -> None:
    catalog = load_stop_by_catalog(STOP_BY_DIR)
    assert catalog.classify("3").classification == StopByClass.UNKNOWN
    assert catalog.classify("").classification == StopByClass.UNKNOWN
    assert catalog.classify(None).classification == StopByClass.UNKNOWN
    assert catalog.classify("Rotulo Inventado").raw_label == "Rotulo Inventado"


def test_interlock_is_not_promoted_by_its_name() -> None:
    catalog = load_stop_by_catalog(STOP_BY_DIR)
    assert catalog.classify("Interlock").classification != StopByClass.INTERLOCK
