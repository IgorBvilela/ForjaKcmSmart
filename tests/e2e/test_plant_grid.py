"""Planta em grade quase quadrada: com 4 dosadores, 2 × 2 a partir de 1024 px, 2 colunas no
tablet e 1 coluna no celular, sem rolagem lateral.

Usa um Edge próprio (configuração em cópia temporária) com um quarto perfil: cópia do Dosador
Pó Base com outro id, na mesma área, para os 4 ficarem num grupo só.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import yaml
from playwright.sync_api import Page, expect

from tests.e2e.conftest import Edge, running_edge, seed_home
from tests.e2e.helpers import open_route, overflow_info

pytestmark = pytest.mark.e2e

FOURTH_ID = "E2E_QUARTO_DOSADOR"


@pytest.fixture(scope="module")
def edge(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Edge]:
    home = seed_home(tmp_path_factory.mktemp("forja_e2e_grid_home"))
    equipment = home / "config" / "equipment"
    profile = yaml.safe_load((equipment / "gtex_pha_po_base.yaml").read_text(encoding="utf-8"))
    profile["id"] = FOURTH_ID
    profile["name"] = "Quarto dosador (teste)"
    (equipment / f"{FOURTH_ID.lower()}.yaml").write_text(
        yaml.safe_dump(profile, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    with running_edge(home, tmp_path_factory.mktemp("forja_e2e_grid_data")) as running:
        yield running


def grid_shape(page: Page) -> tuple[int, int]:
    """(colunas, linhas) pela posição de layout dos cartões (sem efeito de animação)."""
    cards = page.get_by_test_id("plant-grid").locator("[data-testid^='plant-card-']")
    expect(cards).to_have_count(4)
    boxes = cards.evaluate_all("els => els.map(e => [e.offsetLeft, e.offsetTop])")
    return len({x for x, _ in boxes}), len({y for _, y in boxes})


@pytest.mark.parametrize(
    ("width", "shape"),
    [(1440, (2, 2)), (1024, (2, 2)), (768, (2, 2)), (375, (1, 4))],
)
def test_four_dosers_form_a_near_square_grid(
    desktop_1366: Page, width: int, shape: tuple[int, int]
) -> None:
    page = desktop_1366
    page.set_viewport_size({"width": width, "height": 900})
    open_route(page, "/app/plant", "plant")
    expect(page.get_by_test_id(f"plant-card-{FOURTH_ID}")).to_be_visible()
    assert grid_shape(page) == shape
    info = overflow_info(page)
    assert not info["overflow"], info
