"""Linha de comando `forja`: run, diagnose, config validate, doctor, simulate.

Tudo local e offline. `diagnose --json` imprime SOMENTE o JSON v1.0 (o mesmo objeto que a API
devolve em /api/v1/events/{id}/diagnosis). Sem --json imprime texto em português nas sete seções
oficiais e nunca JSON. Relógio só pela porta Clock (SystemClock em produção, FakeClock no demo).

Os outros blocos entram por import tardio, dentro das funções: a CLI carrega rápido e um bloco
ausente vira mensagem em português, não traceback. Nenhum comando escreve no KCM.
"""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import platform
import socket
import sqlite3
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from importlib import metadata
from typing import Any

from forja.config import ConfigStore, ForjaPaths, resolve_paths
from forja.domain import (
    OFFICIAL_SECTIONS_PT,
    ConfigError,
    Diagnosis,
    DriverError,
    EquipmentProfile,
    Event,
    EventTransition,
    ForjaError,
    Mapping,
)
from forja.infra import FakeClock, SystemClock
from forja.version import DIAGNOSIS_SCHEMA_VERSION, __version__

PROG = "forja"
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_INTERRUPTED = 130

MIN_PYTHON = (3, 13)
MAX_SIM_SECONDS = 86_400.0
DEFAULT_SIM_SECONDS = 120.0

REQUIRED_LIBS: tuple[str, ...] = (
    "fastapi",
    "uvicorn",
    "pydantic",
    "sse-starlette",
    "PyYAML",
    "httpx",
)
OPTIONAL_LIBS: tuple[str, ...] = ("pymodbus", "pywin32")


class CliError(ForjaError):
    """Erro de uso ou de ambiente, com texto em português para o terminal."""


def _eprint(*parts: Any) -> None:
    print(*parts, file=sys.stderr)


