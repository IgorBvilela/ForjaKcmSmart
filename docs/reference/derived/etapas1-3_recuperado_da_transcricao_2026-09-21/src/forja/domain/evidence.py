"""Níveis de evidência — o quanto uma afirmação é sustentada, e por quê.

Vocabulário transversal: o catálogo de alarmes, a biblioteca de diagnóstico e
a base de casos usam a MESMA escala. Sem isso, cada módulo inventaria a sua e
o técnico não conseguiria comparar.

A escala, do mais forte para o mais fraco:

    MANUFACTURER_DOC    manual, tabela ou nota técnica do fabricante
    MACHINE_DOC         documento DESTA máquina (ficha, as-built, projeto)
    FIELD_CONFIRMED     ocorrência de campo com causa comprovada
    FIELD_OBSERVED      observado em campo, sem causa comprovada
    FORJA_RULE          decisão ou regra determinística nossa
    TECHNICAL_OPINION   opinião técnica, sem referência documental
    HYPOTHESIS          hipótese em aberto
    UNKNOWN             sem base declarada

REGRA DE PROMOÇÃO
-----------------
MANUFACTURER_DOC e MACHINE_DOC exigem referência RASTREÁVEL: documento +
revisão + seção ou página. Ter o PDF na pasta do projeto não promove nada.

O motivo é prático. Um manual sem revisão não permite conferir se o que está
escrito vale para a máquina que está na frente do técnico: tabelas de alarme,
limites e nomes de parâmetro mudam entre revisões. E uma afirmação que o
técnico não consegue ir conferir na fonte vale, na prática, o mesmo que
opinião — então é assim que ela é rotulada aqui.

`validate_evidence` recusa a promoção sem a referência completa, e um teste
varre o catálogo e a biblioteca inteiros para garantir que ninguém promoveu
uma entrada no impulso.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

UNKNOWN = "UNKNOWN"


class EvidenceLevel(str, Enum):
    MANUFACTURER_DOC = "MANUFACTURER_DOC"
    MACHINE_DOC = "MACHINE_DOC"
    FIELD_CONFIRMED = "FIELD_CONFIRMED"
    FIELD_OBSERVED = "FIELD_OBSERVED"
    FORJA_RULE = "FORJA_RULE"
    TECHNICAL_OPINION = "TECHNICAL_OPINION"
    HYPOTHESIS = "HYPOTHESIS"
    UNKNOWN = "UNKNOWN"


# Força relativa. Usado só para ordenar e para relatório; nunca para decidir
# sozinho o que é verdade.
EVIDENCE_RANK: dict[EvidenceLevel, int] = {
    EvidenceLevel.MANUFACTURER_DOC: 7,
    EvidenceLevel.MACHINE_DOC: 6,
    EvidenceLevel.FIELD_CONFIRMED: 5,
    EvidenceLevel.FIELD_OBSERVED: 4,
    EvidenceLevel.FORJA_RULE: 3,
    EvidenceLevel.TECHNICAL_OPINION: 2,
    EvidenceLevel.HYPOTHESIS: 1,
    EvidenceLevel.UNKNOWN: 0,
}

# Texto curto para a UI. O técnico lê isto, não o nome do enum.
EVIDENCE_LABEL: dict[EvidenceLevel, str] = {
    EvidenceLevel.MANUFACTURER_DOC: "documentado pelo fabricante",
    EvidenceLevel.MACHINE_DOC: "documento desta máquina",
    EvidenceLevel.FIELD_CONFIRMED: "confirmado em campo",
    EvidenceLevel.FIELD_OBSERVED: "observado em campo",
    EvidenceLevel.FORJA_RULE: "regra determinística da Forja",
    EvidenceLevel.TECHNICAL_OPINION: "opinião técnica da Forja",
    EvidenceLevel.HYPOTHESIS: "hipótese em aberto",
    EvidenceLevel.UNKNOWN: "sem base declarada",
}

# Níveis que só podem ser usados com referência rastreável.
REQUIRES_DOC_REFERENCE = {EvidenceLevel.MANUFACTURER_DOC, EvidenceLevel.MACHINE_DOC}


@dataclass(frozen=True)
class DocReference:
    """Referência que o técnico consegue ir conferir.

    Os três campos são obrigatórios para rastreabilidade. `revision` é o que
    costuma faltar, e é justamente o que decide se a informação vale para a
    máquina em questão.
    """
    document: str = UNKNOWN
    revision: str = UNKNOWN
    section: str = UNKNOWN          # seção, parágrafo ou página
    note: str = ""

    @property
    def is_traceable(self) -> bool:
        return all(v and v != UNKNOWN for v in (self.document, self.revision, self.section))

    @property
    def missing(self) -> list[str]:
        """O que falta para esta referência permitir promoção."""
        faltam = []
        if not self.document or self.document == UNKNOWN:
            faltam.append("documento")
        if not self.revision or self.revision == UNKNOWN:
            faltam.append("revisão")
        if not self.section or self.section == UNKNOWN:
            faltam.append("seção ou página")
        return faltam

    def cite(self) -> str:
        if self.document == UNKNOWN:
            return UNKNOWN
        partes = [self.document]
        if self.revision != UNKNOWN:
            partes.append(f"rev. {self.revision}")
        if self.section != UNKNOWN:
            partes.append(self.section)
        return ", ".join(partes)

    def as_dict(self) -> dict:
        return {"document": self.document, "revision": self.revision,
                "section": self.section, "note": self.note,
                "citation": self.cite(), "traceable": self.is_traceable,
                "missing": self.missing}


NO_REFERENCE = DocReference()


def validate_evidence(level: EvidenceLevel, doc_ref: Optional[DocReference],
                      what: str = "entrada") -> None:
    """Recusa promoção sem referência rastreável.

    Levanta ValueError na importação do módulo que errou, não em runtime de
    campo: o erro aparece no primeiro `pytest`, não na frente do cliente.
    """
    if level not in REQUIRES_DOC_REFERENCE:
        return
    if doc_ref is None or not doc_ref.is_traceable:
        faltam = ", ".join(doc_ref.missing) if doc_ref else "documento, revisão, seção ou página"
        raise ValueError(
            f"{what}: nível {level.value} exige referência rastreável e falta {faltam}. "
            f"Ter o documento no projeto não basta — sem revisão e seção o técnico não "
            f"consegue conferir se aquilo vale para esta máquina. "
            f"Use TECHNICAL_OPINION até a referência existir.")


def describe(level: EvidenceLevel, doc_ref: Optional[DocReference] = None) -> dict:
    """Bloco padrão de evidência, igual em qualquer lugar do payload."""
    out = {"evidence_level": level.value,
           "evidence_label": EVIDENCE_LABEL[level],
           "evidence_rank": EVIDENCE_RANK[level],
           "documented_by_manufacturer": level is EvidenceLevel.MANUFACTURER_DOC}
    if doc_ref is not None and doc_ref.document != UNKNOWN:
        out["doc_reference"] = doc_ref.as_dict()
    return out


def weakest(levels: list[EvidenceLevel]) -> EvidenceLevel:
    """O elo mais fraco. Um conjunto não é mais forte que seu pior item."""
    if not levels:
        return EvidenceLevel.UNKNOWN
    return min(levels, key=lambda lv: EVIDENCE_RANK[lv])


def strongest(levels: list[EvidenceLevel]) -> EvidenceLevel:
    if not levels:
        return EvidenceLevel.UNKNOWN
    return max(levels, key=lambda lv: EVIDENCE_RANK[lv])
