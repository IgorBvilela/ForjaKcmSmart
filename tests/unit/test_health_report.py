"""Relatório de saúde: achados em português, do mais grave ao mais leve."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from forja.domain import (
    CommunicationConfig,
    ConnectionState,
    DriverSupportState,
    EquipmentProfile,
    EquipmentRuntimeStatus,
)
from forja.service.health import HealthInputs, build_health_report

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 10, 15, 0, tzinfo=UTC)


def _profile(eid: str, **comm: object) -> EquipmentProfile:
    return EquipmentProfile(
        id=eid,
        name=f"Equipamento {eid}",
        mapping_profile="m_teste",
        communication=CommunicationConfig(**comm),  # type: ignore[arg-type]
    )


def _status(eid: str, connection: ConnectionState, **kw: object) -> EquipmentRuntimeStatus:
    return EquipmentRuntimeStatus(
        equipment_id=eid,
        driver="simulator",
        support_state=DriverSupportState.AVAILABLE,
        connection=connection,
        **kw,  # type: ignore[arg-type]
    )


def test_tudo_bem_sem_achados() -> None:
    report = build_health_report(
        HealthInputs(
            now=NOW,
            uptime_s=60,
            version="0.1.0",
            profiles={"EQ_A": _profile("EQ_A")},
            statuses={"EQ_A": _status("EQ_A", ConnectionState.CONNECTED, last_ok_utc=NOW)},
            disk_total=100,
            disk_free=80,
        )
    )
    assert report["status"] == "ok"
    assert report["findings"] == []
    assert report["equipment"][0]["collecting"] is True


def test_sem_comunicacao_ha_muito_tempo_e_critico_e_vem_primeiro() -> None:
    report = build_health_report(
        HealthInputs(
            now=NOW,
            uptime_s=3600,
            version="0.1.0",
            profiles={"EQ_A": _profile("EQ_A"), "EQ_B": _profile("EQ_B")},
            statuses={
                "EQ_A": _status(
                    "EQ_A",
                    ConnectionState.ERROR,
                    last_ok_utc=NOW - timedelta(minutes=12),
                    consecutive_errors=40,
                ),
                "EQ_B": _status(
                    "EQ_B", ConnectionState.CONNECTED, last_ok_utc=NOW, restart_count=2
                ),
            },
            disk_total=100,
            disk_free=15,
        )
    )
    assert report["status"] == "crit"
    first = report["findings"][0]
    assert first["severity"] == "crit"
    assert "Equipamento EQ_A" in first["text_pt"]
    assert "12 min" in first["text_pt"]
    texts = " ".join(f["text_pt"] for f in report["findings"])
    assert "15% livre" in texts
    assert "reiniciada automaticamente 2 vez(es)" in texts


def test_coleta_pausada_nao_e_falha() -> None:
    report = build_health_report(
        HealthInputs(
            now=NOW,
            uptime_s=10,
            version="0.1.0",
            profiles={"EQ_A": _profile("EQ_A", collection_enabled=False)},
            statuses={"EQ_A": _status("EQ_A", ConnectionState.DISCONNECTED)},
        )
    )
    assert report["status"] == "info"
    assert report["findings"][0]["text_pt"] == "Nenhum equipamento com coleta ativa."


def test_erros_de_tarefas_e_motor_de_eventos_viram_atencao() -> None:
    report = build_health_report(
        HealthInputs(
            now=NOW,
            uptime_s=10,
            version="0.1.0",
            profiles={},
            statuses={},
            jobs={"errors": {"run_rollups": 3, "run_retention": 0}},
            bridge={"errors": 1},
            historian={"size_bytes": 19.5 * 1024**3},
            max_historian_gb=20,
        )
    )
    assert report["status"] == "warn"
    texts = " ".join(f["text_pt"] for f in report["findings"])
    assert "Consolidação do histórico: 3" in texts
    assert "Motor de eventos" in texts
    assert "19,5 GB de 20 GB" in texts
