"""Lint de linguagem: o texto para o usuario e portugues simples, sem codigo tecnico.

Vale para todo campo `title` ou `*_pt` (voz do produto). Codigo interno, id de regra, nivel de
evidencia e nome ingles de variavel ficam nos campos tecnicos (internal_code, rule_id, id,
reference, evidence_level), que a UI mostra so em 'Detalhes tecnicos'.

Cobre duas camadas:
1. As sementes em disco: config/rules, config/alarms, knowledge/diagnostics, knowledge/cases e
   knowledge/i18n.
2. O que a Forja GERA: eventos (OPEN/UPDATE/CLOSE) e diagnosticos dos 9 cenarios do simulador
   real no perfil GTEX (DADOS SIMULADOS), pelo mesmo caminho do `forja diagnose --demo`.

Excecao documentada: o texto que o KCM exibe na tela pode aparecer entre aspas depois de
"texto exibido pelo KCM:", porque e o que o mecanico ve no equipamento.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from forja.config.loader import load_yaml_file
from forja.domain import Diagnosis, EventTransition, TagKind, get_tag
from forja.infra.clock import FakeClock
from tests.fixtures.synthetic_batches import (
    ALARMS_DIR,
    CASES_DIR,
    DIAGNOSTICS_DIR,
    I18N_DIR,
    RULES_DIR,
    T0,
    build_engine,
    feed,
    normal_values,
    series,
    simulate_scenario,
    stopped_values,
)

SYNTHETIC_STOP = "SYNTHETIC_STOP"
"""Chave do cenario sintetico de parada (lotes de tests/fixtures/synthetic_batches.py)."""

SCENARIOS: tuple[str, ...] = (
    "NORMAL_OPERATION",
    "BELTLOAD_LOW",
    "RATE_LOW",
    "ENCODER_FAILURE",
    "SFT_FAILURE",
    "DRIVE_COMMAND_HIGH",
    "INT_CHANNEL_DEGRADED",
    "COMMUNICATION_FAILURE",
    "STOP_NORMAL",
)
"""Os 9 cenarios do simulador (Documento Mestre §25)."""

SCENARIOS_THAT_OPEN_EVENTS: frozenset[str] = frozenset(
    {
        "BELTLOAD_LOW",
        "RATE_LOW",
        "ENCODER_FAILURE",
        "DRIVE_COMMAND_HIGH",
        "COMMUNICATION_FAILURE",
    }
)
"""SFT_FAILURE e INT_CHANNEL_DEGRADED ainda nao tem regra; NORMAL_OPERATION nao abre nada.
STOP_NORMAL no simulador ja comeca parado: sem transicao observada, R-STOP-001 nao dispara.
A parada e coberta aqui pelos lotes sinteticos (`synthetic_stop`)."""

TECH_TOKENS = re.compile(
    r"\b(BELT_LOAD_LOW|RATE_DEVIATION|SPEED_FEEDBACK_ANOMALY|DRIVE_COMMAND_HIGH|COMM_DEGRADED"
    r"|MACHINE_STOPPED|FORJA_RULE|HYPOTHESIS|TECHNICAL_OPINION|FIELD_OBSERVED|UNKNOWN"
    r"|Belt Load|Drive Command|Mass Flow|Belt Speed)\b"
)
ISO_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}|\+00:00")
DECIMAL = re.compile(r"\d,\d")
KCM_SCREEN_TEXT = re.compile(r"texto exibido pelo KCM: '[^']*'")
USER_KEYS = ("title",)
USER_SUFFIX = "_pt"

SEED_FILES: tuple[Path, ...] = (
    *sorted(RULES_DIR.glob("*.yaml")),
    *sorted(ALARMS_DIR.glob("*.yaml")),
    *sorted(DIAGNOSTICS_DIR.glob("*.yaml")),
    *sorted(CASES_DIR.glob("*.yaml")),
)


def user_strings(node: Any, key: str | None = None, path: str = "") -> Iterator[tuple[str, str]]:
    """Percorre dicts/listas e devolve (caminho, texto) de todo campo `title` ou `*_pt`."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from user_strings(v, k, f"{path}.{k}" if path else k)
    elif isinstance(node, list | tuple):
        for i, v in enumerate(node):
            yield from user_strings(v, key, f"{path}[{i}]")
    elif isinstance(node, str) and key is not None:
        if key in USER_KEYS or key.endswith(USER_SUFFIX):
            yield path, node


def violations(path: str, text: str) -> list[str]:
    cleaned = KCM_SCREEN_TEXT.sub("", text)
    out: list[str] = []
    hit = TECH_TOKENS.search(cleaned)
    if hit:
        out.append(f"{path}: token técnico {hit.group(0)!r} em {text!r}")
    if ISO_UTC.search(cleaned):
        out.append(f"{path}: horário ISO UTC cru em {text!r}")
    return out


def _is_discrete(tag: str | None) -> bool:
    return tag is not None and get_tag(tag).kind is not TagKind.CONTINUOUS


# --- camada 1: sementes em disco -------------------------------------------------------------


@pytest.mark.parametrize("path", SEED_FILES, ids=lambda p: p.name)
def test_seed_file_texts_are_plain_portuguese(path: Path) -> None:
    data = load_yaml_file(path)
    problems = [v for key, text in user_strings(data) for v in violations(key, text)]
    assert not problems, "\n".join(problems)


