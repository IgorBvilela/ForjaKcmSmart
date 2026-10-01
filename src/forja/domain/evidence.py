"""Niveis de evidencia e estados de conhecimento (spec §7 e §29, Documento Mestre §3).

Dois vocabularios distintos:
- KnowledgeState: classificacao de qualquer informacao tecnica (9 estados).
- EvidenceLevel: nivel de evidencia de cada item dentro de um diagnostico (7 niveis).

Nunca promover HYPOTHESIS -> FACT nem UNKNOWN -> FACT sem evidencia.
"""

from __future__ import annotations

from enum import Enum

UNKNOWN = "UNKNOWN"
"""Valor literal usado em todo campo cujo conteudo ainda nao e conhecido."""


class KnowledgeState(str, Enum):
    FACT = "FACT"
    OFFICIAL_DOC = "OFFICIAL_DOC"
    MACHINE_DOC = "MACHINE_DOC"
    FIELD_CONFIRMED = "FIELD_CONFIRMED"
    FIELD_OBSERVED = "FIELD_OBSERVED"
    FORJA_RULE = "FORJA_RULE"
    TECHNICAL_OPINION = "TECHNICAL_OPINION"
    HYPOTHESIS = "HYPOTHESIS"
    UNKNOWN = "UNKNOWN"


class EvidenceLevel(str, Enum):
    """Do mais forte para o mais fraco."""

    MANUFACTURER_DOC = "MANUFACTURER_DOC"
    MACHINE_DOC = "MACHINE_DOC"
    FIELD_CONFIRMED = "FIELD_CONFIRMED"
    FIELD_OBSERVED = "FIELD_OBSERVED"
    FORJA_RULE = "FORJA_RULE"
    TECHNICAL_OPINION = "TECHNICAL_OPINION"
    HYPOTHESIS = "HYPOTHESIS"

    @property
    def strength(self) -> int:
        """Quanto maior, mais forte."""
        return _STRENGTH[self]

    @property
    def label_pt(self) -> str:
        return _LABEL_PT[self]

    def is_stronger_than(self, other: EvidenceLevel) -> bool:
        return self.strength > other.strength


_STRENGTH: dict[EvidenceLevel, int] = {
    EvidenceLevel.MANUFACTURER_DOC: 7,
    EvidenceLevel.MACHINE_DOC: 6,
    EvidenceLevel.FIELD_CONFIRMED: 5,
    EvidenceLevel.FIELD_OBSERVED: 4,
    EvidenceLevel.FORJA_RULE: 3,
    EvidenceLevel.TECHNICAL_OPINION: 2,
    EvidenceLevel.HYPOTHESIS: 1,
}

_LABEL_PT: dict[EvidenceLevel, str] = {
    EvidenceLevel.MANUFACTURER_DOC: "Documentado pelo fabricante",
    EvidenceLevel.MACHINE_DOC: "Documento da máquina",
    EvidenceLevel.FIELD_CONFIRMED: "Confirmado em campo",
    EvidenceLevel.FIELD_OBSERVED: "Observado em campo",
    EvidenceLevel.FORJA_RULE: "Regra Forja",
    EvidenceLevel.TECHNICAL_OPINION: "Opinião técnica",
    EvidenceLevel.HYPOTHESIS: "Hipótese",
}


def weakest(levels: list[EvidenceLevel]) -> EvidenceLevel | None:
    if not levels:
        return None
    return min(levels, key=lambda lv: lv.strength)


def strongest(levels: list[EvidenceLevel]) -> EvidenceLevel | None:
    if not levels:
        return None
    return max(levels, key=lambda lv: lv.strength)


class EvidencePromotionError(ValueError):
    """Um item recebeu nivel de evidencia mais forte do que suas fontes sustentam."""
