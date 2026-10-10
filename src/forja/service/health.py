"""Relatório de saúde do Forja Edge em linguagem simples.

Junta o estado de cada parte (aquisição por equipamento, historiador, banco core, disco, tarefas
periódicas, motor de eventos, tempo real) e produz achados em português, do mais grave ao mais
leve. Os limites abaixo são regras da Forja sobre a saúde do PRÓPRIO Edge (FORJA_RULE); nenhum é
limite do KCM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final, Literal

from forja.domain import ConnectionState, EquipmentProfile, EquipmentRuntimeStatus

Severity = Literal["ok", "info", "warn", "crit"]

DISK_WARN_FREE: Final[float] = 0.20
DISK_CRIT_FREE: Final[float] = 0.10
HISTORIAN_WARN_FRACTION: Final[float] = 0.90
COMM_CRIT_AFTER_S: Final[float] = 300.0

_RANK: Final[dict[str, int]] = {"ok": 0, "info": 1, "warn": 2, "crit": 3}
STATUS_PT: Final[dict[str, str]] = {
    "ok": "Tudo funcionando",
    "info": "Funcionando, com observações",
    "warn": "Atenção",
    "crit": "Problema que precisa de ação",
}


@dataclass
class HealthInputs:
    now: datetime
    uptime_s: float
    version: str
    profiles: dict[str, EquipmentProfile]
    statuses: dict[str, EquipmentRuntimeStatus]
    historian: dict[str, Any] | None = None
    core: dict[str, Any] | None = None
    disk_total: int | None = None
    disk_free: int | None = None
    max_historian_gb: float = 20.0
    jobs: dict[str, Any] | None = None
    bridge: dict[str, Any] | None = None
    sse: dict[str, Any] | None = None


@dataclass
class _Report:
    findings: list[dict[str, str]] = field(default_factory=list)

    def add(self, severity: Severity, area: str, text_pt: str) -> None:
        self.findings.append({"severity": severity, "area": area, "text_pt": text_pt})


def _gb_pt(size_bytes: float) -> str:
    return f"{size_bytes / 1024**3:.1f}".replace(".", ",")


def _duration_pt(seconds: float) -> str:
    s = int(max(0, seconds))
    if s < 60:
        return f"{s} s"
    m = s // 60
    if m < 60:
        return f"{m} min"
    h, rm = divmod(m, 60)
    if h < 48:
        return f"{h} h {rm:02d} min"
    return f"{h // 24} dias"


def _equipment(report: _Report, inputs: HealthInputs) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for eid, profile in inputs.profiles.items():
        status = inputs.statuses.get(eid)
        comm = profile.communication
        if status is None:
            continue
        since_ok = (inputs.now - status.last_ok_utc).total_seconds() if status.last_ok_utc else None
        collecting = comm.collection_enabled and not comm.needs_configuration
        rows.append(
            {
                "equipment_id": eid,
                "name": profile.name,
                "driver": comm.driver,
                "collecting": collecting,
                "connection": status.connection.value,
                "connection_pt": status.connection.label_pt,
                "latency_ms": status.latency_ms,
                "consecutive_errors": status.consecutive_errors,
                "reconnect_count": status.reconnect_count,
                "restart_count": status.restart_count,
                "samples_per_min": status.samples_per_min,
                "last_ok_utc": status.last_ok_utc,
                "since_ok_s": since_ok,
                "is_stale": status.is_stale,
                "detail_pt": status.detail_pt,
            }
        )
        if not collecting:
            continue
        if status.connection is ConnectionState.ERROR:
            when = f"há {_duration_pt(since_ok)}" if since_ok is not None else "desde o início"
            severity: Severity = (
                "crit" if since_ok is None or since_ok > COMM_CRIT_AFTER_S else "warn"
            )
            report.add(
                severity,
                "aquisição",
                f"{profile.name}: sem leitura válida {when} "
                f"({status.consecutive_errors} falha(s) seguida(s)).",
            )
        elif status.is_stale:
            report.add("warn", "aquisição", f"{profile.name}: último valor está antigo.")
        if status.restart_count:
            report.add(
                "info",
                "aquisição",
                f"{profile.name}: a coleta travou e foi reiniciada automaticamente "
                f"{status.restart_count} vez(es).",
            )
    if rows and not any(r["collecting"] for r in rows):
        report.add("info", "aquisição", "Nenhum equipamento com coleta ativa.")
    return rows


def _storage(report: _Report, inputs: HealthInputs) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if inputs.disk_total and inputs.disk_free is not None:
        free = inputs.disk_free / inputs.disk_total
        out["disk"] = {
            "total_bytes": inputs.disk_total,
            "free_bytes": inputs.disk_free,
            "free_fraction": free,
        }
        if free < DISK_CRIT_FREE:
            report.add("crit", "disco", f"Disco dos dados com só {free:.0%} livre.")
        elif free < DISK_WARN_FREE:
            report.add("warn", "disco", f"Disco dos dados com {free:.0%} livre.")
    hist = inputs.historian or {}
    size = hist.get("size_bytes")
    if isinstance(size, int | float):
        limit = inputs.max_historian_gb * 1024**3
        out["historian_fraction"] = size / limit if limit else None
        if limit and size > HISTORIAN_WARN_FRACTION * limit:
            report.add(
                "warn",
                "historiador",
                f"Historiador com {_gb_pt(size)} GB de {inputs.max_historian_gb:g} GB previstos.",
            )
    return out


def _engines(report: _Report, inputs: HealthInputs) -> None:
    jobs = inputs.jobs or {}
    for name, label in (
        ("run_rollups", "Consolidação do histórico"),
        ("run_retention", "Retenção"),
    ):
        errors = (jobs.get("errors") or {}).get(name, 0)
        if errors:
            report.add("warn", "historiador", f"{label}: {errors} execução(ões) com erro.")
    bridge = inputs.bridge or {}
    if bridge.get("errors"):
        report.add(
            "warn", "eventos", f"Motor de eventos: {bridge['errors']} erro(s) ao processar lotes."
        )
    sse = inputs.sse or {}
    if sse.get("dropped"):
        report.add(
            "info",
            "tempo real",
            f"Tempo real: {sse['dropped']} atualização(ões) descartada(s) por tela lenta.",
        )


def build_health_report(inputs: HealthInputs) -> dict[str, Any]:
    report = _Report()
    equipment = _equipment(report, inputs)
    storage = _storage(report, inputs)
    _engines(report, inputs)
    report.findings.sort(key=lambda f: -_RANK[f["severity"]])
    worst = max((f["severity"] for f in report.findings), key=lambda s: _RANK[s], default="ok")
    if worst == "info" and not any(f["severity"] != "info" for f in report.findings):
        worst = "info"
    return {
        "status": worst,
        "status_pt": STATUS_PT[worst],
        "findings": report.findings,
        "edge": {"version": inputs.version, "uptime_s": inputs.uptime_s},
        "equipment": equipment,
        "storage": storage,
        "historian": inputs.historian,
        "core": inputs.core,
        "jobs": inputs.jobs,
        "events_engine": inputs.bridge,
        "realtime": inputs.sse,
    }


__all__ = ["HealthInputs", "build_health_report"]
