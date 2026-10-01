"""Montagem do Edge: config → driver → historian → scheduler → motor de eventos.

Este é o único lugar que escolhe o driver. Trocar `KcmSimulator` por um
driver real é uma linha em config/edge.yaml, não uma mudança de código.

A cadeia completa da Etapa 2:

    driver.read() → normalize() → historian
                         ↓
                    CycleResult ──→ EventEngine ──→ evento no historian
                                                          ↓
                                                  biblioteca de diagnóstico

O motor é plugado no scheduler por `on_cycle`. Recebe o ciclo inteiro — as
amostras E as falhas de leitura — porque precisa dos dois para separar
"a leitura falhou" de "o valor exibido é antigo".
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from forja.acquisition.scheduler import AcquisitionScheduler
from forja.config.loader import EdgeConfig, load_edge_config, load_equipment
from forja.domain.equipment import EquipmentCard
from forja.drivers.base import KcmDriver
from forja.drivers.simulator import KcmSimulator
from forja.events.engine import EventEngine
from forja.historian.repository import HistorianRepository

log = logging.getLogger("forja.app")


@dataclass
class Edge:
    config: EdgeConfig
    equipment: EquipmentCard
    driver: KcmDriver
    historian: HistorianRepository
    scheduler: AcquisitionScheduler
    events: Optional[EventEngine] = None

    def start(self) -> None:
        log.info("Forja Edge iniciando: driver=%s equipamento=%s historian=%s eventos=%s",
                 self.config.driver, self.equipment.equipment_id, self.config.historian_url,
                 "on" if self.events else "off")
        self.scheduler.start()

    def stop(self) -> None:
        self.scheduler.stop()


def build_driver(cfg: EdgeConfig, equipment: EquipmentCard) -> KcmDriver:
    if cfg.driver == "simulator":
        return KcmSimulator(scenario=cfg.simulator.scenario, seed=cfg.simulator.seed,
                            speed=cfg.simulator.speed, equipment_id=equipment.equipment_id)
    # Etapa 3: "modbus_tcp" e "ethernet_ip" entram aqui, lendo tudo do YAML.
    raise ValueError(f"driver '{cfg.driver}' ainda não implementado (Etapa 3). Disponível: simulator")


def build_edge(config_path: str = "config/edge.yaml") -> Edge:
    cfg = load_edge_config(config_path)
    equipment = load_equipment(cfg.equipment_file)
    driver = build_driver(cfg, equipment)
    historian = HistorianRepository(cfg.historian_url)

    engine: Optional[EventEngine] = None
    if cfg.events.enabled:
        engine = EventEngine(equipment, historian,
                             history_size=cfg.events.history_size,
                             context_before_s=cfg.events.context_before_s)

    scheduler = AcquisitionScheduler(driver, equipment, historian,
                                     base_cycle_s=cfg.acquisition.base_cycle_s,
                                     stale_after_cycles=cfg.acquisition.stale_after_cycles,
                                     on_cycle=engine.on_cycle if engine else None)
    return Edge(cfg, equipment, driver, historian, scheduler, engine)
