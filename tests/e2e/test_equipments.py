"""Multi-equipamento (fase H): cadastrar, ficha técnica, componentes, catálogo de alarmes,
arquivar e restaurar, com a planta agrupada por área. Nada fala com o KCM."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers import EQ_BARRILHA, EQ_MAIN, open_route, overflow_info

pytestmark = pytest.mark.e2e

NEW_ID = "AREA_TESTE_DOSADOR_E2E"


def test_cadastrar_ficha_arquivar_e_restaurar(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, "/app/system/equipments", "system-equipments")
    page.get_by_test_id("eq-responsible").fill("Técnico de teste")
    page.get_by_test_id("eq-new-name").fill("Dosador E2E")
    page.get_by_test_id("eq-new-area").fill("Área teste")
    expect(page.get_by_test_id("eq-new-id")).to_have_value(NEW_ID)
    page.get_by_test_id("eq-new-submit").click()
    expect(page.get_by_test_id("eq-notice")).to_contain_text("protocolo ainda não identificado")
    expect(page.get_by_test_id(f"eq-row-{NEW_ID}")).to_be_visible()

    # a planta mostra o novo equipamento num grupo da área informada
    open_route(page, "/app/plant", "plant")
    expect(page.get_by_test_id("plant-grid")).to_contain_text("Área teste")
    expect(page.get_by_test_id(f"plant-card-{NEW_ID}")).to_be_visible()

    # ficha técnica: o que falta levantar e edição com evidência
    open_route(page, f"/app/eq/{NEW_ID}/kcm/datasheet", "kcm-datasheet")
    expect(page.get_by_test_id("datasheet-unknown")).to_contain_text("Versão de software do KCM")
    page.get_by_test_id("datasheet-edit").click()
    page.get_by_test_id("datasheet-version").fill("versão de teste")
    page.get_by_test_id("datasheet-responsible").fill("Técnico de teste")
    page.get_by_test_id("datasheet-save").click()
    expect(page.get_by_test_id("datasheet-saved")).to_be_visible()
    expect(page.get_by_test_id("datasheet-controller")).to_contain_text("versão de teste")
    expect(page.get_by_test_id("datasheet-unknown")).not_to_contain_text(
        "Versão de software do KCM"
    )

    # comunicação do novo nasce com protocolo não identificado
    page.goto(f"/app/eq/{NEW_ID}/kcm/communication", wait_until="load")
    expect(page.get_by_test_id("comm-state")).to_contain_text("Protocolo ainda não identificado")

    # arquivar exige o id digitado e um motivo; restaurar devolve
    open_route(page, "/app/system/equipments", "system-equipments")
    page.get_by_test_id("eq-responsible").fill("Técnico de teste")
    page.get_by_test_id(f"eq-archive-{NEW_ID}").click()
    submit = page.get_by_test_id("eq-archive-submit")
    expect(submit).to_be_disabled()
    page.get_by_test_id("eq-archive-confirm").fill(NEW_ID)
    page.get_by_test_id("eq-archive-reason").fill("teste de arquivamento")
    submit.click()
    expect(page.get_by_test_id(f"eq-row-{NEW_ID}")).to_have_count(0)
    page.get_by_test_id(f"eq-restore-{NEW_ID}").click()
    expect(page.get_by_test_id(f"eq-row-{NEW_ID}")).to_be_visible()

    # deixa a planta como estava para os outros testes (3 equipamentos de demonstração)
    page.get_by_test_id(f"eq-archive-{NEW_ID}").click()
    page.get_by_test_id("eq-archive-confirm").fill(NEW_ID)
    page.get_by_test_id("eq-archive-reason").fill("fim do teste")
    page.get_by_test_id("eq-archive-submit").click()
    expect(page.get_by_test_id(f"eq-row-{NEW_ID}")).to_have_count(0)


def test_catalogo_de_alarmes_respeita_a_chave(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, f"/app/eq/{EQ_BARRILHA}/kcm/alarms", "kcm-alarms")
    expect(page.get_by_test_id("alarm-key")).to_contain_text("WBF")
    expect(page.get_by_test_id("alarm-list")).to_contain_text("BELTLOAD LOW")
    expect(page.get_by_test_id("alarm-key")).to_contain_text("Desconhecido")


def test_componentes_mostram_evidencia(desktop_1366: Page) -> None:
    page = desktop_1366
    open_route(page, f"/app/eq/{EQ_MAIN}/kcm/components", "kcm-components")
    page.get_by_test_id("components-edit").click()
    expect(page.get_by_test_id("components-form")).to_be_visible()


@pytest.mark.parametrize(
    "path",
    [
        "/app/system/equipments",
        f"/app/eq/{EQ_MAIN}/kcm/datasheet",
        f"/app/eq/{EQ_BARRILHA}/kcm/alarms",
        f"/app/eq/{EQ_MAIN}/kcm/components",
    ],
)
def test_telas_de_equipamento_cabem_no_celular(mobile_375: Page, path: str) -> None:
    page = mobile_375
    page.goto(path, wait_until="load")
    expect(page.get_by_test_id("page")).to_be_visible()
    page.wait_for_timeout(800)
    info = overflow_info(page)
    assert not info["overflow"], info
