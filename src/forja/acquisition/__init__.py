"""Aquisição: loops por equipamento, estado ao vivo, backoff, watchdog e teste de leitura."""

from forja.acquisition.backoff import Backoff
from forja.acquisition.live import LiveSnapshot, LiveState, StaleMonitor
from forja.acquisition.loop import (
    AcquisitionPipeline,
    DriverRegistryPort,
    EquipmentLoop,
    default_pipeline,
)
from forja.acquisition.manager import EquipmentManager
from forja.acquisition.state import ConnectionChanged, EquipmentState, reason_pt_for
from forja.acquisition.test_read import ReadTestResult, run_read_test
from forja.acquisition.watchdog import Watchdog

__all__ = [
    "AcquisitionPipeline",
    "Backoff",
    "ConnectionChanged",
    "DriverRegistryPort",
    "EquipmentLoop",
    "EquipmentManager",
    "EquipmentState",
    "LiveSnapshot",
    "LiveState",
    "ReadTestResult",
    "StaleMonitor",
    "Watchdog",
    "default_pipeline",
    "reason_pt_for",
    "run_read_test",
]
