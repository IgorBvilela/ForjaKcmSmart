"""Regras de aviso antecipado (config/early_warning/EW-*.yaml).

Aviso antecipado é detecção de tendência, desvio em relação ao padrão do próprio equipamento,
mudança gradual e combinação de variáveis. Não é previsão de falha e não é alarme do KCM.
Todo limiar é FORJA_RULE, configurável e acompanhado da nota de evidência; nenhum número vem do
KCM. Os sinais de uma regra são combinados por AND.

Unidade de `min_change`, a mesma convenção do componente "O que mudou":
- variável em kg/h, kg/m ou kg: percentual em relação ao valor de referência;
- variável em %: pontos;
- demais: unidade da própria variável.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from forja.config.loader import load_yaml_file
from forja.domain import ConfigError, Quality, Severity, SourceRef, TagKind, get_tag, is_known_tag
from forja.events.rules import DEFAULT_ALLOWED_QUALITIES, INTERNAL_CODE_PATTERN

EW_ID_PATTERN = r"^EW-[A-Z]+-\d{3}$"

SignalKind = Literal["trend", "deviation", "stable", "near_reference", "state"]
Direction = Literal["up", "down", "any"]
BaselineMode = Literal["window_start", "before_window"]

MAX_WINDOW_S = 7 * 86_400
EW_THRESHOLD_NOTE_PT = (
    "Limiares definidos pela Forja em relação ao comportamento do próprio equipamento. Não são "
    "limites do KCM e precisam ser ajustados depois de observar a operação real."
)

SIGNAL_KIND_PT: dict[str, str] = {
    "trend": "tendência na janela",
    "deviation": "desvio em relação ao padrão",
    "stable": "estabilidade em relação ao padrão",
    "near_reference": "proximidade da referência",
    "state": "estado durante a janela",
}


class Signal(BaseModel):
    """Um sinal observado pela regra. Cada tipo exige os próprios parâmetros."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tag: str
    kind: SignalKind
    direction: Direction = "any"
    """trend e deviation: sentido exigido da variação."""
    min_change: float | None = Field(default=None, gt=0)
    """trend e deviation: variação mínima (percentual, pontos ou unidade; ver o módulo)."""
    max_change: float | None = Field(default=None, gt=0)
    """stable: variação máxima admitida entre o padrão e o trecho recente."""
    min_fit: float = Field(default=0.0, ge=0.0, le=1.0)
    """trend: R² mínimo da reta ajustada. Separa mudança gradual de ruído."""
    ref_tag: str | None = None
    """near_reference: variável de referência (ex.: setpoint para a vazão)."""
    max_deviation_pct: float | None = Field(default=None, gt=0)
    """near_reference: distância máxima, em % da referência, nos últimos `recent_s`."""
    value: float | None = None
    """state: valor esperado da variável discreta."""
    min_fraction: float = Field(default=0.95, gt=0.0, le=1.0)
    """state: fração mínima do tempo com leitura em que a variável ficou em `value`."""

    @model_validator(mode="after")
    def _check(self) -> Signal:
        if not is_known_tag(self.tag):
            raise ValueError(f"tag semântica desconhecida: {self.tag!r}")
        continuous = get_tag(self.tag).kind is TagKind.CONTINUOUS
        if self.kind in ("trend", "deviation"):
            if not continuous:
                raise ValueError(f"{self.kind} exige variável contínua: {self.tag!r}")
            if self.min_change is None:
                raise ValueError(f"{self.kind} exige min_change")
        if self.kind == "stable":
            if not continuous:
                raise ValueError(f"stable exige variável contínua: {self.tag!r}")
            if self.max_change is None:
                raise ValueError("stable exige max_change")
        if self.kind == "near_reference":
            if not continuous:
                raise ValueError(f"near_reference exige variável contínua: {self.tag!r}")
            if self.ref_tag is None or not is_known_tag(self.ref_tag):
                raise ValueError("near_reference exige ref_tag conhecida")
            if self.max_deviation_pct is None:
                raise ValueError("near_reference exige max_deviation_pct")
        if self.kind == "state" and self.value is None:
            raise ValueError("state exige value")
        return self


