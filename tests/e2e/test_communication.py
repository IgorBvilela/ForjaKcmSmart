"""KCM › Comunicação no navegador, contra um servidor Modbus de bancada (127.0.0.1).

Fluxo de campo completo, numa coluna: escolher protocolo, endereço e variável; conferir sem
conectar; testar somente leitura; comparar com o "valor na tela do KCM"; salvar e ativar com um
botão só (auditado, com histórico); ver a variável validada em Tempo Real. O servidor de bancada
prova que só funções de leitura chegaram ao fio. Os testes seguem a ordem do arquivo: o fluxo de
campo deixa o Modbus de bancada salvo e a coleta ativa para os seguintes.

Usa um Edge próprio (configuração em cópia temporária): os outros testes de tela continuam
vendo os equipamentos da semente intactos.
"""

from __future__ import annotations

import asyncio
import re
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from playwright.sync_api import Browser, Page, Request, Route, expect

from tests.e2e.conftest import (
    DEFAULT_TIMEOUT_MS,
    Edge,
    is_local_url,
    running_edge,
    seed_home,
)
from tests.e2e.helpers import overflow_info
from tests.fixtures.fake_modbus_server import FakeModbusServer, float32_words

pytestmark = pytest.mark.e2e

EQ = "GTEX_PHA_PO_BASE"
FLOW = 1250.0  # dado de bancada, sem relação com equipamento real
READ_FCS = {1, 2, 3, 4}


@pytest.fixture(scope="module")
def bench() -> Iterator[FakeModbusServer]:
    loop = asyncio.new_event_loop()
    server = FakeModbusServer(unit_id=1)
    w0, w1 = float32_words(FLOW)
    server.holding.update({0: w0, 1: w1, 2: 1})

    def run() -> None:
        asyncio.set_event_loop(loop)
        loop.run_forever()

    thread = threading.Thread(target=run, name="bancada-modbus", daemon=True)
    thread.start()
    asyncio.run_coroutine_threadsafe(server.start(), loop).result(10)
    try:
        yield server
    finally:
        asyncio.run_coroutine_threadsafe(server.stop(), loop).result(10)
        loop.call_soon_threadsafe(loop.stop)
        thread.join(10)


@pytest.fixture(scope="module")
def comm_edge(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Edge]:
    home = seed_home(tmp_path_factory.mktemp("forja_e2e_comm_home"))
    with running_edge(home, tmp_path_factory.mktemp("forja_e2e_comm_data")) as edge:
        yield edge


@pytest.fixture
def page(browser: Browser, comm_edge: Edge) -> Iterator[Page]:
    violations: list[str] = []
    errors: list[str] = []

    def guard(route: Route, req: Request) -> None:
        if is_local_url(req.url):
            route.continue_()
        else:
            violations.append(req.url)
            route.abort("blockedbyclient")

    ctx = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        base_url=comm_edge.base_url,
        locale="pt-BR",
        timezone_id="America/Sao_Paulo",
        color_scheme="dark",
        reduced_motion="reduce",
    )
    ctx.set_default_timeout(DEFAULT_TIMEOUT_MS)
    pg = ctx.new_page()
    pg.route("**/*", guard)
    pg.on("pageerror", lambda e: errors.append(str(e)))
    yield pg
    ctx.close()
    assert not violations, violations
    assert not errors, errors


def _open(page: Page) -> None:
    page.goto(f"/app/eq/{EQ}/kcm/communication", wait_until="load")
    expect(page.get_by_test_id("comm-state")).to_be_visible()


def test_protocolo_nao_identificado_e_honesto_e_bloqueia_o_teste(page: Page) -> None:
    _open(page)
    page.get_by_test_id("protocol-UNKNOWN").click()
    expect(page.get_by_test_id("protocol-unknown")).to_contain_text(
        "Protocolo ainda não identificado"
    )
    expect(page.get_by_test_id("comm-test")).to_be_disabled()
    expect(page.get_by_test_id("comm-step-address")).to_have_count(0)


