"""Qualidade do dado (spec §22, Documento Mestre §15.3).

COMM_ERROR: a tentativa atual de aquisicao falhou.
STALE: o ultimo valor armazenado ficou velho. Nunca confundir os dois.
"""

from __future__ import annotations

from enum import StrEnum


class Quality(StrEnum):
    GOOD = "GOOD"
    SIMULATED = "SIMULATED"
    UNCERTAIN = "UNCERTAIN"
    STALE = "STALE"
    COMM_ERROR = "COMM_ERROR"
    BAD = "BAD"

    @property
    def label_pt(self) -> str:
        return _LABEL_PT[self]

    @property
    def rank(self) -> int:
        """Quanto maior, pior. Usado para 'pior qualidade do lote'."""
        return _RANK[self]

    @property
    def is_usable_value(self) -> bool:
        """Valor pode ser mostrado como numero atual (nao antigo, nao ausente)."""
        return self in (Quality.GOOD, Quality.SIMULATED, Quality.UNCERTAIN)

    @property
    def counts_for_rules(self) -> bool:
        """Regras deterministicas so avaliam leituras reais ou simuladas."""
        return self in (Quality.GOOD, Quality.SIMULATED, Quality.UNCERTAIN)


_RANK: dict[Quality, int] = {
    Quality.GOOD: 0,
    Quality.SIMULATED: 1,
    Quality.UNCERTAIN: 2,
    Quality.STALE: 3,
    Quality.BAD: 4,
    Quality.COMM_ERROR: 5,
}

_LABEL_PT: dict[Quality, str] = {
    Quality.GOOD: "Validado",
    Quality.SIMULATED: "Simulado",
    Quality.UNCERTAIN: "Não validado",
    Quality.STALE: "Valor antigo",
    Quality.COMM_ERROR: "Sem comunicação",
    Quality.BAD: "Inválido",
}


def worst(qualities: list[Quality] | tuple[Quality, ...]) -> Quality:
    """Pior qualidade de um conjunto. Conjunto vazio = COMM_ERROR (nada foi lido)."""
    if not qualities:
        return Quality.COMM_ERROR
    return max(qualities, key=lambda q: q.rank)
