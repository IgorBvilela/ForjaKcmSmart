"""Testes da interface local (Etapa 3).

Não testam aparência — testam as promessas que a UI faz e que são fáceis de
quebrar sem perceber:

1. a tela é servida pelo próprio Edge, sem depender de build;
2. NADA vem de fora: sem CDN, sem fonte remota, sem script externo. O Edge
   roda num notebook dentro da planta e pode não ter internet;
3. a UI consome o contrato JSON e declara a família de versão que entende;
4. a origem do dado nunca sai da tela.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "forja" / "api" / "static"
HTML = STATIC / "index.html"
CSS = STATIC / "css" / "app.css"
JS_APP = STATIC / "js" / "app.js"
JS_GRAF = STATIC / "js" / "graficos.js"

ARQUIVOS = [HTML, CSS, JS_APP, JS_GRAF]


def _texto(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Os arquivos existem e são servidos
# ---------------------------------------------------------------------------
def test_todos_os_arquivos_da_ui_existem():
    for p in ARQUIVOS:
        assert p.exists(), f"faltando: {p.relative_to(ROOT)}"
        assert p.stat().st_size > 0


def test_a_raiz_serve_a_interface(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "<title>Forja KCM" in r.text


def test_os_assets_sao_servidos(client):
    for caminho, tipo in [("/ui/css/app.css", "text/css"),
                          ("/ui/js/app.js", "javascript"),
                          ("/ui/js/graficos.js", "javascript")]:
        r = client.get(caminho)
        assert r.status_code == 200, caminho
        assert tipo in r.headers["content-type"], caminho


# ---------------------------------------------------------------------------
# NADA VEM DE FORA
# ---------------------------------------------------------------------------
EXTERNO = re.compile(
    r"""(https?:)?//(?!127\.0\.0\.1|localhost)[a-z0-9.-]+\.[a-z]{2,}""",
    re.IGNORECASE)

# ocorrências legítimas: namespace do SVG e comentários de bloco
PERMITIDO = {"http://www.w3.org/2000/svg", "https://json-schema.org"}


def test_nenhum_recurso_externo_na_interface():
    """Sem CDN, sem Google Fonts, sem script de terceiro.

    Se alguém acrescentar um `<script src="https://cdn...">`, a tela quebra
    silenciosamente na planta sem internet — e só se descobre em campo.
    """
    problemas = []
    for p in ARQUIVOS:
        texto = _texto(p)
        for linha_n, linha in enumerate(texto.splitlines(), 1):
            # ignora linha de comentário em JS/CSS
            despido = linha.strip()
            if despido.startswith(("*", "//", "/*")):
                continue
            for m in EXTERNO.finditer(linha):
                url = m.group(0)
                if any(url in ok or ok in url for ok in PERMITIDO):
                    continue
                problemas.append(f"{p.name}:{linha_n} → {url}")
    assert problemas == [], f"recursos externos encontrados: {problemas}"


def test_html_nao_importa_script_nem_estilo_de_fora():
    html = _texto(HTML)
    for src in re.findall(r'<script[^>]+src="([^"]+)"', html):
        assert src.startswith("/ui/"), f"script de fora: {src}"
    for href in re.findall(r'<link[^>]+href="([^"]+)"', html):
        assert href.startswith(("/ui/", "data:")), f"folha de estilo de fora: {href}"


def test_css_nao_usa_import_remoto():
    assert "@import" not in _texto(CSS), "@import pode puxar recurso remoto"


# ---------------------------------------------------------------------------
# A UI consome o contrato, não texto
# ---------------------------------------------------------------------------
def test_a_ui_declara_a_familia_de_contrato_que_entende():
    js = _texto(JS_APP)
    assert 'CONTRATO_SUPORTADO = "1."' in js
    assert "diagnosis_schema_version" in js


def test_a_ui_avisa_quando_o_contrato_e_incompativel():
    js = _texto(JS_APP)
    assert "incompativel" in js
    assert "CONTRATO_SUPORTADO" in js


def test_a_ui_le_os_endpoints_json_e_nao_a_saida_de_texto():
    js = _texto(JS_APP)
    for endpoint in ["/api/status", "/api/latest", "/api/samples",
                     "/api/events", "/diagnosis", "/api/equipment", "/api/alarms"]:
        assert endpoint in js, f"a UI não consome {endpoint}"


def test_a_ui_mostra_o_nivel_de_evidencia_por_item():
    js = _texto(JS_APP)
    assert "evidence_level" in js
    assert "evidence_label" in js
    # o selo é aplicado a hipótese, verificação, fonte e caso
    assert js.count("nivelHtml(") >= 5


def test_a_ui_mostra_o_que_falta_para_promover_uma_referencia():
    js = _texto(JS_APP)
    assert "falta para promover" in js
    assert "doc_reference" in js


# ---------------------------------------------------------------------------
# A origem do dado nunca sai da tela
# ---------------------------------------------------------------------------
def test_a_origem_do_dado_aparece_no_topo_e_no_rodape():
    html = _texto(HTML)
    assert 'id="seloOrigem"' in html
    assert 'id="rodapeOrigem"' in html
    js = _texto(JS_APP)
    assert "data_is_simulated" in js
    assert "simulador" in js.lower()


def test_valor_antigo_mostra_a_idade():
    js = _texto(JS_APP)
    assert "age_s" in js
    assert "idade" in js


def test_a_ui_nao_tem_nenhum_verbo_de_escrita_no_controlador():
    """A tela é read-only como o resto do produto."""
    js = _texto(JS_APP) + _texto(JS_GRAF)
    # o único POST do sistema é a troca de cenário, e ela não está na UI
    assert "method: \"POST\"" not in js
    assert "method: 'POST'" not in js
    assert "/api/dev/scenario" not in js


# ---------------------------------------------------------------------------
# Regras da casa para a tela
# ---------------------------------------------------------------------------
def test_a_tela_nasce_responsiva():
    html = _texto(HTML)
    assert 'name="viewport"' in html
    css = _texto(CSS)
    assert "@media (min-width: 860px)" in css      # nav vira coluna fixa
    assert "@media (max-width: 400px)" in css      # celular pequeno
    assert "overflow-x: hidden" in css


def test_animacao_respeita_movimento_reduzido():
    css = _texto(CSS)
    assert "prefers-reduced-motion: reduce" in css
    bloco = css.split("prefers-reduced-motion: reduce")[1]
    assert "animation-duration: .001ms !important" in bloco
    assert "transition-duration: .001ms !important" in bloco


def test_hidden_vence_qualquer_display_de_autor():
    """Sem isto o painel invisível intercepta todos os cliques da página."""
    css = _texto(CSS)
    assert "[hidden] { display: none !important; }" in css


def test_a_tela_tem_tema_claro_e_escuro():
    css = _texto(CSS)
    assert "prefers-color-scheme: dark" in css
    assert 'name="color-scheme"' in _texto(HTML)


def test_alvos_de_toque_de_44px():
    css = _texto(CSS)
    assert "width: 44px; height: 44px" in css      # botão de menu
    assert "min-height: 44px" in css               # itens de navegação


def test_a_ui_escapa_conteudo_antes_de_inserir_no_dom():
    js = _texto(JS_APP)
    assert "function esc(" in js
    assert "&lt;" in js and "&quot;" in js
    # innerHTML sempre acompanhado de esc() em algum ponto do arquivo
    assert js.count("esc(") > 40