def test_fluxo_de_campo_completo_contra_modbus_de_bancada(
    page: Page, bench: FakeModbusServer, comm_edge: Edge
) -> None:
    _open(page)
    page.get_by_test_id("protocol-modbus_tcp").click()
    page.get_by_test_id("comm-ip").fill("127.0.0.1")
    page.get_by_test_id("comm-port").fill(str(bench.port))
    page.get_by_test_id("comm-unit").fill("1")
    # variáveis (mapping) ficam fechadas, com a contagem no título
    mapping = page.get_by_test_id("comm-mapping")
    expect(mapping).to_contain_text("sem endereço")
    mapping.click()
    page.get_by_test_id("mapping-entry-mass_flow").get_by_role("button").first.click()
    page.get_by_test_id("map-mass_flow-area").select_option("holding")
    page.get_by_test_id("map-mass_flow-address").fill("0")
    page.get_by_test_id("map-mass_flow-datatype").select_option("float32")
    page.get_by_test_id("map-mass_flow-endianness").select_option("big")
    page.get_by_test_id("map-mass_flow-source").fill("bancada: servidor de teste local")

    page.get_by_test_id("comm-validate").click()
    expect(page.get_by_test_id("comm-validation")).to_have_attribute("data-ok", "true")
    assert bench.requests == [], "conferir não pode abrir conexão"

    page.get_by_test_id("comm-user").fill("tecnico de teste")
    page.get_by_test_id("comm-test").click()
    # o resultado vem numa frase; o detalhe (bruto, decodificado, comparação) fica fechado
    expect(page.get_by_test_id("comm-test-summary")).to_contain_text(
        re.compile(r"Leu \d+ de \d+ variáve")
    )
    page.get_by_test_id("comm-test-detail").click()
    result = page.get_by_test_id("read-test-result")
    expect(result).to_have_attribute("data-success", "true")
    row = page.get_by_test_id("read-test-row-mass_flow")
    expect(row).to_contain_text("Holding register (função 03), endereço 0")
    expect(row).to_contain_text("1250 kg/h")
    page.get_by_test_id("kcm-value-mass_flow").fill("1250")
    page.get_by_test_id("register-match-mass_flow").click()
    expect(page.get_by_test_id("comm-next-commissioning")).to_be_visible()

    # testado com o que está na tela: o botão único salva e ativa
    page.get_by_test_id("comm-reason").fill("conferência de bancada")
    save = page.get_by_test_id("comm-save")
    expect(save).to_have_text("Salvar e ativar a coleta")
    save.click()
    expect(page.get_by_test_id("comm-notice")).to_have_text(
        "Configuração salva e coleta ativada: a Forja passa a ler o KCM."
    )
    expect(page.get_by_test_id("comm-collection")).to_contain_text("ativa")
    # gravado na cópia da configuração, com a versão anterior no histórico
    saved = yaml.safe_load(
        (Path(comm_edge.home) / "config" / "equipment" / "gtex_pha_po_base.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert saved["communication"]["driver"] == "modbus_tcp"
    assert saved["communication"]["collection_enabled"] is True
    assert list((Path(comm_edge.home) / "config" / "_history" / "equipment").glob("*.yaml"))

    # mudar o que afeta a leitura (porta) pede novo teste: o botão passa a salvar sem ativar
    page.get_by_test_id("comm-port").fill("1")
    expect(save).to_have_text("Salvar sem ativar")
    page.get_by_test_id("comm-port").fill(str(bench.port))
    expect(save).to_be_disabled()

    page.goto(f"/app/eq/{EQ}/realtime", wait_until="load")
    live_row = page.get_by_test_id("realtime-row-mass_flow")
    expect(live_row).to_have_attribute("data-quality", "GOOD", timeout=30_000)
    expect(live_row).to_contain_text("1.250")
    assert bench.requests, "a coleta não leu o servidor de bancada"
    assert bench.functions <= READ_FCS, f"função que não lê no fio: {bench.functions}"


def test_salvar_e_ativar_diz_quando_a_ativacao_e_recusada(
    page: Page, bench: FakeModbusServer
) -> None:
    """Salvar deu certo e a ativação foi recusada: a tela diz exatamente isso."""
    _open(page)
    page.get_by_test_id("comm-user").fill("tecnico de teste")
    page.get_by_test_id("comm-collection-off").click()
    expect(page.get_by_test_id("comm-collection")).not_to_contain_text("Coleta ativa")

    page.get_by_test_id("comm-advanced").click()
    page.get_by_test_id("comm-poll").fill("2")
    page.get_by_test_id("comm-test").click()
    expect(page.get_by_test_id("comm-test-summary")).to_contain_text("Leu")

    refusal = {"error": {"code": "READ_TEST_REQUIRED", "message_pt": "Recusada.", "details": None}}
    page.route(
        "**/api/v1/communication/*/collection",
        lambda route: route.fulfill(status=409, json=refusal),
    )
    save = page.get_by_test_id("comm-save")
    expect(save).to_have_text("Salvar e ativar a coleta")
    save.click()
    expect(page.get_by_test_id("comm-notice")).to_have_text(
        "Configuração salva. A coleta não foi ativada: Recusada."
    )


def test_testar_aparece_sem_rolar_em_1440x900(browser: Browser, comm_edge: Edge) -> None:
    ctx = browser.new_context(
        viewport={"width": 1440, "height": 900},
        base_url=comm_edge.base_url,
        locale="pt-BR",
        reduced_motion="reduce",
    )
    try:
        pg = ctx.new_page()
        pg.goto(f"/app/eq/{EQ}/kcm/communication", wait_until="load")
        expect(pg.get_by_test_id("comm-state")).to_be_visible()
        # o aviso de segurança é uma frase só
        expect(pg.get_by_test_id("comm-safety")).to_have_text(
            "Somente leitura: a Forja só lê o KCM, no endereço que você informar."
        )
        pg.get_by_test_id("protocol-modbus_tcp").click()
        box = pg.get_by_test_id("comm-test").bounding_box()
        assert box is not None
        assert box["y"] + box["height"] <= 900, box
    finally:
        ctx.close()


def test_tela_cabe_no_celular(browser: Browser, comm_edge: Edge) -> None:
    ctx = browser.new_context(
        viewport={"width": 375, "height": 812},
        base_url=comm_edge.base_url,
        is_mobile=True,
        has_touch=True,
        locale="pt-BR",
        reduced_motion="reduce",
    )
    try:
        pg = ctx.new_page()
        pg.goto(f"/app/eq/{EQ}/kcm/communication", wait_until="load")
        expect(pg.get_by_test_id("comm-state")).to_be_visible()
        pg.get_by_test_id("comm-mapping").click()
        pg.get_by_test_id("mapping-entry-mass_flow").get_by_role("button").first.click()
        info = overflow_info(pg)
        assert not info["overflow"], info
    finally:
        ctx.close()