class EarlyWarningRule(BaseModel):
    """Regra de aviso antecipado. Abre um aviso (evento de origem EARLY_WARNING), nunca alarme."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = 1
    id: str = Field(pattern=EW_ID_PATTERN)
    version: int = Field(default=1, ge=1)
    internal_code: str = Field(pattern=INTERNAL_CODE_PATTERN)
    title_pt: str = Field(min_length=3)
    description_pt: str = ""
    severity: Severity = Severity.ATTENTION
    """INFO ou ATTENTION. Aviso antecipado nunca é CRITICAL: é sinal fraco, não falha."""
    window_s: int = Field(ge=60, le=MAX_WINDOW_S)
    """Janela observada (tendência e estado)."""
    recent_s: int = Field(default=300, ge=10)
    """Trecho final da janela usado como "agora" em desvio e proximidade da referência."""
    baseline: BaselineMode = "window_start"
    """Padrão do desvio: início da janela (mesma duração de recent_s) ou período antes dela."""
    baseline_s: int | None = Field(default=None, ge=60, le=MAX_WINDOW_S)
    evaluate_every_s: int = Field(default=60, ge=10)
    min_coverage: float = Field(default=0.6, gt=0.0, le=1.0)
    """Fração mínima de cada trecho com leitura utilizável. Abaixo disso: dados insuficientes."""
    persist_evaluations: int = Field(default=3, ge=1)
    clear_evaluations: int = Field(default=3, ge=1)
    signals: list[Signal] = Field(min_length=1)
    allowed_qualities: list[Quality] = Field(
        default_factory=lambda: list(DEFAULT_ALLOWED_QUALITIES)
    )
    applications: list[str] = Field(default_factory=list)
    """Aplicações a que a regra se aplica (ex.: WBF). Vazio: todas."""
    diagnosis_ref: str | None = None
    sources: list[SourceRef] = Field(min_length=1)
    threshold_basis: Literal["FORJA_RULE"] = "FORJA_RULE"
    threshold_note_pt: str = EW_THRESHOLD_NOTE_PT

    @model_validator(mode="after")
    def _check(self) -> EarlyWarningRule:
        if self.title_pt.strip().upper() == self.internal_code:
            raise ValueError("title_pt não pode ser o código interno")
        if self.severity is Severity.CRITICAL:
            raise ValueError("aviso antecipado aceita severidade INFO ou ATTENTION")
        bad = [q.value for q in self.allowed_qualities if not q.counts_for_rules]
        if bad:
            raise ValueError(f"allowed_qualities não pode conter {bad}")
        if self.recent_s * 2 > self.window_s:
            raise ValueError("recent_s precisa caber duas vezes na janela (início e fim)")
        if self.baseline == "before_window" and self.baseline_s is None:
            raise ValueError("baseline before_window exige baseline_s")
        return self

    @property
    def tags(self) -> tuple[str, ...]:
        out: list[str] = []
        for signal in self.signals:
            out.append(signal.tag)
            if signal.ref_tag is not None:
                out.append(signal.ref_tag)
        return tuple(dict.fromkeys(out))

    @property
    def lookback_s(self) -> int:
        """Quanto histórico a avaliação lê: a janela e, se for o caso, o padrão anterior a ela."""
        extra = (self.baseline_s or 0) if self.baseline == "before_window" else 0
        return self.window_s + extra

    def applies_to(self, application: str) -> bool:
        return not self.applications or application in self.applications


def _fmt(exc: ValidationError) -> str:
    return "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())


def load_ew_rule(path: Path) -> EarlyWarningRule:
    data = load_yaml_file(path)
    try:
        return EarlyWarningRule.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"{path.name}: {_fmt(exc)}") from exc


def load_ew_rules(dir_: Path) -> list[EarlyWarningRule]:
    """Regras de uma pasta. Pasta ausente: nenhuma regra. Ids e códigos internos únicos."""
    if not dir_.is_dir():
        return []
    rules: list[EarlyWarningRule] = []
    seen_ids: set[str] = set()
    seen_codes: set[str] = set()
    for path in sorted(dir_.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        rule = load_ew_rule(path)
        if rule.id in seen_ids:
            raise ConfigError(f"{path.name}: id de aviso duplicado: {rule.id}")
        if rule.internal_code in seen_codes:
            raise ConfigError(f"{path.name}: internal_code duplicado: {rule.internal_code}")
        seen_ids.add(rule.id)
        seen_codes.add(rule.internal_code)
        rules.append(rule)
    return rules


__all__ = [
    "EW_ID_PATTERN",
    "EW_THRESHOLD_NOTE_PT",
    "SIGNAL_KIND_PT",
    "EarlyWarningRule",
    "Signal",
    "load_ew_rule",
    "load_ew_rules",
]
