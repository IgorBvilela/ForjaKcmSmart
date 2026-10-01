"""Rotulos em portugues do Brasil (knowledge/i18n/pt_BR.yaml) e renderizacao em texto.

O backend e a fonte dos rotulos: a UI recebe tudo pronto no JSON. O texto gerado aqui e para a
CLI sem --json e para impressao; a UI nunca reparseia este texto.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from forja.config.loader import load_yaml_file
from forja.domain import OFFICIAL_SECTIONS_PT, ConfigError, Diagnosis
from forja.events.what_changed import fmt_number_pt, with_unit

DEFAULT_I18N_FILENAME = "pt_BR.yaml"


class I18nBundle(BaseModel):
    """Conteudo validado de knowledge/i18n/pt_BR.yaml."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = 1
    locale: str = "pt_BR"
    internal_codes: dict[str, str] = Field(default_factory=dict)
    sections: dict[str, str] = Field(default_factory=dict)
    transitions: dict[str, str] = Field(default_factory=dict)
    ops: dict[str, str] = Field(default_factory=dict)
    misc: dict[str, str] = Field(default_factory=dict)


class Translator:
    """Consulta de rotulos. Codigo interno nunca e devolvido como titulo."""

    def __init__(self, bundle: I18nBundle | None = None) -> None:
        self.bundle = bundle or I18nBundle()

    @property
    def locale(self) -> str:
        return self.bundle.locale

    def has_code(self, internal_code: str) -> bool:
        return internal_code in self.bundle.internal_codes

    def code_title(self, internal_code: str, default: str | None = None) -> str:
        """Titulo em portugues de um codigo interno. Sem tradução e sem default: KeyError."""
        title = self.bundle.internal_codes.get(internal_code)
        if title is not None:
            return title
        if default is not None:
            return default
        raise KeyError(f"sem título em português para {internal_code!r}")

    def section(self, key: str) -> str:
        official = dict(OFFICIAL_SECTIONS_PT)
        return self.bundle.sections.get(key, official.get(key, key))

    def transition(self, kind: str) -> str:
        return self.bundle.transitions.get(kind, kind)

    def op(self, op: str) -> str:
        return self.bundle.ops.get(op, op)

    def misc(self, key: str, default: str = "") -> str:
        return self.bundle.misc.get(key, default)


def load_translator(dir_or_file: Path) -> Translator:
    """Carrega knowledge/i18n/pt_BR.yaml (ou o arquivo apontado)."""
    path = dir_or_file / DEFAULT_I18N_FILENAME if dir_or_file.is_dir() else dir_or_file
    data: Any = load_yaml_file(path) or {}
    try:
        return Translator(I18nBundle.model_validate(data))
    except ValidationError as exc:
        msg = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
        raise ConfigError(f"{path.name}: {msg}") from exc


def render_diagnosis_pt(diagnosis: Diagnosis, translator: Translator | None = None) -> str:
    """Texto em portugues com as 7 secoes oficiais, na ordem oficial. Nunca JSON."""
    tr = translator or Translator()
    lines: list[str] = [
        f"Diagnóstico Forja — {diagnosis.summary.title_pt}",
        f"Equipamento: {diagnosis.equipment_id} · Evento: {diagnosis.event_id}",
        f"Gerado em: {diagnosis.generated_at_utc.isoformat()} (UTC)",
        "",
    ]
    for key, _ in OFFICIAL_SECTIONS_PT:
        lines.append(f"== {tr.section(key)} ==")
        lines.extend(_render_section(key, diagnosis))
        lines.append("")
    lines.append(
        "Detalhes técnicos: código interno "
        f"{diagnosis.summary.internal_code} · schema {diagnosis.diagnosis_schema_version} · "
        f"motor {diagnosis.engine_version}"
    )
    return "\n".join(lines)


def _render_section(key: str, d: Diagnosis) -> list[str]:
    if key == "summary":
        return [
            f"{d.summary.title_pt} ({d.summary.severity.label_pt})",
            d.summary.text_pt,
        ]
    if key == "evidence":
        return [
            f"- {e.text_pt} [{e.evidence_level.label_pt}]"
            + (f" (qualidade: {e.quality.label_pt})" if e.quality is not None else "")
            for e in d.evidence
        ] or ["- (sem evidências registradas)"]
    if key == "what_changed":
        out: list[str] = []
        for w in d.what_changed:
            star = " ← primeiro a mudar" if w.changed_first else ""
            out.append(f"- {w.label_pt}: {w.text_pt}{star}")
        return out or ["- (sem variáveis comparadas)"]
    if key == "hypotheses":
        return [
            f"- {h.text_pt} [{h.evidence_level.label_pt}] — {h.rationale_pt}" for h in d.hypotheses
        ] or ["- (nenhuma hipótese cadastrada)"]
    if key == "next_checks":
        out = []
        for c in sorted(d.next_checks, key=lambda c: c.order):
            how = f" Como: {c.how_pt}" if c.how_pt else ""
            out.append(
                f"{c.order}. {c.text_pt}{how} Segurança: {c.safety_pt} "
                f"[{c.evidence_level.label_pt}]"
            )
        return out or ["- (nenhuma verificação cadastrada)"]
    if key == "sources":
        return [
            f"- {s.title}"
            + (f" ({s.reference})" if s.reference else "")
            + f" [{s.evidence_level.label_pt}]"
            for s in d.sources
        ] or ["- (sem fontes)"]
    return [f"- {c.text_pt}" for c in d.caveats]


def format_value_pt(value: float | None, unit: str, decimals: int) -> str:
    """Atalho para a UI/CLI: numero com virgula e unidade."""
    return with_unit(fmt_number_pt(value, decimals), unit)
