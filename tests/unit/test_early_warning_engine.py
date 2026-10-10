"""Motor de aviso antecipado: persistência, encerramento, dados insuficientes e aplicação."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from forja.domain import (
    CommunicationConfig,
    EquipmentProfile,
    EventStatus,
    Quality,
    Series,
    SeriesPoint,
)
from forja.events.ew_engine import EarlyWarningEngine
from forja.events.ew_rules import load_ew_rules
from forja.infra import FakeClock

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]
T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
STEP_S = 10

Fn = Callable[[float], float | None]


class FnSource:
    """Historiador falso: valor de cada tag em função do tempo absoluto (s desde T0)."""

    def __init__(self, fns: dict[str, Fn], quality: Quality = Quality.SIMULATED) -> None:
        self.fns = fns
        self.quality = quality
        self.calls = 0
        self.fail = False

    async def range(
        self, equipment_id: str, tag: str, start: datetime, end: datetime, max_points: int = 2000
    ) -> Series:
        self.calls += 1
        if self.fail:
            raise RuntimeError("historiador indisponível")
        fn = self.fns.get(tag, lambda t: None)
        points = []
        t = start
        while t <= end:
            value = fn((t - T0).total_seconds())
            points.append(
                SeriesPoint(
                    ts_utc=t,
                    value=value,
                    quality=self.quality if value is not None else Quality.COMM_ERROR,
                )
            )
            t += timedelta(seconds=STEP_S)
        return Series(
            equipment_id=equipment_id, tag=tag, resolution="raw", bucket_s=0, points=tuple(points)
        )


def profile(eq: str = "EQ", application: str = "WBF") -> EquipmentProfile:
    return EquipmentProfile(
        id=eq,
        name="Dosador de teste",
        application=application,
        communication=CommunicationConfig(driver="simulator"),
        mapping_profile="simulator_wbf",
    )


def engine(
    clock: FakeClock, *profiles: EquipmentProfile, only: str = "EW-BELTLOAD-001"
) -> EarlyWarningEngine:
    rules = [r for r in load_ew_rules(REPO / "config" / "early_warning") if r.id == only]
    assert rules
    return EarlyWarningEngine(rules, {p.id: p for p in profiles or (profile(),)}, clock)


def drifting(start_drift_s: float) -> dict[str, Fn]:
    """Normal até start_drift_s; depois esforço sobe 1 ponto/min e material cai 1,5%/min."""

    def drive(t: float) -> float:
        return 40.0 + max(0.0, t - start_drift_s) / 60.0

    def load(t: float) -> float:
        return 1.0 * (1 - 0.015 * max(0.0, t - start_drift_s) / 60.0)

    return {
        "drive_command": drive,
        "belt_load": load,
        "mass_flow": lambda t: 1000.0,
        "setpoint": lambda t: 1000.0,
        "machine_state": lambda t: 1.0,
    }


def steady() -> dict[str, Fn]:
    return {
        "drive_command": lambda t: 40.0,
        "belt_load": lambda t: 1.0,
        "mass_flow": lambda t: 1000.0,
        "setpoint": lambda t: 1000.0,
        "machine_state": lambda t: 1.0,
    }


async def run_minutes(
    eng: EarlyWarningEngine, clock: FakeClock, src: FnSource, minutes: int
) -> list:
    out = []
    for _ in range(minutes):
        clock.advance(60)
        out.extend(await eng.evaluate(src, "EQ"))
    return out


async def test_abre_so_depois_das_avaliacoes_seguidas_e_encerra() -> None:
    clock = FakeClock(T0 + timedelta(minutes=15))
    eng = engine(clock)
    src = FnSource(drifting(start_drift_s=15 * 60))
    transitions = await run_minutes(eng, clock, src, 20)
    opens = [t for t in transitions if t.kind == "OPEN"]
    assert len(opens) == 1
    event = opens[0].event
    assert event.origin == "EARLY_WARNING"
    assert event.rule_id == "EW-BELTLOAD-001"
    assert event.quality is Quality.SIMULATED
    assert event.status is EventStatus.OPEN
    assert "Esforço do acionamento" in event.summary_pt
    assert "alarme" not in event.title_pt.lower()
    assert {i.tag for i in event.context.what_changed} == {"drive_command", "belt_load"}
    runtime = eng.runtime("EQ", "EW-BELTLOAD-001")
    assert runtime.open_event is not None
    # abriu só depois de 3 avaliações seguidas atendidas
    first_met = event.start_utc
    open_at = event.context.timeline[-1].ts_utc
    assert (open_at - first_met).total_seconds() == pytest.approx(120)

    # condição some (volta ao normal): encerra depois de 3 avaliações seguidas sem a combinação
    src.fns = steady()
    closes = [t for t in await run_minutes(eng, clock, src, 5) if t.kind == "CLOSE"]
    assert len(closes) == 1
    closed = closes[0].event
    assert closed.status is EventStatus.RESOLVED
    assert closed.end_utc is not None
    assert closed.resolution is not None
    assert "combinação configurada" in closed.resolution.note_pt


async def test_ruido_e_operacao_estavel_nao_abrem_aviso() -> None:
    clock = FakeClock(T0 + timedelta(minutes=15))
    eng = engine(clock)
    transitions = await run_minutes(eng, clock, FnSource(steady()), 30)
    assert transitions == []
    last = eng.runtime("EQ", "EW-BELTLOAD-001").last
    assert last is not None
    assert last.state == "NOT_MET"


async def test_sem_dados_nunca_abre_e_nao_encerra_aviso_aberto() -> None:
    clock = FakeClock(T0 + timedelta(minutes=15))
    eng = engine(clock)
    empty = FnSource({})
    assert await run_minutes(eng, clock, empty, 10) == []
    assert eng.runtime("EQ", "EW-BELTLOAD-001").last.state == "INSUFFICIENT"  # type: ignore[union-attr]

    src = FnSource(drifting(start_drift_s=25 * 60))
    opened = [t for t in await run_minutes(eng, clock, src, 25) if t.kind == "OPEN"]
    assert len(opened) == 1
    # comunicação some: o aviso continua aberto (não dá para confirmar que passou)
    assert [t for t in await run_minutes(eng, clock, empty, 10) if t.kind == "CLOSE"] == []
    assert eng.open_warnings("EQ")


async def test_regra_respeita_aplicacao_do_equipamento() -> None:
    clock = FakeClock(T0 + timedelta(minutes=15))
    eng = engine(clock, profile(application="LWF"))
    src = FnSource(drifting(start_drift_s=15 * 60))
    assert eng.rules_for("EQ") == []
    assert await run_minutes(eng, clock, src, 20) == []
    assert src.calls == 0


async def test_avalia_so_quando_vence_o_intervalo() -> None:
    clock = FakeClock(T0 + timedelta(minutes=15))
    eng = engine(clock)
    src = FnSource(steady())
    await eng.evaluate(src, "EQ")
    calls = src.calls
    clock.advance(20)
    await eng.evaluate(src, "EQ")
    assert src.calls == calls
    clock.advance(45)
    await eng.evaluate(src, "EQ")
    assert src.calls > calls


async def test_esforco_subindo_com_material_estavel_e_outro_aviso() -> None:
    # EW-DRIVE-001 exige material estável: com a correia perdendo material ele não abre
    clock = FakeClock(T0 + timedelta(minutes=30))
    eng = engine(clock, only="EW-DRIVE-001")
    fns = steady()
    fns["drive_command"] = lambda t: 40.0 + max(0.0, t - 30 * 60) / 60.0
    opened = [t for t in await run_minutes(eng, clock, FnSource(fns), 30) if t.kind == "OPEN"]
    assert len(opened) == 1
    assert opened[0].event.rule_id == "EW-DRIVE-001"

    clock2 = FakeClock(T0 + timedelta(minutes=30))
    eng2 = engine(clock2, only="EW-DRIVE-001")
    falling = drifting(start_drift_s=30 * 60)
    assert [
        t for t in await run_minutes(eng2, clock2, FnSource(falling), 30) if t.kind == "OPEN"
    ] == []
