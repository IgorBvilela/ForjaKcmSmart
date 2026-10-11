"""Planta: equipamento com a coleta pausada nunca entra no resumo como condição normal.

Usa um Edge próprio (configuração em cópia temporária) com a coleta pausada em todos os perfis:
o resumo tem de contar esse estado e não pode dizer "todos em condição normal".
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import yaml
from playwright.sync_api import Page, expect

from tests.e2e.conftest import Edge, running_edge, seed_home
from tests.e2e.helpers import open_route

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def edge(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Edge]:
    home = seed_home(tmp_path_factory.mktemp("forja_e2e_paused_home"))
    for path in sorted((home / "config" / "equipment").glob("*.yaml")):
        profile = yaml.safe_load(path.read_text(encoding="utf-8"))
        profile.setdefault("communication", {})["collection_enabled"] = False
        path.write_text(
            yaml.safe_dump(profile, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
    with running_edge(home, tmp_path_factory.mktemp("forja_e2e_paused_data")) as running:
        yield running


def test_summary_counts_paused_collection_and_never_reads_all_normal(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, "/app/plant", "plant")
    cards = page.get_by_test_id("plant-grid").locator("[data-testid^='plant-card-']")
    expect(cards).to_have_count(3)
    for i in range(3):
        expect(cards.nth(i)).to_have_attribute("data-state", "Coleta pausada")

    summary = page.get_by_test_id("plant-summary")
    expect(summary).to_contain_text("3 equipamentos")
    expect(summary).to_contain_text("3 com coleta pausada")
    expect(summary).not_to_contain_text("normal")