def test_i18n_labels_are_plain_portuguese() -> None:
    data = load_yaml_file(I18N_DIR / "pt_BR.yaml")
    labels = [
        (f"{section}.{key}", text)
        for section in ("internal_codes", "sections", "transitions", "ops", "misc")
        for key, text in (data.get(section) or {}).items()
    ]
    assert labels
    problems = [v for key, text in labels for v in violations(key, text)]
    assert not problems, "\n".join(problems)


# --- camada 2: eventos e diagnosticos gerados pelos 9 cenarios --------------------------------


async def _synthetic_stop() -> tuple[list[EventTransition], list[Diagnosis]]:
    """Transicao em operacao -> parado com lotes sinteticos (o simulador real nao a produz)."""
    from forja.diagnostics.engine import DiagnosisEngine
    from forja.diagnostics.library import load_library
    from forja.diagnostics.translator import load_translator

    clock = FakeClock(T0)
    engine = build_engine(clock)
    transitions = await feed(
        engine, [*series(normal_values, 5), *series(stopped_values, 20, first=6)], clock
    )
    diagnosis_engine = DiagnosisEngine(
        load_library(DIAGNOSTICS_DIR), clock, load_translator(I18N_DIR)
    )
    diagnoses = [diagnosis_engine.diagnose(t.event) for t in transitions if t.kind == "OPEN"]
    return transitions, diagnoses


@pytest.fixture(scope="module")
def generated() -> dict[str, tuple[list[EventTransition], list[Diagnosis]]]:
    out = {code: asyncio.run(simulate_scenario(code)) for code in SCENARIOS}
    out[SYNTHETIC_STOP] = asyncio.run(_synthetic_stop())
    return out


def test_scenarios_cover_the_rules(
    generated: dict[str, tuple[list[EventTransition], list[Diagnosis]]],
) -> None:
    opened = {code for code, (transitions, _) in generated.items() if transitions}
    assert opened == SCENARIOS_THAT_OPEN_EVENTS | {SYNTHETIC_STOP}
    for code in opened:
        assert generated[code][1], f"{code}: OPEN sem diagnóstico"
    types = {t.event.type for code in opened for t in generated[code][0]}
    assert types == {
        "BELT_LOAD_LOW",
        "RATE_DEVIATION",
        "SPEED_FEEDBACK_ANOMALY",
        "DRIVE_COMMAND_HIGH",
        "COMM_DEGRADED",
        "MACHINE_STOPPED",
    }


@pytest.mark.parametrize("code", [*SCENARIOS, SYNTHETIC_STOP])
def test_generated_texts_are_plain_portuguese(
    code: str, generated: dict[str, tuple[list[EventTransition], list[Diagnosis]]]
) -> None:
    transitions, diagnoses = generated[code]
    problems: list[str] = []
    for n, t in enumerate(transitions):
        data = t.event.model_dump(mode="json")
        for key, text in user_strings(data, path=f"{code}.event[{n}:{t.kind}]"):
            problems.extend(violations(key, text))
    for n, d in enumerate(diagnoses):
        data = d.model_dump(mode="json")
        for key, text in user_strings(data, path=f"{code}.diagnosis[{n}]"):
            problems.extend(violations(key, text))
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("code", [*sorted(SCENARIOS_THAT_OPEN_EVENTS), SYNTHETIC_STOP])
def test_discrete_values_are_words_never_decimals(
    code: str, generated: dict[str, tuple[list[EventTransition], list[Diagnosis]]]
) -> None:
    """'Estado da máquina: Antes 1,00 · Agora 1,00' nunca mais: discreta e palavra."""
    transitions, diagnoses = generated[code]
    problems: list[str] = []
    for t in transitions:
        ctx = t.event.context
        for item in ctx.what_changed:
            if _is_discrete(item.tag):
                if DECIMAL.search(item.text_pt) or item.delta_kind != "none":
                    problems.append(f"{code} what_changed {item.tag}: {item.text_pt!r}")
                if item.before == item.now:
                    problems.append(f"{code} what_changed {item.tag}: entrou sem mudar de valor")
        for point in ctx.timeline:
            if _is_discrete(point.tag) and DECIMAL.search(point.text_pt):
                problems.append(f"{code} timeline {point.tag}: {point.text_pt!r}")
    for d in diagnoses:
        for ev in d.evidence:
            if _is_discrete(ev.tag) and DECIMAL.search(ev.text_pt):
                problems.append(f"{code} evidence {ev.id}: {ev.text_pt!r}")
    assert not problems, "\n".join(problems)


def test_times_in_text_follow_plant_timezone(
    generated: dict[str, tuple[list[EventTransition], list[Diagnosis]]],
) -> None:
    """T0 = 12:00 UTC -> 09:00 em São Paulo. O texto fala 09:xx; ts_utc segue UTC."""
    _, diagnoses = generated["BELTLOAD_LOW"]
    rule_ev = diagnoses[0].evidence[0]
    assert rule_ev.id == "EV-RULE"
    assert re.search(r"a partir de 09:\d{2}:\d{2}\.$", rule_ev.text_pt), rule_ev.text_pt
    assert rule_ev.ts_utc is not None
    assert rule_ev.ts_utc.hour == 12
    closes = [t.event for t in generated["BELTLOAD_LOW"][0] if t.kind == "CLOSE"]
    for closed in closes:
        assert closed.resolution is not None
        assert re.search(r"a partir de 09:\d{2}:\d{2}\.$", closed.resolution.note_pt)
