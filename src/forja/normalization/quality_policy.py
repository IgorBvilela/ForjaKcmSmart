"""Politica de qualidade por entrada do mapping.

- Tag no plano sem valor no quadro -> COMM_ERROR ("sem leitura"). A tentativa falhou para ela.
- Erro de decodificacao, valor nao numerico ou fora de valid_min/valid_max -> BAD com motivo.
- Senao: entry.quality_for(driver) (SIMULATED no simulador; GOOD se confirmada; UNCERTAIN).
STALE nunca nasce aqui: e estado derivado do relogio, calculado por quem expoe o valor ao vivo.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from forja.domain.mapping import MappingEntry
from forja.domain.quality import Quality

REASON_NO_READ_PT = "sem leitura"
REASON_NOT_NUMERIC_PT = "valor não numérico"


@dataclass(frozen=True)
class Verdict:
    quality: Quality
    reason_pt: str | None = None


class QualityPolicy:
    """Decide a qualidade de uma amostra. Sem estado; pode ser substituida em teste."""

    def for_missing(self) -> Verdict:
        return Verdict(Quality.COMM_ERROR, REASON_NO_READ_PT)

    def for_decode_error(self, message: str) -> Verdict:
        return Verdict(Quality.BAD, f"decodificação falhou: {message}")

    def for_value(self, entry: MappingEntry, driver: str, value: float) -> Verdict:
        if not math.isfinite(value):
            return Verdict(Quality.BAD, REASON_NOT_NUMERIC_PT)
        reason = range_violation_pt(entry, value)
        if reason is not None:
            return Verdict(Quality.BAD, reason)
        return Verdict(entry.quality_for(driver), None)


def range_violation_pt(entry: MappingEntry, value: float) -> str | None:
    """Motivo em portugues se o valor sair de valid_min/valid_max; None se estiver dentro."""
    if entry.valid_min is not None and value < entry.valid_min:
        return f"abaixo do mínimo válido ({_fmt(value)} < {_fmt(entry.valid_min)})"
    if entry.valid_max is not None and value > entry.valid_max:
        return f"acima do máximo válido ({_fmt(value)} > {_fmt(entry.valid_max)})"
    return None


def _fmt(value: float) -> str:
    return f"{value:g}"
