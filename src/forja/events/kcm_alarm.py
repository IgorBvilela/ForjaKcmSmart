"""Estado do alarme do KCM num instante, pela leitura gravada: a mesma regra da leitura atual.

Ativo quando `alarm_active` vale 1 ou `alarm_code` é diferente de zero. Leitura sem valor ou sem
qualidade utilizável deixa o estado desconhecido, nunca inativo.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from forja.domain import Quality, Sample

ALARM_TAGS: Final = ("alarm_active", "alarm_code")
ACTIVE: Final = "ACTIVE"
INACTIVE: Final = "INACTIVE"
UNKNOWN: Final = "UNKNOWN"
USABLE: Final = frozenset({Quality.GOOD, Quality.SIMULATED, Quality.UNCERTAIN})


def alarm_state(samples: Iterable[Sample]) -> str:
    """Estado do alarme pelas amostras de um mesmo instante."""
    unknown = False
    for s in samples:
        if s.value is None or s.quality not in USABLE:
            unknown = True
            continue
        if (s.tag == "alarm_active" and s.value == 1) or (s.tag == "alarm_code" and s.value != 0):
            return ACTIVE
    return UNKNOWN if unknown else INACTIVE


__all__ = ["ACTIVE", "ALARM_TAGS", "INACTIVE", "UNKNOWN", "alarm_state"]
