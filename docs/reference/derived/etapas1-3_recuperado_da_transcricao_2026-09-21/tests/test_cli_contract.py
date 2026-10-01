"""`forja diagnose --json` é o contrato oficial entre diagnóstico e consumidor.

A UI da Etapa 3 e qualquer integração leem ESTE JSON. Nunca a saída de texto:
o texto é apresentação e muda sem aviso; o JSON tem versão e regra de
compatibilidade.

Os testes aqui chamam a CLI como um processo de verdade, do jeito que a UI
chamaria — incluindo a captura do stdout com acentos, que no Windows é onde
a integração costuma quebrar primeiro.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from forja.acquisition.scheduler import AcquisitionScheduler
from forja.config.loader import load_edge_config, load_equipment
from forja.drivers.simulator import KcmSimulator
from forja.events.engine import EventEngine
from forja.historian.repository import HistorianRepository

ROOT = Path(__file__).resolve().parents[1]


def _advance(sim: KcmSimulator, seconds: float, sub_step_s: float = 0.5) -> None:
    for _ in range(max(1, int(round(seconds / sub_step_s)))):
        sim._last_t -= sub_step_s / sim.speed
        sim._step()


@pytest.fixture()
def projeto_com_evento(tmp_path):
    """Gera um historian com um evento real e uma config apontando para ele."""
    cfg_base = load_edge_config(ROOT / "config" / "edge.yaml")
    eq = load_equipment(ROOT / cfg_base.equipment_file)
    db = tmp_path / "cli.db"
    h = HistorianRepository(f"sqlite:///{db.as_posix()}")
    sim = KcmSimulator("ENCODER_FAILURE", seed=5, equipment_id=eq.equipment_id)
    engine = EventEngine(eq, h, context_before_s=20.0)
    sched = AcquisitionScheduler(sim, eq, h, on_cycle=engine.on_cycle)
    sim.connect()
    for _ in range(26):
        _advance(sim, 3.0)
        for st in sched._tags.values():
            st.next_due = 0.0
        sched.cycle()

    eventos = h.events(eq.equipment_id)
    assert eventos, "o cenário deveria ter gerado evento"

    dados = yaml.safe_load((ROOT / "config" / "edge.yaml").read_text(encoding="utf-8"))
    dados["historian_url"] = f"sqlite:///{db.as_posix()}"
    dados["equipment_file"] = str((ROOT / cfg_base.equipment_file).as_posix())
    dados["diagnostics"] = {"cases_dir": str((ROOT / "knowledge" / "cases").as_posix())}
    cfg_path = tmp_path / "edge_cli.yaml"
    cfg_path.write_text(yaml.safe_dump(dados, sort_keys=False), encoding="utf-8")
    return {"config": str(cfg_path), "event_id": eventos[-1]["id"], "events": eventos}


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "forja.cli", *args],
                          capture_output=True, text=True, encoding="utf-8", cwd=str(ROOT))


def test_diagnose_json_is_valid_and_versioned(projeto_com_evento):
    r = _cli("diagnose", str(projeto_com_evento["event_id"]),
             "--config", projeto_com_evento["config"], "--json")
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)            # tem de ser JSON puro, sem texto em volta
    assert d["diagnosis_schema_version"] == "1.0"
    assert d["available"] is True
    assert d["event_id"] == projeto_com_evento["event_id"]


def test_diagnose_json_carries_every_section_the_ui_needs(projeto_com_evento):
    r = _cli("diagnose", str(projeto_com_evento["event_id"]),
             "--config", projeto_com_evento["config"], "--json")
    d = json.loads(r.stdout)
    for chave in ("summary", "evidences", "hypotheses", "checks", "sources",
                  "evidence_summary", "related_cases", "caveats"):
        assert chave in d, f"contrato sem '{chave}'"
    assert d["hypotheses"] and d["checks"] and d["sources"]


def test_diagnose_json_has_evidence_level_on_every_item(projeto_com_evento):
    r = _cli("diagnose", str(projeto_com_evento["event_id"]),
             "--config", projeto_com_evento["config"], "--json")
    d = json.loads(r.stdout)
    for grupo in ("hypotheses", "checks", "sources"):
        for item in d[grupo]:
            assert item.get("evidence_level"), f"{grupo}: item sem evidence_level"
            assert item.get("evidence_label"), f"{grupo}: item sem rótulo legível"


def test_diagnose_json_keeps_accents(projeto_com_evento):
    """Acento quebrado em pipe no Windows derruba integração silenciosamente."""
    r = _cli("diagnose", str(projeto_com_evento["event_id"]),
             "--config", projeto_com_evento["config"], "--json")
    d = json.loads(r.stdout)
    texto = json.dumps(d, ensure_ascii=False)
    assert "ó" in texto or "ã" in texto or "é" in texto


def test_diagnose_json_for_missing_event_is_still_json(projeto_com_evento):
    r = _cli("diagnose", "999999", "--config", projeto_com_evento["config"], "--json")
    assert r.returncode == 0
    d = json.loads(r.stdout)
    assert d["error"] == "event_not_found"


def test_text_output_is_not_json_and_is_for_humans(projeto_com_evento):
    r = _cli("diagnose", str(projeto_com_evento["event_id"]),
             "--config", projeto_com_evento["config"])
    assert r.returncode == 0
    with pytest.raises(json.JSONDecodeError):
        json.loads(r.stdout)
    assert "RESUMO" in r.stdout
    assert "FONTES" in r.stdout
    assert "PRÓXIMAS VERIFICAÇÕES" in r.stdout


def test_text_output_shows_the_evidence_level_to_the_technician(projeto_com_evento):
    r = _cli("diagnose", str(projeto_com_evento["event_id"]),
             "--config", projeto_com_evento["config"])
    assert "EVIDÊNCIA:" in r.stdout
    assert "observado em campo" in r.stdout or "opinião técnica" in r.stdout
