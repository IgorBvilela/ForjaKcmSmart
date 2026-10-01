"""Lotes sinteticos para os testes do Bloco 4 (eventos, diagnostico, conhecimento).

Tudo aqui e SIMULATED e nasce de formulas simples. Nenhum numero representa o KCM da GTEX.
Os caminhos apontam para as sementes reais em config/ e knowledge/, que os testes validam.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from forja.config.loader import (
    load_alarm_catalog,
    load_mapping,
    load_profile,
    load_stop_by_catalog,
)
from forja.domain import (
    Diagnosis,
    DriverError,
    EquipmentProfile,
    Event,
    EventTransition,
    Quality,
    Sample,
    SampleBatch,
    worst,
)
from forja.events.engine import RuleEngine
from forja.events.rules import Rule, load_rules
from forja.infra.clock import FakeClock

REPO_ROOT = Path(__file__).resolve().parents[2]
RULES_DIR = REPO_ROOT / "config" / "rules"
ALARMS_DIR = REPO_ROOT / "config" / "alarms"
STOP_BY_DIR = REPO_ROOT / "config" / "stop_by"
EQUIPMENT_DIR = REPO_ROOT / "config" / "equipment"
MAPPINGS_DIR = REPO_ROOT / "config" / "mappings"
DIAGNOSTICS_DIR = REPO_ROOT / "knowledge" / "diagnostics"
CASES_DIR = REPO_ROOT / "knowledge" / "cases"
I18N_DIR = REPO_ROOT / "knowledge" / "i18n"
SCHEMA_PATH = REPO_ROOT / "docs" / "contracts" / "diagnosis-v1.0.schema.json"
GOLDEN_PATH = REPO_ROOT / "tests" / "fixtures" / "diagnosis_golden_belt_load_low.json"

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
EQ = "EQ_TESTE"
GTEX_ID = "GTEX_PHA_PO_BASE"
SOURCE = "sim:teste"

WBF_TAGS: tuple[str, ...] = (
    "machine_state",
    "setpoint",
    "mass_flow",
    "drive_command",
    "rpm",
    "belt_load",
    "alarm_code",
    "alarm_active",
    "stop_by",
)

ValuesFn = Callable[[float], dict[str, float]]


def at(seconds: float, start: datetime = T0) -> datetime:
    return start + timedelta(seconds=seconds)


def make_batch(
    ts: datetime,
    values: Mapping[str, float | None],
    quality: Quality = Quality.SIMULATED,
    equipment_id: str = EQ,
    qualities: Mapping[str, Quality] | None = None,
) -> SampleBatch:
    """Um lote com uma amostra por tag. `qualities` sobrescreve a qualidade de tags especificas."""
    per_tag = dict(qualities or {})
    samples = tuple(
        Sample(
            ts_utc=ts,
            equipment_id=equipment_id,
            tag=tag,
            value=value,
            quality=per_tag.get(tag, quality),
            source=SOURCE,
        )
        for tag, value in values.items()
    )
    return SampleBatch(
        equipment_id=equipment_id,
        ts_utc=ts,
        samples=samples,
        quality=worst([s.quality for s in samples]),
    )


def comm_error_batch(
    ts: datetime, tags: Iterable[str] = WBF_TAGS, equipment_id: str = EQ
) -> SampleBatch:
    """Lote em que a tentativa de leitura falhou: value None, COMM_ERROR (nunca STALE)."""
    samples = tuple(
        Sample(
            ts_utc=ts,
            equipment_id=equipment_id,
            tag=tag,
            value=None,
            quality=Quality.COMM_ERROR,
            source=SOURCE,
            reason_pt="sem leitura",
        )
        for tag in tags
    )
    return SampleBatch(
        equipment_id=equipment_id, ts_utc=ts, samples=samples, quality=Quality.COMM_ERROR
    )


def normal_values(_t: float) -> dict[str, float]:
    """Operacao normal sintetica (referencias do perfil GTEX: 1300 kg/h, 2,0 kg/m, 62 rpm)."""
    return {
        "machine_state": 1,
        "setpoint": 1300.0,
        "mass_flow": 1300.0,
        "drive_command": 50.0,
        "rpm": 62.0,
        "belt_load": 2.0,
        "alarm_code": 0,
        "alarm_active": 0,
        "stop_by": 0,
    }


def beltload_low_values(t: float) -> dict[str, float]:
    """Cenario sintetico de pouco material na correia.

    Estavel ate 60 s. belt_load cai de 2,0 para 1,2 entre 60 e 120 s (primeira a mudar).
    O controlador reage a partir de 65 s: drive_command sobe de 50 para 72 (pontos) e rpm junto;
    mass_flow cai ~2%. alarm_code 56 / alarm_active 1 a partir de 110 s (valor SIMULADO).
    """
    v = normal_values(t)
    if t >= 60:
        frac = min((t - 60) / 60, 1.0)
        v["belt_load"] = round(2.0 - 0.8 * frac, 4)
    if t >= 65:
        frac = min((t - 65) / 60, 1.0)
        v["drive_command"] = round(50 + 22 * frac, 3)
        v["rpm"] = round(62 * v["drive_command"] / 50, 2)
        v["mass_flow"] = round(1300 - 26 * frac, 2)
    if t >= 110:
        v["alarm_code"] = 56
        v["alarm_active"] = 1
    return v


def stopped_values(_t: float) -> dict[str, float]:
    """Maquina parada (machine_state 0). stop_by e inteiro SIMULADO: o catalogo diz UNKNOWN."""
    v = normal_values(_t)
    v.update({"machine_state": 0, "mass_flow": 0.0, "drive_command": 0.0, "rpm": 0.0, "stop_by": 3})
    return v


def series(
    values_fn: ValuesFn,
    seconds: int,
    start: datetime = T0,
    step: int = 1,
    first: int = 0,
    equipment_id: str = EQ,
    quality: Quality = Quality.SIMULATED,
) -> list[SampleBatch]:
    """Lotes a cada `step` s, de `first` ate `seconds` inclusive, com ts relativo a `start`."""
    return [
        make_batch(at(t, start), values_fn(t), quality=quality, equipment_id=equipment_id)
        for t in range(first, seconds + 1, step)
    ]


def gtex_profile() -> EquipmentProfile:
    return load_profile(EQUIPMENT_DIR / "gtex_pha_po_base.yaml")


def seed_rules() -> list[Rule]:
    return load_rules(RULES_DIR)


def build_engine(
    clock: FakeClock,
    rules: Sequence[Rule] | None = None,
    pre_window_s: int = 60,
    post_window_s: int = 30,
    buffer_s: int = 180,
) -> RuleEngine:
    """RuleEngine com as sementes reais (regras, alarmes, STOP BY) e o perfil GTEX registrado."""
    engine = RuleEngine(
        rules if rules is not None else seed_rules(),
        load_alarm_catalog(ALARMS_DIR),
        load_stop_by_catalog(STOP_BY_DIR),
        clock,
        pre_window_s=pre_window_s,
        post_window_s=post_window_s,
        buffer_s=buffer_s,
    )
    engine.set_profile(gtex_profile())
    return engine


async def feed(
    engine: RuleEngine, batches: Iterable[SampleBatch], clock: FakeClock | None = None
) -> list[EventTransition]:
    """Entrega os lotes em ordem. Com FakeClock, o relogio de parede acompanha o ts do lote."""
    out: list[EventTransition] = []
    for batch in batches:
        if clock is not None:
            clock.set_wall(batch.ts_utc)
        out.extend(await engine.on_batch(batch))
    return out


def opens(transitions: Iterable[EventTransition], event_type: str | None = None) -> list[Event]:
    return [
        t.event
        for t in transitions
        if t.kind == "OPEN" and (event_type is None or t.event.type == event_type)
    ]


async def open_beltload_low_event(
    clock: FakeClock | None = None, seconds: int = 125
) -> tuple[RuleEngine, Event, list[EventTransition]]:
    """Roda o cenario sintetico no perfil GTEX e devolve o evento BELT_LOAD_LOW aberto."""
    clock = clock or FakeClock(T0)
    engine = build_engine(clock)
    transitions = await feed(
        engine, series(beltload_low_values, seconds, equipment_id=GTEX_ID), clock
    )
    found = opens(transitions, "BELT_LOAD_LOW")
    if len(found) != 1:
        raise AssertionError(f"esperado 1 OPEN de BELT_LOAD_LOW, veio {len(found)}")
    return engine, found[0], transitions


async def simulate_scenario(
    scenario_code: str,
    seconds: float = 150.0,
    *,
    clock: FakeClock | None = None,
    timezone: str = "America/Sao_Paulo",
) -> tuple[list[EventTransition], list[Diagnosis]]:
    """Simulador REAL + Normalizer + RuleEngine + DiagnosisEngine no perfil GTEX, sem rede e sem
    banco. Mesmo caminho do `forja diagnose --demo`; tudo que sai e SIMULATED.

    Devolve todas as transicoes e um diagnostico por OPEN.
    """
    from forja.acquisition.state import reason_pt_for
    from forja.diagnostics.engine import DiagnosisEngine
    from forja.diagnostics.library import load_library
    from forja.diagnostics.translator import load_translator
    from forja.drivers.simulator.controls import SimulatorControlRegistry
    from forja.drivers.simulator.driver import SimulatorDriver
    from forja.normalization.normalizer import Normalizer, comm_error_batch
    from forja.normalization.plan import ReadPlanCompiler

    clock = clock or FakeClock(T0)
    profile = gtex_profile().model_copy(deep=True)
    profile.communication.options["scenario"] = scenario_code
    mapping = load_mapping(MAPPINGS_DIR / f"{profile.mapping_profile}.yaml")
    driver = SimulatorDriver(profile, mapping, clock, controls=SimulatorControlRegistry())
    compiler = ReadPlanCompiler()
    plan = compiler.compile(profile, mapping)
    normalizer = Normalizer(compiler=compiler)
    engine = RuleEngine(
        seed_rules(),
        load_alarm_catalog(ALARMS_DIR),
        load_stop_by_catalog(STOP_BY_DIR),
        clock,
        profiles={profile.id: profile},
        timezone=timezone,
    )
    diagnosis_engine = DiagnosisEngine(
        load_library(DIAGNOSTICS_DIR), clock, load_translator(I18N_DIR), timezone=timezone
    )
    transitions: list[EventTransition] = []
    diagnoses: list[Diagnosis] = []
    step = profile.communication.poll_interval_s
    await driver.connect()
    try:
        elapsed = 0.0
        while elapsed <= seconds:
            try:
                frame = await driver.read(plan)
                batch = normalizer.normalize(frame, profile, mapping, clock, plan)
            except DriverError as exc:
                batch = comm_error_batch(profile, mapping, clock, reason_pt_for(exc))
            for t in await engine.on_batch(batch):
                transitions.append(t)
                if t.kind == "OPEN":
                    diagnoses.append(diagnosis_engine.diagnose(t.event))
            clock.advance(step)
            elapsed += step
    finally:
        await driver.disconnect()
    return transitions, diagnoses
