"""Contrato: o JSON Schema gravado em docs/contracts bate com o modelo Pydantic Diagnosis v1.0."""

from __future__ import annotations

import json
from typing import Any

import pytest

from forja.diagnostics.schema_v1 import (
    SCHEMA_FILENAME,
    diagnosis_json_schema,
    schema_is_current,
    schema_text,
)
from forja.domain import OFFICIAL_SECTIONS_PT, Diagnosis
from tests.fixtures.synthetic_batches import GOLDEN_PATH, SCHEMA_PATH

pytestmark = pytest.mark.contract


def test_schema_file_exists_and_is_current() -> None:
    assert SCHEMA_PATH.name == SCHEMA_FILENAME == "diagnosis-v1.0.schema.json"
    assert SCHEMA_PATH.exists(), "gere com forja.diagnostics.schema_v1.write_schema"
    assert schema_is_current(SCHEMA_PATH), "schema desatualizado: regenerar com write_schema"
    assert SCHEMA_PATH.read_text(encoding="utf-8") == schema_text()


def test_schema_metadata() -> None:
    schema = diagnosis_json_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"] == "forja://contracts/diagnosis-v1.0.schema.json"
    assert schema["x-forja-schema-version"] == "1.0"
    assert schema["title"].startswith("Forja KCM Intelligence")
    assert schema["type"] == "object"
    assert schema.get("additionalProperties") is False


def test_schema_properties_match_pydantic_fields() -> None:
    schema = diagnosis_json_schema()
    assert set(schema["properties"]) == set(Diagnosis.model_fields)
    official = [key for key, _ in OFFICIAL_SECTIONS_PT]
    in_schema = [key for key in schema["properties"] if key in official]
    assert in_schema == official
    for key in official:
        assert key in schema["required"]
    assert "diagnosis_schema_version" in schema["properties"]
    assert schema["properties"]["diagnosis_schema_version"]["default"] == "1.0"


def test_schema_has_no_cause_field() -> None:
    def names(node: Any) -> set[str]:
        out: set[str] = set()
        if isinstance(node, dict):
            if "properties" in node and isinstance(node["properties"], dict):
                out.update(node["properties"].keys())
            for value in node.values():
                out.update(names(value))
        elif isinstance(node, list):
            for value in node:
                out.update(names(value))
        return out

    all_names = names(diagnosis_json_schema())
    assert not any("causa" in n.lower() or "cause" in n.lower() for n in all_names)
    assert "hypotheses" in all_names


def test_golden_validates_against_pydantic_and_schema_defs() -> None:
    assert GOLDEN_PATH.exists(), "golden ausente: tests/unit/test_diagnosis_engine.py o gera"
    data = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    diagnosis = Diagnosis.model_validate(data)
    assert diagnosis.diagnosis_schema_version == "1.0"
    assert set(data) == set(diagnosis_json_schema()["properties"])
    defs = diagnosis_json_schema()["$defs"]
    expected = (
        "DiagnosisSummary",
        "EvidenceItem",
        "Hypothesis",
        "NextCheck",
        "SourceRef",
        "Caveat",
    )
    for name in expected:
        assert name in defs
