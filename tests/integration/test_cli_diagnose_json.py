"""CLI `forja`: diagnose (--json e texto), config validate, doctor, simulate.

Sem rede, sem banco em disco: o core store é substituído por um fake em memória.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from forja.api.routers.diagnostics import diagnosis_json
from forja.domain import OFFICIAL_SECTIONS_PT, Diagnosis
from forja.infra import FakeClock
from forja.tools import cli
from tests.integration.api_testkit import REPO_ROOT, make_diagnosis, make_event

pytestmark = pytest.mark.integration

HOME = ["--home", str(REPO_ROOT)]


class FakeCoreStore:
    def __init__(self, diagnosis: Diagnosis | None) -> None:
        self._diagnosis = diagnosis
        self.opened = False
        self.closed = False

    async def open(self) -> None:
        self.opened = True

    async def close(self) -> None:
        self.closed = True

    async def get_for_event(self, event_id: str) -> Diagnosis | None:
        if self._diagnosis is not None and self._diagnosis.event_id == event_id:
            return self._diagnosis
        return None


@pytest.fixture
def stored(monkeypatch: pytest.MonkeyPatch) -> tuple[Diagnosis, FakeCoreStore]:
    clock = FakeClock()
    event = make_event(clock, "EQUIPAMENTO_TESTE")
    diagnosis = make_diagnosis(clock, event)
    store = FakeCoreStore(diagnosis)
    monkeypatch.setattr(cli, "open_core_store", lambda _paths, _clock: store)
    return diagnosis, store


def _run(capsys: pytest.CaptureFixture[str], argv: list[str]) -> tuple[int, str, str]:
    code = cli.main(argv)
    out, err = capsys.readouterr()
    return code, out, err


def test_diagnose_event_id_json_is_exactly_the_api_object(
    capsys: pytest.CaptureFixture[str], stored: tuple[Diagnosis, FakeCoreStore]
) -> None:
    diagnosis, store = stored
    code, out, err = _run(capsys, ["diagnose", "--json", "--event-id", diagnosis.event_id, *HOME])
    assert code == 0
    assert err == ""
    parsed = json.loads(out)
    assert parsed == diagnosis_json(diagnosis)
    assert Diagnosis.model_validate(parsed) == diagnosis
    assert parsed["diagnosis_schema_version"] == "1.0"
    assert store.opened
    assert store.closed


def test_diagnose_without_json_prints_seven_sections_and_no_json(
    capsys: pytest.CaptureFixture[str], stored: tuple[Diagnosis, FakeCoreStore]
) -> None:
    diagnosis, _ = stored
    code, out, _ = _run(capsys, ["diagnose", "--event-id", diagnosis.event_id, *HOME])
    assert code == 0
    assert not out.lstrip().startswith("{")
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)
    positions = [out.index(title) for _, title in OFFICIAL_SECTIONS_PT]
    assert positions == sorted(positions)  # ordem oficial
    assert diagnosis.summary.title_pt in out
    assert "Hipóteses não representam causa confirmada." in out
    assert '"diagnosis_schema_version"' not in out


def test_diagnose_unknown_event_fails_with_empty_stdout(
    capsys: pytest.CaptureFixture[str], stored: tuple[Diagnosis, FakeCoreStore]
) -> None:
    code, out, err = _run(capsys, ["diagnose", "--json", "--event-id", "nao-existe", *HOME])
    assert code == 1
    assert out == ""
    assert "Nenhum diagnóstico" in err


def test_diagnose_requires_exactly_one_source(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["diagnose", "--json", "--demo", "BELTLOAD_LOW", "--event-id", "x", *HOME])
    assert exc.value.code == 2
    with pytest.raises(SystemExit) as exc2:
        cli.main(["diagnose", "--json", *HOME])
    assert exc2.value.code == 2


def test_diagnose_demo_rejects_unknown_scenario(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = _run(capsys, ["diagnose", "--json", "--demo", "REFILL", *HOME])
    assert code == 1
    assert out == ""
    assert "cenário desconhecido" in err
    assert "NORMAL_OPERATION" in err


def test_diagnose_demo_rejects_non_simulator_equipment(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    code, out, err = _run(
        capsys, ["diagnose", "--json", "--demo", "BELTLOAD_LOW", "--equipment", "NAO_EXISTE", *HOME]
    )
    assert code == 1
    assert out == ""
    assert "não encontrado" in err


def test_config_validate_returns_zero_for_seed(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = _run(capsys, ["config", "validate", *HOME])
    assert code == 0, out
    assert "Equipamentos (" in out
    assert "Mappings (" in out
    assert "configuração válida" in out
    assert "ERRO" not in out


def test_config_validate_fails_on_broken_config(
    capsys: pytest.CaptureFixture[str], tmp_path: Any
) -> None:
    (tmp_path / "config" / "equipment").mkdir(parents=True)
    (tmp_path / "config" / "mappings").mkdir(parents=True)
    (tmp_path / "config" / "equipment" / "quebrado.yaml").write_text(
        "id: minusculo_invalido\nname: x\nmapping_profile: nada\n", encoding="utf-8"
    )
    code, out, _ = _run(capsys, ["config", "validate", "--home", str(tmp_path)])
    assert code == 1
    assert "ERRO" in out


def test_doctor_runs_offline_and_returns_zero(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = _run(capsys, ["doctor", *HOME])
    assert code == 0, out
    assert "Python" in out
    assert "SQLite" in out
    assert "lib fastapi" in out
    assert "Nenhuma verificação usa rede" in out


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert "forja" in capsys.readouterr().out


# --- caminho completo (depende dos blocos 1 e 4 já presentes no repositório) -------------------


def test_diagnose_demo_beltload_low_produces_valid_v1_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = _run(capsys, ["diagnose", "--json", "--demo", "BELTLOAD_LOW", *HOME])
    assert code == 0, err
    parsed = json.loads(out)
    diagnosis = Diagnosis.model_validate(parsed)
    assert parsed == diagnosis_json(diagnosis)
    assert diagnosis.summary.internal_code == "BELT_LOAD_LOW"
    assert diagnosis.what_changed
    assert any(w.changed_first for w in diagnosis.what_changed)
    assert all("causa:" not in h.text_pt.lower() for h in diagnosis.hypotheses)
    assert diagnosis.summary.title_pt != diagnosis.summary.internal_code


def test_diagnose_demo_text_mode_never_prints_json(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = _run(capsys, ["diagnose", "--demo", "BELTLOAD_LOW", *HOME])
    assert code == 0, err
    assert not out.lstrip().startswith("{")
    for _, title in OFFICIAL_SECTIONS_PT:
        assert title in out
    assert "DADOS SIMULADOS" in err


def test_simulate_lists_transitions_in_portuguese(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = _run(
        capsys, ["simulate", "--scenario", "STOP_NORMAL", "--seconds", "30", *HOME]
    )
    assert code == 0, err
    assert "Simulação offline" in out
    assert "DADOS SIMULADOS" in out
    assert "Resumo:" in out
    assert not out.lstrip().startswith("{")
