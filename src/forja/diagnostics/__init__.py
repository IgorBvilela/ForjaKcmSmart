"""Diagnostico deterministico: biblioteca YAML, motor v1.0, rotulos pt-BR e JSON Schema."""

from forja.diagnostics.engine import DiagnosisEngine, diagnosis_id_for, evidence_level_for_quality
from forja.diagnostics.library import (
    DiagnosisEntry,
    DiagnosisLibrary,
    FieldCase,
    load_case,
    load_cases,
    load_entry,
    load_library,
)
from forja.diagnostics.schema_v1 import (
    SCHEMA_FILENAME,
    diagnosis_json_schema,
    schema_is_current,
    write_schema,
)
from forja.diagnostics.translator import (
    I18nBundle,
    Translator,
    load_translator,
    render_diagnosis_pt,
)

__all__ = [
    "SCHEMA_FILENAME",
    "DiagnosisEngine",
    "DiagnosisEntry",
    "DiagnosisLibrary",
    "FieldCase",
    "I18nBundle",
    "Translator",
    "diagnosis_id_for",
    "diagnosis_json_schema",
    "evidence_level_for_quality",
    "load_case",
    "load_cases",
    "load_entry",
    "load_library",
    "load_translator",
    "render_diagnosis_pt",
    "schema_is_current",
    "write_schema",
]
