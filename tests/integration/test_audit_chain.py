"""Cadeia de hash da trilha de auditoria (ADR 0014): alteração por fora do Forja é detectada."""

from __future__ import annotations

import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from forja.historian import SqliteCoreStore
from forja.infra.clock import FakeClock
from forja.tools.cli import main

pytestmark = pytest.mark.integration


@pytest.fixture
async def core(tmp_path: Path) -> AsyncIterator[SqliteCoreStore]:
    store = SqliteCoreStore(tmp_path / "forja_core.db", FakeClock())
    await store.open()
    try:
        yield store
    finally:
        await store.close()


async def _three(core: SqliteCoreStore) -> None:
    for n in range(3):
        await core.audit("tecnico", "EVENT_ACK", "event", f"ev{n}", None, {"n": n}, "visto")


def _tamper(db: Path, sql: str, *params: object) -> None:
    """Edita o arquivo do banco por fora (sem os triggers), como faria um invasor."""
    conn = sqlite3.connect(db)
    try:
        conn.execute("DROP TRIGGER IF EXISTS audit_log_no_update")
        conn.execute("DROP TRIGGER IF EXISTS audit_log_no_delete")
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


async def test_cadeia_integra(core: SqliteCoreStore) -> None:
    await _three(core)
    result = await core.verify_audit()
    assert result["ok"] is True
    assert result["chained"] == 3
    assert "íntegra" in result["message_pt"]


async def test_alterar_registro_por_fora_e_detectado(core: SqliteCoreStore, tmp_path: Path) -> None:
    await _three(core)
    await core.close()
    _tamper(
        tmp_path / "forja_core.db",
        "UPDATE audit_log SET reason_pt = ? WHERE entity_id = ?",
        "x",
        "ev1",
    )
    await core.open()
    result = await core.verify_audit()
    assert result["ok"] is False
    assert result["broken_at"] == 2
    assert "alterada fora do Forja" in result["message_pt"]


async def test_apagar_registro_por_fora_e_detectado(core: SqliteCoreStore, tmp_path: Path) -> None:
    await _three(core)
    await core.close()
    _tamper(tmp_path / "forja_core.db", "DELETE FROM audit_log WHERE entity_id = ?", "ev1")
    await core.open()
    result = await core.verify_audit()
    assert result["ok"] is False


async def test_registro_anterior_ao_encadeamento_fica_de_fora(
    core: SqliteCoreStore, tmp_path: Path
) -> None:
    await core.close()
    conn = sqlite3.connect(tmp_path / "forja_core.db")
    conn.execute(
        "INSERT INTO audit_log (ts_ms, user, action, entity_type, entity_id, reason_pt) "
        "VALUES (1, 'antigo', 'EVENT_ACK', 'event', 'velho', '')"
    )
    conn.commit()
    conn.close()
    await core.open()
    await _three(core)
    result = await core.verify_audit()
    assert result["ok"] is True
    assert result["before_chain"] == 1
    assert result["chained"] == 3


def test_linha_de_comando_confere(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    home = tmp_path / "ForjaKCM"
    assert main(["init", "--home", str(home)]) == 0
    assert main(["audit", "verify", "--home", str(home)]) == 0
    assert "íntegra" in capsys.readouterr().out
