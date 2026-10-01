"""Base de casos: ocorrências reais de campo, estruturadas.

Um caso é memória, não regra. Ele registra o que foi observado numa máquina
concreta, o caminho que o atendimento percorreu e o que ficou aprendido.

O que um caso NÃO é:
- não é tabela de causa e efeito;
- não transforma "aconteceu lá" em "acontece sempre";
- não substitui verificação: ao casar com um evento, entra como referência,
  com o rótulo de confiança que o próprio arquivo declara.

Campos sem fonte ficam UNKNOWN e continuam UNKNOWN.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field

DEFAULT_CASES_DIR = Path("knowledge/cases")


class CaseRecord(BaseModel):
    case_id: str
    equipment: str = "UNKNOWN"
    date: str = "UNKNOWN"
    symptom: str = ""
    matches_event_types: list[str] = Field(default_factory=list)
    signals: dict[str, Any] = Field(default_factory=dict)
    observations: list[str] = Field(default_factory=list)
    diagnostic_path: list[str] = Field(default_factory=list)
    possible_causes: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    confirmed_cause: str = "UNKNOWN"
    solution: str = "UNKNOWN"
    calibration_after: dict[str, Any] = Field(default_factory=dict)
    lessons: list[str] = Field(default_factory=list)
    confidence: str = "UNKNOWN"
    sources: list[str] = Field(default_factory=list)
    scope_note: str = ""

    @property
    def is_resolved(self) -> bool:
        return self.confirmed_cause != "UNKNOWN"

    def summary(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "equipment": self.equipment,
            "date": self.date,
            "symptom": self.symptom,
            "confirmed_cause": self.confirmed_cause,
            "solution": self.solution,
            "confidence": self.confidence,
            "resolved": self.is_resolved,
            "scope_note": self.scope_note or
                          "ocorrência registrada nesta máquina; não generalizar sem verificação",
            "lessons": self.lessons,
            "sources": self.sources,
        }


def load_cases(directory: str | Path = DEFAULT_CASES_DIR) -> list[CaseRecord]:
    """Lê todos os YAML da pasta de casos. Arquivo inválido é ignorado com aviso."""
    path = Path(directory)
    if not path.exists():
        return []
    out: list[CaseRecord] = []
    for f in sorted(path.glob("*.yaml")):
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        try:
            out.append(CaseRecord(**data))
        except Exception:                      # arquivo malformado não derruba o sistema
            import logging
            logging.getLogger("forja.diagnostics").warning("caso ignorado (inválido): %s", f.name)
    return out


@lru_cache(maxsize=8)
def _cached(directory: str) -> tuple[CaseRecord, ...]:
    return tuple(load_cases(directory))


def cases_for_event(event_type: str, directory: str | Path = DEFAULT_CASES_DIR) -> list[CaseRecord]:
    """Casos que declaram casar com este tipo de evento.

    O casamento é EXPLÍCITO: o arquivo do caso diz com que eventos ele se
    relaciona. Não há inferência por semelhança de texto.
    """
    return [c for c in _cached(str(directory)) if event_type in c.matches_event_types]


def find_case(case_id: str, directory: str | Path = DEFAULT_CASES_DIR) -> Optional[CaseRecord]:
    for c in _cached(str(directory)):
        if c.case_id == case_id:
            return c
    return None