def _configure_stdout() -> None:
    """UTF-8 na saída mesmo quando redirecionada (Windows usa cp1252 por padrão)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):  # fluxo já em uso ou sem suporte: segue como está
            pass


def _paths(args: argparse.Namespace) -> ForjaPaths:
    return resolve_paths(getattr(args, "home", None))


def _load_store(paths: ForjaPaths) -> ConfigStore:
    try:
        return ConfigStore(paths).load_all()
    except ConfigError as exc:
        raise CliError(f"configuração inválida em {paths.config_dir}: {exc}") from exc


def _is_loopback(host: str) -> bool:
    if host in ("localhost",):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


# ----------------------------------------------------------------------------------------------
# Simulação offline (diagnose --demo e simulate)
# ----------------------------------------------------------------------------------------------


@dataclass
class OfflineRun:
    """Resultado de uma simulação offline com relógio falso."""

    profile: EquipmentProfile
    scenario_code: str
    scenario_title_pt: str
    started_utc: datetime
    seconds_simulated: float
    batches: int = 0
    comm_errors: int = 0
    transitions: list[EventTransition] = field(default_factory=list)
    first_open: Event | None = None
    diagnosis: Diagnosis | None = None


def _pick_simulator_profile(store: ConfigStore, equipment_id: str | None) -> EquipmentProfile:
    """Perfil pedido, ou o primeiro simulador que não é exemplo, ou o primeiro simulador."""
    if equipment_id is not None:
        profile = store.profiles.get(equipment_id)
        if profile is None:
            known = ", ".join(sorted(store.profiles)) or "(nenhum)"
            raise CliError(f"equipamento {equipment_id!r} não encontrado. Conhecidos: {known}")
        if not profile.is_simulated:
            raise CliError(
                f"equipamento {equipment_id!r} usa o driver "
                f"{profile.communication.driver!r}; a simulação offline só roda com 'simulator'."
            )
        return profile
    simulated = [p for p in store.profiles.values() if p.is_simulated]
    if not simulated:
        raise CliError("nenhum perfil com driver 'simulator' em config/equipment.")
    real_first = [p for p in simulated if not p.is_example]
    return (real_first or simulated)[0]


def _parse_scenario(code: str) -> Any:
    # INTEGRACAO: bloco 1 (forja.drivers.simulator.scenarios.scenario_from_text / Scenario).
    try:
        from forja.drivers.simulator.scenarios import Scenario, scenario_from_text
    except ImportError as exc:
        raise CliError("simulador indisponível neste build (bloco drivers ausente).") from exc
    try:
        return scenario_from_text(code)
    except ConfigError as exc:
        names = ", ".join(s.value for s in Scenario)
        raise CliError(f"cenário desconhecido: {code!r}. Válidos: {names}") from exc


def _translator(paths: ForjaPaths) -> Any | None:
    # INTEGRACAO: bloco 4 (forja.diagnostics.translator.load_translator); i18n é opcional.
    i18n_path = paths.knowledge_dir / "i18n" / "pt_BR.yaml"
    if not i18n_path.exists():
        return None
    try:
        from forja.diagnostics.translator import load_translator
    except ImportError:
        return None
    return load_translator(i18n_path)


async def run_offline_simulation(
    paths: ForjaPaths,
    store: ConfigStore,
    profile: EquipmentProfile,
    scenario: Any,
    seconds: float,
    *,
    stop_on_open: bool,
    diagnose: bool,
) -> OfflineRun:
    """Simulador + Normalizer + RuleEngine (+ DiagnosisEngine) com FakeClock, sem rede e sem banco.

    O registro de controles é privado desta execução: nada toca o singleton do processo.
    """
    # INTEGRACAO: assinaturas dos blocos 1 e 4 conferidas no código em 2026-10-01.
    from forja.acquisition.state import reason_pt_for
    from forja.diagnostics.engine import DiagnosisEngine
    from forja.diagnostics.library import load_library
    from forja.drivers.simulator.controls import SimulatorControlRegistry
    from forja.drivers.simulator.driver import SimulatorDriver
    from forja.events.engine import RuleEngine
    from forja.events.rules import load_rules
    from forja.normalization.normalizer import Normalizer, comm_error_batch
    from forja.normalization.plan import ReadPlanCompiler

    mapping: Mapping = store.mapping_for(profile.id)
    demo_profile = profile.model_copy(deep=True)
    demo_profile.communication.options["scenario"] = scenario.value

    clock = FakeClock()
    controls = SimulatorControlRegistry()
    driver = SimulatorDriver(demo_profile, mapping, clock, controls=controls)
    compiler = ReadPlanCompiler()
    plan = compiler.compile(demo_profile, mapping)
    normalizer = Normalizer(compiler=compiler)
    events_cfg = store.config.events
    engine = RuleEngine(
        load_rules(paths.rules_dir),
        store.alarms,
        store.stop_by,
        clock,
        events_cfg.pre_window_s,
        events_cfg.post_window_s,
        events_cfg.buffer_s,
        profiles={demo_profile.id: demo_profile},
    )
    diagnosis_engine = (
        DiagnosisEngine(
            load_library(paths.knowledge_dir / "diagnostics"), clock, _translator(paths)
        )
        if diagnose
        else None
    )

    run = OfflineRun(
        profile=demo_profile,
        scenario_code=str(scenario.value),
        scenario_title_pt=str(getattr(scenario, "title_pt", scenario.value)),
        started_utc=clock.now_utc(),
        seconds_simulated=0.0,
    )
    step = demo_profile.communication.poll_interval_s
    await driver.connect()
    try:
        elapsed = 0.0
        while elapsed <= seconds:
            try:
                frame = await driver.read(plan)
                batch = normalizer.normalize(frame, demo_profile, mapping, clock, plan)
            except DriverError as exc:
                run.comm_errors += 1
                batch = comm_error_batch(demo_profile, mapping, clock, reason_pt_for(exc))
            run.batches += 1
            transitions = await engine.on_batch(batch)
            run.transitions.extend(transitions)
            for t in transitions:
                if t.kind == "OPEN" and run.first_open is None:
                    run.first_open = t.event
                    if diagnosis_engine is not None:
                        run.diagnosis = diagnosis_engine.diagnose(t.event)
            if stop_on_open and run.first_open is not None:
                break
            clock.advance(step)
            elapsed += step
        run.seconds_simulated = elapsed
    finally:
        await driver.disconnect()
    return run


# ----------------------------------------------------------------------------------------------
# diagnose
# ----------------------------------------------------------------------------------------------


def open_core_store(paths: ForjaPaths, clock: Any) -> Any:
    """Core store SQLite (bloco 2): objeto com open()/close()/get_for_event().

    Função de módulo de propósito: o teste a substitui por um repositório em memória.
    """
    # INTEGRACAO: bloco 2 (forja.historian.core_store.SqliteCoreStore(db_path, clock)).
    try:
        from forja.historian.core_store import SqliteCoreStore
    except ImportError as exc:
        raise CliError("core store indisponível neste build (bloco historian ausente).") from exc
    if not paths.core_db.exists():
        raise CliError(f"banco core não encontrado: {paths.core_db}. Rode `forja run` antes.")
    return SqliteCoreStore(paths.core_db, clock)


async def _diagnosis_from_store(paths: ForjaPaths, event_id: str) -> Diagnosis | None:
    store = open_core_store(paths, SystemClock())
    await store.open()
    try:
        found = await store.get_for_event(event_id)
    finally:
        await store.close()
    if found is None:
        return None
    return found if isinstance(found, Diagnosis) else Diagnosis.model_validate(found)


def diagnosis_json_text(diagnosis: Diagnosis) -> str:
    """Exatamente o objeto da API, serializado. Única fonte: forja.api.routers.diagnostics."""
    from forja.api.routers.diagnostics import diagnosis_json

    return json.dumps(diagnosis_json(diagnosis), ensure_ascii=False, indent=2)


def diagnosis_text_pt(diagnosis: Diagnosis, translator: Any | None) -> str:
    """Texto em português nas sete seções. Nunca JSON."""
    try:
        from forja.diagnostics.translator import render_diagnosis_pt
    except ImportError:
        return _render_fallback_pt(diagnosis)
    return render_diagnosis_pt(diagnosis, translator)


def _render_fallback_pt(d: Diagnosis) -> str:
    """Renderização mínima, caso o tradutor do bloco 4 não esteja disponível."""
    lines = [f"Diagnóstico Forja — {d.summary.title_pt}", f"Evento: {d.event_id}", ""]
    for key, title in OFFICIAL_SECTIONS_PT:
        lines.append(f"== {title} ==")
        value = getattr(d, key)
        if key == "summary":
            lines.append(f"{d.summary.title_pt} ({d.summary.severity.label_pt})")
            lines.append(d.summary.text_pt)
        else:
            for item in value:
                text = getattr(item, "text_pt", None) or getattr(item, "title", "")
                lines.append(f"- {text}")
        lines.append("")
    return "\n".join(lines)


def _validate_seconds(seconds: float) -> float:
    if not 0 < seconds <= MAX_SIM_SECONDS:
        raise CliError(
            f"--seconds deve estar entre 1 e {int(MAX_SIM_SECONDS)} (recebido {seconds})."
        )
    return float(seconds)


def cmd_diagnose(args: argparse.Namespace) -> int:
    paths = _paths(args)
    if args.event_id:
        diagnosis = asyncio.run(_diagnosis_from_store(paths, args.event_id))
        if diagnosis is None:
            _eprint(f"Nenhum diagnóstico gravado para o evento {args.event_id!r}.")
            return EXIT_ERROR
    else:
        seconds = _validate_seconds(args.seconds)
        store = _load_store(paths)
        profile = _pick_simulator_profile(store, args.equipment)
        scenario = _parse_scenario(args.demo)
        run = asyncio.run(
            run_offline_simulation(
                paths, store, profile, scenario, seconds, stop_on_open=True, diagnose=True
            )
        )
        if run.diagnosis is None:
            _eprint(
                f"Nenhum evento abriu em {int(run.seconds_simulated)} s simulados no cenário "
                f"{run.scenario_code} ({run.scenario_title_pt}) para {profile.id}. "
                "Tente --seconds maior ou outro cenário."
            )
            return EXIT_ERROR
        diagnosis = run.diagnosis
        if not args.json:
            _eprint(
                f"Simulação offline: {profile.id} · cenário {run.scenario_code} · "
                f"{run.batches} leituras · relógio simulado a partir de "
                f"{run.started_utc.isoformat()}. DADOS SIMULADOS."
            )
    if args.json:
        print(diagnosis_json_text(diagnosis))
    else:
        print(diagnosis_text_pt(diagnosis, _translator(paths)))
    return EXIT_OK


# ----------------------------------------------------------------------------------------------
# simulate
# ----------------------------------------------------------------------------------------------


def cmd_simulate(args: argparse.Namespace) -> int:
    paths = _paths(args)
    seconds = _validate_seconds(args.seconds)
    store = _load_store(paths)
    profile = _pick_simulator_profile(store, args.equipment)
    scenario = _parse_scenario(args.scenario)
    run = asyncio.run(
        run_offline_simulation(
            paths, store, profile, scenario, seconds, stop_on_open=False, diagnose=False
        )
    )
    print(
        f"Simulação offline · {profile.id} ({profile.name}) · cenário {run.scenario_code} "
        f"({run.scenario_title_pt}) · {int(run.seconds_simulated)} s simulados · "
        f"{run.batches} leituras · {run.comm_errors} sem comunicação · DADOS SIMULADOS"
    )
    opened = closed = updated = 0
    for t in run.transitions:
        offset = (t.event.start_utc - run.started_utc).total_seconds()
        if t.kind == "OPEN":
            opened += 1
            print(
                f"[t=+{offset:.0f} s] ABERTO   {t.event.title_pt} "
                f"({t.event.severity.label_pt}) — {t.event.summary_pt}"
            )
        elif t.kind == "CLOSE":
            closed += 1
            end = t.event.end_utc or t.event.start_utc
            end_offset = (end - run.started_utc).total_seconds()
            print(
                f"[t=+{end_offset:.0f} s] FECHADO  {t.event.title_pt} (aberto em t=+{offset:.0f} s)"
            )
        else:
            updated += 1
    if not run.transitions:
        print("Nenhum evento abriu ou fechou neste intervalo.")
    print(f"Resumo: {opened} aberto(s), {closed} fechado(s), {updated} atualização(ões).")
    return EXIT_OK


# ----------------------------------------------------------------------------------------------
# config validate
# ----------------------------------------------------------------------------------------------


def cmd_config_validate(args: argparse.Namespace) -> int:
    paths = _paths(args)
    errors: list[str] = []
    warnings: list[str] = []
    print(f"Pasta: {paths.home}")
    print(f"Config: {paths.config_dir}")
    try:
        store = ConfigStore(paths).load_all()
    except ConfigError as exc:
        print(f"ERRO  {exc}")
        return EXIT_ERROR
    edge = store.config.edge
    print(f"Edge: {edge.name} · bind {edge.bind_host}:{edge.bind_port} · fuso {edge.timezone}")
    if not _is_loopback(edge.bind_host):
        warnings.append(
            f"bind_host {edge.bind_host!r} não é loopback; o padrão do produto é 127.0.0.1"
        )

    _validate_profiles(store, errors)
    print(f"Mappings ({len(store.mappings)}):")
    for m in store.mappings.values():
        print(
            f"  - {m.mapping_id} v{m.version} · driver {m.driver} · "
            f"{len(m.readable_entries)} legíveis / {len(m.unknown_entries)} UNKNOWN"
        )
    rule_codes = _validate_rules(paths, errors)
    n_alarms = len(store.alarms.definitions)
    print(f"Alarmes catalogados: {n_alarms} · STOP BY: {len(store.stop_by.entries)}")
    _validate_knowledge(paths, rule_codes, errors, warnings)

    for w in warnings:
        print(f"AVISO {w}")
    for e in errors:
        print(f"ERRO  {e}")
    if errors:
        print(f"Resultado: {len(errors)} erro(s).")
        return EXIT_ERROR
    print("Resultado: configuração válida.")
    return EXIT_OK


def _validate_profiles(store: ConfigStore, errors: list[str]) -> None:
    print(f"Equipamentos ({len(store.profiles)}):")
    for p in store.profiles.values():
        mapping = store.mappings.get(p.mapping_profile)
        source = "SIMULADO" if p.is_simulated else "EQUIPAMENTO"
        flags = []
        if p.is_example:
            flags.append("exemplo")
        if p.communication.needs_configuration:
            flags.append("requer configuração de campo")
        detail = f" [{', '.join(flags)}]" if flags else ""
        print(
            f"  - {p.id} · {p.name} · driver {p.communication.driver} · "
            f"mapping {p.mapping_profile} · {source}{detail}"
        )
        if mapping is None:
            errors.append(f"{p.id}: mapping {p.mapping_profile!r} ausente")
            continue
        _validate_plan(p, mapping, errors)
        if p.is_simulated:
            try:
                _parse_scenario(str(p.communication.options.get("scenario", "NORMAL_OPERATION")))
            except CliError as exc:
                errors.append(f"{p.id}: {exc}")


def _validate_plan(profile: EquipmentProfile, mapping: Mapping, errors: list[str]) -> None:
    # INTEGRACAO: bloco 1 (forja.normalization.plan.ReadPlanCompiler).
    try:
        from forja.normalization.plan import ReadPlanCompiler
    except ImportError:
        return
    if not profile.is_simulated and profile.communication.needs_configuration:
        return  # sem IP/protocolo não há plano a validar; é esperado até o campo
    try:
        plan = ReadPlanCompiler().compile(profile, mapping)
    except ForjaError as exc:
        errors.append(f"{profile.id}: plano de leitura inválido: {exc}")
        return
    if not plan.blocks:
        errors.append(f"{profile.id}: mapping {mapping.mapping_id} sem entradas legíveis")


def _validate_rules(paths: ForjaPaths, errors: list[str]) -> list[str]:
    # INTEGRACAO: bloco 4 (forja.events.rules.load_rules).
    try:
        from forja.events.rules import load_rules
    except ImportError:
        print("Regras: módulo de eventos indisponível neste build.")
        return []
    try:
        rules = load_rules(paths.rules_dir)
    except ConfigError as exc:
        errors.append(f"regras: {exc}")
        return []
    print(f"Regras ({len(rules)}):")
    for r in rules:
        print(f"  - {r.id} v{r.version} · {r.title_pt} · {r.severity.label_pt} · {r.internal_code}")
    return [r.internal_code for r in rules]


def _validate_knowledge(
    paths: ForjaPaths, rule_codes: list[str], errors: list[str], warnings: list[str]
) -> None:
    # INTEGRACAO: bloco 4 (forja.diagnostics.library.load_library, translator.load_translator).
    try:
        from forja.diagnostics.library import load_library
    except ImportError:
        print("Biblioteca de diagnóstico: módulo indisponível neste build.")
        return
    try:
        library = load_library(paths.knowledge_dir / "diagnostics")
    except ConfigError as exc:
        errors.append(f"biblioteca de diagnóstico: {exc}")
        return
    refs = library.refs()
    print(f"Biblioteca de diagnóstico: {len(refs)} entrada(s)")
    if not refs:
        warnings.append("biblioteca de diagnóstico vazia: diagnósticos usarão a entrada genérica")
    try:
        translator = _translator(paths)
    except ConfigError as exc:
        errors.append(f"i18n: {exc}")
        return
    if translator is None:
        warnings.append("knowledge/i18n/pt_BR.yaml ausente: títulos vêm das regras")
        return
    missing = [c for c in rule_codes if not translator.has_code(c)]
    if missing:
        warnings.append(f"i18n sem título para: {', '.join(missing)}")


# ----------------------------------------------------------------------------------------------
# doctor
# ----------------------------------------------------------------------------------------------


@dataclass
class Check:
    name: str
    ok: bool | None
    detail: str
    required: bool = True

    @property
    def mark(self) -> str:
        if self.ok is None:
            return "info"
        return "ok  " if self.ok else ("ERRO" if self.required else "aviso")


def _sqlite_feature(sql: str) -> bool:
    try:
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute(sql)
        finally:
            conn.close()
    except sqlite3.Error:
        return False
    return True


def _lib_version(dist: str) -> str | None:
    try:
        return metadata.version(dist)
    except metadata.PackageNotFoundError:
        return None


def _port_state(host: str, port: int) -> str:
    """Tenta ocupar a porta local por um instante. Só 127.0.0.1/loopback; nada sai da máquina."""
    if not _is_loopback(host):
        return "não verificado (host não é loopback)"
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind((host, port))
    except OSError:
        return "em uso (o Edge já está rodando?)"
    return "livre"


def _exists_pt(path: Any) -> str:
    return "existe" if path.exists() else "ainda não criado"


def _data_dir_writable(paths: ForjaPaths) -> tuple[bool, str]:
    try:
        paths.data_dir.mkdir(parents=True, exist_ok=True)
        probe = paths.data_dir / ".forja_doctor_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return False, f"{paths.data_dir}: {exc}"
    return True, str(paths.data_dir)


def run_doctor(paths: ForjaPaths) -> list[Check]:
    checks: list[Check] = []
    py = sys.version_info[:3]
    checks.append(
        Check("Python", py >= MIN_PYTHON, f"{platform.python_version()} ({platform.platform()})")
    )
    checks.append(Check("SQLite", True, sqlite3.sqlite_version))
    checks.append(
        Check(
            "SQLite FTS5", _sqlite_feature("CREATE VIRTUAL TABLE t USING fts5(x)"), "busca textual"
        )
    )
    checks.append(Check("SQLite JSON1", _sqlite_feature("SELECT json('{}')"), "funções json"))
    for dist in REQUIRED_LIBS:
        v = _lib_version(dist)
        checks.append(Check(f"lib {dist}", v is not None, v or "não instalada"))
    for dist in OPTIONAL_LIBS:
        v = _lib_version(dist)
        checks.append(Check(f"lib {dist}", v is not None, v or "não instalada", required=False))
    checks.append(Check("pasta config", paths.config_dir.is_dir(), str(paths.config_dir)))
    checks.append(Check("forja.yaml", paths.forja_yaml.exists(), str(paths.forja_yaml)))
    n_profiles = (
        len(list(paths.equipment_dir.glob("*.yaml"))) if paths.equipment_dir.is_dir() else 0
    )
    checks.append(Check("perfis de equipamento", n_profiles > 0, f"{n_profiles} arquivo(s)"))
    checks.append(
        Check(
            "pasta knowledge",
            paths.knowledge_dir.is_dir(),
            str(paths.knowledge_dir),
            required=False,
        )
    )
    ok, detail = _data_dir_writable(paths)
    checks.append(Check("pasta de dados gravável", ok, detail))
    checks.append(Check("banco core", None, f"{paths.core_db} ({_exists_pt(paths.core_db)})"))
    checks.append(
        Check("banco historian", None, f"{paths.historian_db} ({_exists_pt(paths.historian_db)})")
    )
    clock = SystemClock()
    checks.append(Check("relógio UTC", True, clock.now_utc().isoformat()))
    checks.append(Check("relógio monotônico", clock.monotonic_ns() > 0, "disponível"))
    try:
        store = ConfigStore(paths).load_all()
    except ConfigError as exc:
        checks.append(Check("configuração", False, str(exc)))
    else:
        edge = store.config.edge
        checks.append(
            Check(
                "configuração",
                True,
                f"{len(store.profiles)} equipamento(s), {len(store.mappings)} mapping(s)",
            )
        )
        checks.append(
            Check("bind", _is_loopback(edge.bind_host), f"{edge.bind_host}:{edge.bind_port}")
        )
        checks.append(Check("porta", None, _port_state(edge.bind_host, edge.bind_port)))
    return checks


def cmd_doctor(args: argparse.Namespace) -> int:
    paths = _paths(args)
    print(f"Forja KCM Intelligence {__version__} · diagnóstico v{DIAGNOSIS_SCHEMA_VERSION}")
    print(f"Pasta: {paths.home}")
    checks = run_doctor(paths)
    width = max(len(c.name) for c in checks)
    for c in checks:
        print(f"[{c.mark}] {c.name.ljust(width)}  {c.detail}")
    failed = [c for c in checks if c.ok is False and c.required]
    if failed:
        print(f"Resultado: {len(failed)} problema(s) bloqueante(s).")
        return EXIT_ERROR
    print("Resultado: ambiente pronto. Nenhuma verificação usa rede.")
    return EXIT_OK


# ----------------------------------------------------------------------------------------------
# run
# ----------------------------------------------------------------------------------------------


def _first_free_port(host: str, start: int, tries: int = 10) -> int:
    """Devolve a primeira porta livre a partir de start (inclusive). Sem rede: so bind local."""
    for candidate in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, candidate))
            except OSError:
                continue
            return candidate
    raise CliError(f"nenhuma porta livre entre {start} e {start + tries - 1} em {host}")


async def _run_async(paths: ForjaPaths, host: str | None, port: int | None) -> int:
    # INTEGRACAO: bloco 3 (forja.service.runner.build_container/start/stop); build_container
    # importa o bloco 2 (historian SQLite) por dentro.
    try:
        from forja.service.runner import build_container, start, stop
    except ImportError as exc:
        raise CliError(f"serviço indisponível neste build: {exc}") from exc
    import uvicorn

    from forja.api.app import create_app

    try:
        container = await build_container(paths)
    except ImportError as exc:
        raise CliError(f"um bloco do núcleo ainda não existe neste build: {exc}") from exc
    edge = container.store.config.edge
    bind_host = host or edge.bind_host
    bind_port = port or edge.bind_port
    if not _is_loopback(bind_host):
        _eprint(
            f"AVISO: bind em {bind_host!r} expõe o Edge fora desta máquina. "
            "O padrão do produto é 127.0.0.1."
        )
    app = create_app(container)
    free_port = _first_free_port(bind_host, bind_port)
    if free_port != bind_port:
        _eprint(
            f"AVISO: porta {bind_port} ocupada por outro programa nesta máquina; "
            f"usando {free_port}. Para fixar, ajuste edge.bind_port em config/forja.yaml."
        )
        bind_port = free_port
    config = uvicorn.Config(
        app,
        host=bind_host,
        port=bind_port,
        log_level=container.store.config.logging.level.lower(),
        lifespan="on",
    )
    server = uvicorn.Server(config)
    await start(container)
    print(
        f"Forja Edge em http://{bind_host}:{bind_port} · {len(container.store.profiles)} "
        "equipamento(s) · somente leitura · Ctrl+C para parar"
    )
    try:
        await server.serve()
    finally:
        await stop(container)
        print("Forja Edge parado.")
    return EXIT_OK


def cmd_run(args: argparse.Namespace) -> int:
    paths = _paths(args)
    if args.port is not None and not 1024 <= args.port <= 65535:
        raise CliError("--port deve estar entre 1024 e 65535.")
    try:
        return asyncio.run(_run_async(paths, args.host, args.port))
    except KeyboardInterrupt:
        return EXIT_INTERRUPTED


# ----------------------------------------------------------------------------------------------
# parser
# ----------------------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description=(
            "Forja KCM Intelligence: observador somente leitura de controladores KCM. "
            "Nenhum comando altera o equipamento."
        ),
    )
    parser.add_argument("--version", action="version", version=f"{PROG} {__version__}")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--home",
        metavar="PASTA",
        help=(
            "Pasta raiz com config/, knowledge/ e var/. "
            "Padrão: FORJA_HOME ou a raiz do repositório."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="comando")

    run = sub.add_parser("run", parents=[common], help="Sobe o Edge local (API, SSE e aquisição).")
    run.add_argument("--host", help="Endereço de bind. Padrão: edge.bind_host (127.0.0.1).")
    run.add_argument("--port", type=int, help="Porta. Padrão: edge.bind_port (8765).")

    diag = sub.add_parser(
        "diagnose",
        parents=[common],
        help="Gera um diagnóstico: texto em português (padrão) ou JSON v1.0 (--json).",
    )
    source = diag.add_mutually_exclusive_group(required=True)
    source.add_argument("--demo", metavar="CENARIO", help="Roda o simulador offline neste cenário.")
    source.add_argument("--event-id", metavar="ID", help="Lê o diagnóstico gravado deste evento.")
    diag.add_argument("--json", action="store_true", help="Imprime SOMENTE o JSON v1.0.")
    diag.add_argument(
        "--seconds",
        type=float,
        default=DEFAULT_SIM_SECONDS,
        help="Segundos simulados (padrão 120).",
    )
    diag.add_argument("--equipment", metavar="ID", help="Perfil simulado a usar no demo.")

    cfg = sub.add_parser("config", help="Configuração externa (config/ e knowledge/).")
    cfg_sub = cfg.add_subparsers(dest="config_command", required=True, metavar="ação")
    cfg_sub.add_parser(
        "validate", parents=[common], help="Valida perfis, mappings, regras e conhecimento."
    )

    sub.add_parser("doctor", parents=[common], help="Verifica o ambiente local. Sem rede.")

    sim = sub.add_parser(
        "simulate", parents=[common], help="Roda um cenário offline e lista os eventos."
    )
    sim.add_argument("--scenario", required=True, metavar="CENARIO")
    sim.add_argument("--seconds", type=float, default=DEFAULT_SIM_SECONDS)
    sim.add_argument("--equipment", metavar="ID")
    return parser


def _dispatch(args: argparse.Namespace) -> int:
    if args.command == "run":
        return cmd_run(args)
    if args.command == "diagnose":
        return cmd_diagnose(args)
    if args.command == "config":
        return cmd_config_validate(args)
    if args.command == "doctor":
        return cmd_doctor(args)
    if args.command == "simulate":
        return cmd_simulate(args)
    raise CliError(f"comando desconhecido: {args.command!r}")


def main(argv: Sequence[str] | None = None) -> int:
    _configure_stdout()
    args = build_parser().parse_args(argv)
    try:
        return _dispatch(args)
    except CliError as exc:
        _eprint(f"erro: {exc}")
        return EXIT_ERROR
    except ConfigError as exc:
        _eprint(f"erro de configuração: {exc}")
        return EXIT_ERROR
    except KeyboardInterrupt:
        _eprint("interrompido.")
        return EXIT_INTERRUPTED


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
