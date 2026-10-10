"""API sobre o Container REAL (SQLite em pasta temporária), não sobre os fakes do kit.

Pega defeito de integração que os fakes escondem: o reconhecimento de evento precisa gravar na
trilha de auditoria do banco core de verdade.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from forja.api.app import create_app
from forja.config import ForjaPaths
from forja.infra import FakeClock
from forja.service.container import Container
from forja.service.runner import build_container, stop
from tests.integration.api_testkit import make_event

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[2]


def tmp_paths(tmp_path: Path) -> ForjaPaths:
    return ForjaPaths(
        home=REPO,
        config_dir=REPO / "config",
        knowledge_dir=REPO / "knowledge",
        data_dir=tmp_path / "var",
        logs_dir=tmp_path / "var" / "logs",
        backups_dir=tmp_path / "var" / "backups",
    )


@pytest.fixture
async def real(tmp_path: Path) -> AsyncIterator[tuple[Container, FakeClock]]:
    clock = FakeClock()
    container = await build_container(tmp_paths(tmp_path), clock)
    try:
        yield container, clock
    finally:
        await stop(container, timeout_s=2)


async def test_reconhecer_evento_grava_auditoria_no_banco_real(
    real: tuple[Container, FakeClock],
) -> None:
    container, clock = real
    equipment_id = next(iter(container.store.profiles))
    event = make_event(clock, equipment_id)
    await container.events_repo.save(event)
    app = create_app(container)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            resp = await c.post(
                f"/api/v1/events/{event.id}/ack", json={"user": "tecnico", "note_pt": "visto"}
            )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "ACKNOWLEDGED"
        rows = await container.events_repo.audit_list()  # type: ignore[attr-defined]
        assert rows[0]["action"] == "EVENT_ACK"
        assert rows[0]["user"] == "tecnico"
        assert rows[0]["entity_id"] == event.id
    finally:
        await app.state.stream_hub.stop()
