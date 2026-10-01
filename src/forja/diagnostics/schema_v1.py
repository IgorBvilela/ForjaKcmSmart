"""JSON Schema do contrato Diagnosis v1.0, gerado a partir do modelo Pydantic.

Lei de Hyrum: cada chave e compromisso. O arquivo docs/contracts/diagnosis-v1.0.schema.json
e regenerado por write_schema() e um teste de contrato garante que esta em dia.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from forja.domain import Diagnosis
from forja.version import DIAGNOSIS_SCHEMA_VERSION

SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
SCHEMA_ID = f"forja://contracts/diagnosis-v{DIAGNOSIS_SCHEMA_VERSION}.schema.json"
SCHEMA_FILENAME = f"diagnosis-v{DIAGNOSIS_SCHEMA_VERSION}.schema.json"


def diagnosis_json_schema() -> dict[str, Any]:
    """Schema completo (com $defs) do Diagnosis, em modo de serializacao JSON."""
    schema: dict[str, Any] = Diagnosis.model_json_schema(mode="serialization")
    schema["$schema"] = SCHEMA_DIALECT
    schema["$id"] = SCHEMA_ID
    schema["title"] = "Forja KCM Intelligence — Diagnosis"
    schema["description"] = (
        "Contrato oficial do diagnóstico determinístico. Sete seções, na ordem: RESUMO, "
        "EVIDÊNCIAS, O QUE MUDOU, HIPÓTESES, PRÓXIMAS VERIFICAÇÕES, FONTES, RESSALVAS. "
        "Hipótese nunca é causa. Cada item carrega o próprio nível de evidência."
    )
    schema["x-forja-schema-version"] = DIAGNOSIS_SCHEMA_VERSION
    return schema


def schema_text() -> str:
    return json.dumps(diagnosis_json_schema(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_schema(path: Path) -> None:
    """Grava o schema em `path` (UTF-8, chaves ordenadas, newline final)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(schema_text(), encoding="utf-8")


def schema_is_current(path: Path) -> bool:
    """True se o arquivo em disco e identico ao schema gerado agora."""
    if not path.exists():
        return False
    return path.read_text(encoding="utf-8") == schema_text()
