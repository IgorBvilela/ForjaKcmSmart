"""EquipmentManager: uma task por equipamento, isoladas entre si.

Guarda EquipmentState e LiveState fora das tasks (sobrevivem a restart e reload), cria o
driver pelo registry, liga cada loop ao watchdog e expõe status/live/test_read.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from forja.acquisition.backoff import Backoff
from forja.acquisition.live import LiveSnapshot, LiveState
from forja.acquisition.loop import (
    AcquisitionPipeline,
    DriverRegistryPort,
    EquipmentLoop,
    default_pipeline,
)
from forja.acquisition.state import NEEDS_FIELD_CONFIG_PT, EquipmentState, reason_pt_for
from forja.acquisition.test_read import ReadTestResult, run_read_test
from forja.acquisition.watchdog import Watchdog
from forja.config import ConfigStore
from forja.config.loader import load_mapping, load_profile
from forja.domain import (
    Clock,
    ConfigError,
    ConnectionState,
    DriverSupportState,
    EquipmentProfile,
    EquipmentRuntimeStatus,
    EventBus,
    HistorianRepository,
    Mapping,
    ReadOnlyDriverBase,
    UnsupportedDriver,
)

logger = logging.getLogger(__name__)


@dataclass
class _Runner:
    profile: EquipmentProfile
    mapping: Mapping
    driver: ReadOnlyDriverBase
    loop: EquipmentLoop
    task: asyncio.Task[None]


def load_profile_by_id(dir_: Path, equipment_id: str) -> EquipmentProfile:
    """Procura em config/equipment o YAML cujo id é equipment_id (o nome do arquivo não manda)."""
    for p in sorted(dir_.glob("*.yaml")):
        if p.name.startswith("_"):
            continue
        prof = load_profile(p)
        if prof.id == equipment_id:
            return prof
    raise ConfigError(f"perfil {equipment_id} não encontrado em {dir_}")


def load_mapping_by_id(dir_: Path, mapping_id: str) -> Mapping:
    for p in sorted(dir_.glob("*.yaml")):
        if p.name.startswith("_"):
            continue
        m = load_mapping(p)
        if m.mapping_id == mapping_id:
            return m
    raise ConfigError(f"mapping {mapping_id} não encontrado em {dir_}")


class EquipmentManager:
    def __init__(
        self,
        store: ConfigStore,
        registry: DriverRegistryPort,
        historian: HistorianRepository,
        bus: EventBus,
        clock: Clock,
        *,
        pipeline: AcquisitionPipeline | None = None,
        backoff_factory: Callable[[], Backoff] | None = None,
        watchdog: Watchdog | None = None,
        restart_grace_s: float = 2.0,
    ) -> None:
        self._store = store
        self._registry = registry
        self._historian = historian
        self._bus = bus
        self._clock = clock
        self._pipeline = pipeline
        self._backoff_factory: Callable[[], Backoff] = backoff_factory or Backoff
        self._watchdog = watchdog or Watchdog(clock)
        self._watchdog_task: asyncio.Task[None] | None = None
        self._restart_grace_s = restart_grace_s
        self._states: dict[str, EquipmentState] = {}
        self._lives: dict[str, LiveState] = {}
        self._runners: dict[str, _Runner] = {}
        self._stopping = False

    # --- propriedades -----------------------------------------------------------------

    @property
    def pipeline(self) -> AcquisitionPipeline:
        """Pipeline do Bloco 1, importado só quando alguém precisa."""
        if self._pipeline is None:
            self._pipeline = default_pipeline()
        return self._pipeline

    @property
    def watchdog(self) -> Watchdog:
        return self._watchdog

    def equipment_ids(self) -> list[str]:
        return list(self._store.profiles)

    def is_running(self, equipment_id: str) -> bool:
        return equipment_id in self._runners

    def driver_of(self, equipment_id: str) -> ReadOnlyDriverBase | None:
        runner = self._runners.get(equipment_id)
        return runner.driver if runner else None

    def task_of(self, equipment_id: str) -> asyncio.Task[None] | None:
        runner = self._runners.get(equipment_id)
        return runner.task if runner else None

    # --- ciclo de vida ----------------------------------------------------------------

    async def start_all(self) -> None:
        """Sobe todos. Um equipamento com problema não impede os demais de subir."""
        self._stopping = False
        self._ensure_watchdog_task()
        for eid in self.equipment_ids():
            try:
                await self.start(eid)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("aquisição %s: falha ao iniciar; os demais seguem", eid)

    async def stop_all(self, timeout_s: float = 5) -> None:
        """Parada graciosa: cancela todas as tasks e espera até timeout_s (tempo real).

        O watchdog para primeiro: assim nenhum restart em voo relança task depois que os
        loops foram cancelados (ela gravaria num historian já fechado).
        """
        self._stopping = True
        await self._stop_watchdog_task()
        runners = list(self._runners.values())
        for r in runners:
            self._watchdog.unwatch(r.profile.id)
            r.loop.request_stop()
            r.task.cancel()
        if runners:
            _, pending = await asyncio.wait({r.task for r in runners}, timeout=timeout_s)
            for t in pending:
                logger.warning("aquisição: task %s não parou em %.1f s", t.get_name(), timeout_s)
        for r in runners:
            self._runners.pop(r.profile.id, None)
            self._mark_disconnected(r.profile.id)

    async def start(self, equipment_id: str) -> None:
        if equipment_id in self._runners:
            return
        self._stopping = False
        profile = self._profile(equipment_id)
        mapping = self._store.mapping_for(equipment_id)
        state = self._state_for(profile)
        live = LiveState(equipment_id, self._clock, profile.communication.stale_after_s)
        self._lives[equipment_id] = live
        if profile.communication.needs_configuration:
            state.support_state = DriverSupportState.NEEDS_CONFIGURATION
            state.connection = ConnectionState.NOT_CONFIGURED
            state.detail_pt = f"{NEEDS_FIELD_CONFIG_PT}: IP ou protocolo não definidos"
            return
        try:
            driver = self._registry.create(profile, mapping, self._clock)
        except UnsupportedDriver as exc:
            logger.info("aquisição %s: driver não suportado (%s)", equipment_id, exc)
            state.support_state = DriverSupportState.UNSUPPORTED
            state.connection = ConnectionState.NOT_CONFIGURED
            state.detail_pt = NEEDS_FIELD_CONFIG_PT
            return
        except Exception as exc:
            state.connection = ConnectionState.ERROR
            state.detail_pt = f"Falha ao criar o driver: {reason_pt_for(exc)}"
            raise
        state.support_state = self._support_state_of(driver, profile)
        state.connection = ConnectionState.DISCONNECTED
        state.detail_pt = ""
        self._launch(profile, mapping, driver, state, live)
        self._ensure_watchdog_task()

    async def stop(self, equipment_id: str, timeout_s: float = 5) -> None:
        self._watchdog.unwatch(equipment_id)
        runner = self._runners.pop(equipment_id, None)
        if runner is None:
            return
        await self._cancel(runner, timeout_s)
        self._mark_disconnected(equipment_id)

    async def restart(self, equipment_id: str) -> None:
        """Usado pelo watchdog: cancela a task travada (se houver) e recria com driver novo.

        Se o driver não puder ser recriado, o estado fica ERROR e o watchdog tenta de novo no
        próximo ciclo de silêncio (o tick é renovado aqui para não disparar em cascata).
        """
        state = self._states.get(equipment_id)
        if state is None or self._stopping:
            self._watchdog.unwatch(equipment_id)
            return
        runner = self._runners.pop(equipment_id, None)
        profile: EquipmentProfile
        mapping: Mapping
        if runner is not None:
            profile, mapping = runner.profile, runner.mapping
            await self._cancel(runner, self._restart_grace_s)
        else:
            stored = self._store.profiles.get(equipment_id)
            if stored is None:
                self._watchdog.unwatch(equipment_id)
                return
            profile, mapping = stored, self._store.mapping_for(equipment_id)
        state.restart_count += 1
        state.tick(self._clock.monotonic_ns())
        if self._stopping:
            return
        try:
            driver = self._registry.create(profile, mapping, self._clock)
        except Exception:
            logger.exception("aquisição %s: falha ao recriar o driver", equipment_id)
            state.connection = ConnectionState.ERROR
            state.detail_pt = (
                "Falha ao recriar o driver após travamento; o watchdog tentará de novo"
            )
            return
        live = self._lives.get(equipment_id)
        if live is None:
            live = LiveState(equipment_id, self._clock, profile.communication.stale_after_s)
            self._lives[equipment_id] = live
        self._launch(profile, mapping, driver, state, live)

    async def reload(
        self,
        equipment_id: str,
        *,
        profile: EquipmentProfile | None = None,
        mapping: Mapping | None = None,
    ) -> None:
        """Recarrega perfil e mapping de UM equipamento (do disco ou dos argumentos)."""
        self._profile(equipment_id)
        new_profile = profile or load_profile_by_id(self._store.paths.equipment_dir, equipment_id)
        if new_profile.id != equipment_id:
            raise ConfigError(
                f"perfil recarregado tem id {new_profile.id}, esperado {equipment_id}"
            )
        new_mapping = mapping or load_mapping_by_id(
            self._store.paths.mappings_dir, new_profile.mapping_profile
        )
        if new_mapping.mapping_id != new_profile.mapping_profile:
            raise ConfigError(
                f"mapping {new_mapping.mapping_id} não corresponde ao mapping_profile "
                f"{new_profile.mapping_profile} do perfil {equipment_id}"
            )
        old_profile = self._store.profiles[equipment_id]
        old_mapping = self._store.mappings.get(old_profile.mapping_profile)
        await self.stop(equipment_id)
        self._apply_config(new_profile, new_mapping)
        try:
            await self.start(equipment_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "aquisição %s: perfil novo falhou; voltando à configuração anterior", equipment_id
            )
            self._apply_config(old_profile, old_mapping)
            await self.start(equipment_id)
            raise

    def _apply_config(self, profile: EquipmentProfile, mapping: Mapping | None) -> None:
        self._store.profiles[profile.id] = profile
        if mapping is not None:
            self._store.mappings[mapping.mapping_id] = mapping
        state = self._states.get(profile.id)
        if state is not None:
            state.driver = profile.communication.driver

    # --- consultas ---------------------------------------------------------------------

    def profile(self, equipment_id: str) -> EquipmentProfile:
        """Perfil em vigor para o equipamento (o que a aquisição está usando)."""
        return self._profile(equipment_id)

    def status(self, equipment_id: str) -> EquipmentRuntimeStatus:
        profile = self._profile(equipment_id)
        state = self._state_for(profile)
        live = self._lives.get(equipment_id)
        return state.to_status(
            now_mono_ns=self._clock.monotonic_ns(),
            is_stale=live.is_stale if live else False,
            stale_for_s=live.stale_for_s if live else None,
        )

    def statuses(self) -> dict[str, EquipmentRuntimeStatus]:
        return {eid: self.status(eid) for eid in self.equipment_ids()}

    def live(self, equipment_id: str) -> LiveSnapshot:
        profile = self._profile(equipment_id)
        state = self._state_for(profile)
        live = self._lives.get(equipment_id)
        if live is None:
            live = LiveState(equipment_id, self._clock, profile.communication.stale_after_s)
            self._lives[equipment_id] = live
        return live.snapshot(state.connection)

    async def test_read(self, profile: EquipmentProfile, mapping: Mapping) -> ReadTestResult:
        """Driver descartável; não toca nos loops em execução. Nunca escreve."""
        return await run_read_test(
            profile, mapping, registry=self._registry, pipeline=self.pipeline, clock=self._clock
        )

    # --- internos ----------------------------------------------------------------------

    def _profile(self, equipment_id: str) -> EquipmentProfile:
        try:
            return self._store.profiles[equipment_id]
        except KeyError as exc:
            raise KeyError(f"equipamento desconhecido: {equipment_id}") from exc

    def _state_for(self, profile: EquipmentProfile) -> EquipmentState:
        state = self._states.get(profile.id)
        if state is None:
            state = EquipmentState(equipment_id=profile.id, driver=profile.communication.driver)
            self._states[profile.id] = state
        return state

    def _support_state_of(
        self, driver: ReadOnlyDriverBase, profile: EquipmentProfile
    ) -> DriverSupportState:
        try:
            return driver.capabilities().support_state
        except Exception:
            logger.debug("aquisição %s: capabilities() falhou", profile.id)
        try:
            info = self._registry.support().get(profile.communication.driver)
            if info is not None:
                return DriverSupportState(info.state)
        except Exception:
            logger.debug("aquisição %s: registry.support() falhou", profile.id)
        return DriverSupportState.NEEDS_CONFIGURATION

    def _launch(
        self,
        profile: EquipmentProfile,
        mapping: Mapping,
        driver: ReadOnlyDriverBase,
        state: EquipmentState,
        live: LiveState,
    ) -> _Runner:
        loop = EquipmentLoop(
            profile=profile,
            mapping=mapping,
            driver=driver,
            pipeline=self.pipeline,
            historian=self._historian,
            bus=self._bus,
            clock=self._clock,
            state=state,
            live=live,
            backoff=self._backoff_factory(),
        )
        task = asyncio.create_task(loop.run(), name=f"forja-acq-{profile.id}")
        runner = _Runner(profile=profile, mapping=mapping, driver=driver, loop=loop, task=task)
        self._runners[profile.id] = runner
        self._watchdog.watch(
            profile.id,
            poll_interval_s=profile.communication.poll_interval_s,
            last_tick=lambda: state.last_tick_mono_ns,
            restart=partial(self.restart, profile.id),
        )
        return runner

    async def _cancel(self, runner: _Runner, timeout_s: float) -> None:
        runner.loop.request_stop()
        runner.task.cancel()
        _, pending = await asyncio.wait({runner.task}, timeout=timeout_s)
        if pending:
            logger.warning("aquisição %s: task não parou em %.1f s", runner.profile.id, timeout_s)

    def _mark_disconnected(self, equipment_id: str) -> None:
        state = self._states.get(equipment_id)
        if state is None:
            return
        if state.connection not in (ConnectionState.DISCONNECTED, ConnectionState.NOT_CONFIGURED):
            state.connection = ConnectionState.DISCONNECTED
            state.detail_pt = "Aquisição parada"

    def _ensure_watchdog_task(self) -> None:
        if self._watchdog_task is None or self._watchdog_task.done():
            self._watchdog_task = asyncio.create_task(self._watchdog.run(), name="forja-watchdog")

    async def _stop_watchdog_task(self) -> None:
        task, self._watchdog_task = self._watchdog_task, None
        if task is None or task.done():
            return
        task.cancel()
        await asyncio.wait({task}, timeout=1.0)
