"""Apoio aos testes do Bloco 1 (drivers + normalizacao).

Perfis aqui sao genericos de teste (ids SIM_TESTE_*, MB_TESTE_*): nada da GTEX.
O mapping do simulador e o arquivo real `config/mappings/simulator_wbf.yaml`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from forja.domain import EquipmentProfile, Mapping

REPO_ROOT = Path(__file__).resolve().parents[2]
SIM_MAPPING_PATH = REPO_ROOT / "config" / "mappings" / "simulator_wbf.yaml"

TEST_REFS: dict[str, float] = {"setpoint_ref": 1000.0, "belt_load_ref": 2.0, "rpm_ref": 60.0}
"""Referencias de teste. Nao sao limites de nenhum KCM."""


def load_sim_mapping() -> Mapping:
    with SIM_MAPPING_PATH.open("r", encoding="utf-8") as fh:
        return Mapping.model_validate(yaml.safe_load(fh))


def sim_profile(
    equipment_id: str = "SIM_TESTE_01",
    *,
    scenario: str = "NORMAL_OPERATION",
    seed: int = 7,
    time_scale: float | None = None,
    refs: dict[str, float] | None = None,
    driver: str = "simulator",
    mapping_profile: str = "simulator_wbf",
    **communication: Any,
) -> EquipmentProfile:
    """Perfil de teste. Para driver != simulator, options fica vazio."""
    options: dict[str, Any] = {}
    if driver == "simulator":
        options = {"scenario": scenario, "seed": seed}
        if time_scale is not None:
            options["time_scale"] = time_scale
    return EquipmentProfile.model_validate(
        {
            "id": equipment_id,
            "name": f"Equipamento de teste {equipment_id}",
            "application": "WBF",
            "mapping_profile": mapping_profile,
            "is_example": True,
            "communication": {"driver": driver, "options": options, **communication},
            "reference_values": dict(TEST_REFS if refs is None else refs),
        }
    )
