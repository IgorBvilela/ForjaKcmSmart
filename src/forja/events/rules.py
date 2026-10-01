"""Regras deterministicas carregadas de YAML (config/rules/R-*.yaml).

Todo limiar aqui e FORJA_RULE: relativo as referencias do perfil ou ao cenario simulado.
Nenhum numero destas regras e limite do KCM. O codigo interno (BELT_LOAD_LOW) nunca e titulo.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from forja.config.loader import load_yaml_file
from forja.domain import ConfigError, Quality, Severity, SourceRef, is_known_tag

ConditionOp = Literal[
    "gt",
    "lt",
    "between",
    "drop_pct_over_window",
    "rise_pct_over_window",
    "rate_of_change",
    "equals",
    "changed",
    "quality_is",
    "persists_for",
]

ANY_TAG = "*"
"""Em quality_is, '*' significa a pior qualidade do lote inteiro."""

WINDOW_OPS: frozenset[str] = frozenset(
    {"drop_pct_over_window", "rise_pct_over_window", "rate_of_change"}
)
NUMERIC_VALUE_OPS: frozenset[str] = frozenset(
    {"gt", "lt", "between", "drop_pct_over_window", "rise_pct_over_window", "rate_of_change"}
)
RULE_ID_PATTERN = r"^R-[A-Z]+-\d{3}$"
INTERNAL_CODE_PATTERN = r"^[A-Z][A-Z0-9_]{2,63}$"

DEFAULT_ALLOWED_QUALITIES: tuple[Quality, ...] = (
    Quality.GOOD,
    Quality.SIMULATED,
    Quality.UNCERTAIN,
)
THRESHOLD_NOTE_PT = (
    "Limiares definidos pela Forja em relação às referências do perfil ou ao cenário simulado. "
    "Não são limites do KCM."
)


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


class Condition(BaseModel):
    """Uma condicao atomica. As condicoes de uma regra sao combinadas por AND."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tag: str
    op: ConditionOp
    value: float | str | None = None
    value2: float | None = None
    ref_tag: str | None = None
    """Quando presente em gt/lt/between, o limiar vira value x valor atual de ref_tag."""
    window_s: int | None = Field(default=None, gt=0)
    persist_s: int | None = Field(default=None, ge=0)
    """Segundos que a condicao precisa ficar verdadeira antes de contar como atendida."""

    @model_validator(mode="after")
    def _check(self) -> Condition:
        self._check_tags()
        self._check_value()
        return self

    def _check_tags(self) -> None:
        if self.tag == ANY_TAG:
            if self.op != "quality_is":
                raise ValueError("tag '*' só é permitida com op quality_is")
        elif not is_known_tag(self.tag):
            raise ValueError(f"tag semântica desconhecida: {self.tag!r}")
        if self.ref_tag is not None and not is_known_tag(self.ref_tag):
            raise ValueError(f"ref_tag desconhecida: {self.ref_tag!r}")

    def _check_value(self) -> None:
        if self.op in WINDOW_OPS and self.window_s is None:
            raise ValueError(f"op {self.op} exige window_s")
        if self.op in NUMERIC_VALUE_OPS and not _is_number(self.value):
            raise ValueError(f"op {self.op} exige value numérico")
        if self.op == "between" and self.value2 is None:
            raise ValueError("op between exige value2")
        if self.op == "equals" and self.value is None:
            raise ValueError("op equals exige value")
        if self.op == "persists_for" and not self.persist_s:
            raise ValueError("op persists_for exige persist_s > 0")
        if self.op == "quality_is":
            names = {q.value for q in Quality}
            if not isinstance(self.value, str) or self.value not in names:
                raise ValueError(f"op quality_is exige value em {sorted(names)}")


class Rule(BaseModel):
    """Regra Forja. Dispara um Event com codigo interno fixo e titulo em portugues."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = 1
    id: str = Field(pattern=RULE_ID_PATTERN)
    version: int = Field(default=1, ge=1)
    internal_code: str = Field(pattern=INTERNAL_CODE_PATTERN)
    title_pt: str = Field(min_length=3)
    description_pt: str = ""
    severity: Severity
    conditions: list[Condition] = Field(min_length=1)
    allowed_qualities: list[Quality] = Field(
        default_factory=lambda: list(DEFAULT_ALLOWED_QUALITIES)
    )
    """Qualidades que alimentam condicoes de valor. Nunca pode incluir STALE, BAD ou COMM_ERROR."""
    cooldown_s: int = Field(default=0, ge=0)
    close_when_clear_for_s: int = Field(default=30, ge=0)
    diagnosis_ref: str = Field(min_length=1)
    sources: list[SourceRef] = Field(min_length=1)
    summary_template_pt: str = Field(min_length=1)
    context_tags: list[str] = Field(default_factory=list)
    """Tags extras que entram em 'O que mudou' sem participar das condicoes (ex.: mass_flow)."""
    threshold_basis: Literal["FORJA_RULE"] = "FORJA_RULE"
    threshold_note_pt: str = THRESHOLD_NOTE_PT

    @model_validator(mode="after")
    def _check(self) -> Rule:
        if self.title_pt.strip().upper() == self.internal_code:
            raise ValueError("title_pt não pode ser o código interno")
        bad = [q.value for q in self.allowed_qualities if not q.counts_for_rules]
        if bad:
            raise ValueError(f"allowed_qualities não pode conter {bad}")
        unknown = [t for t in self.context_tags if not is_known_tag(t)]
        if unknown:
            raise ValueError(f"context_tags desconhecidas: {unknown}")
        return self

    @property
    def tags(self) -> tuple[str, ...]:
        """Tags observadas pela regra, na ordem das condicoes, sem repeticao e sem '*'."""
        out: list[str] = []
        for c in self.conditions:
            if c.tag != ANY_TAG:
                out.append(c.tag)
            if c.ref_tag is not None:
                out.append(c.ref_tag)
        out.extend(self.context_tags)
        return tuple(dict.fromkeys(out))

    @property
    def persist_s(self) -> int:
        """Maior persistencia exigida entre as condicoes."""
        return max((c.persist_s or 0 for c in self.conditions), default=0)


def _fmt(exc: ValidationError) -> str:
    return "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())


def load_rule(path: Path) -> Rule:
    """Carrega uma regra de um arquivo YAML (safe_load via forja.config.loader)."""
    data = load_yaml_file(path)
    try:
        return Rule.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"{path.name}: {_fmt(exc)}") from exc


def load_rules(dir_: Path) -> list[Rule]:
    """Carrega todas as regras de uma pasta. Ids e codigos internos devem ser unicos."""
    if not dir_.is_dir():
        return []
    rules: list[Rule] = []
    seen_ids: set[str] = set()
    seen_codes: set[str] = set()
    for path in sorted(dir_.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        rule = load_rule(path)
        if rule.id in seen_ids:
            raise ConfigError(f"{path.name}: id de regra duplicado: {rule.id}")
        if rule.internal_code in seen_codes:
            raise ConfigError(f"{path.name}: internal_code duplicado: {rule.internal_code}")
        seen_ids.add(rule.id)
        seen_codes.add(rule.internal_code)
        rules.append(rule)
    return rules
