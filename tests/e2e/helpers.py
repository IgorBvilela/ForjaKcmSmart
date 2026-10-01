"""Apoio dos testes E2E: ids dos equipamentos de demonstração, esperas web-first e leitores de DOM.

Tudo o que o Playwright toca é `data-testid` (frontend/src/lib/testids.ts) ou `data-*` de estado.
"""

from __future__ import annotations

import re
import time
from typing import Any

from playwright.sync_api import Locator, Page, expect

EQ_MAIN = "GTEX_PHA_PO_BASE"
EQ_BARRILHA = "EXEMPLO_BARRILHA"
EQ_KCM03 = "EXEMPLO_KCM_03"
ALL_EQUIPMENTS = (EQ_MAIN, EQ_BARRILHA, EQ_KCM03)

TILE_TAGS = ("mass_flow", "setpoint", "drive_command", "rpm", "belt_load", "int_channel_pct")

DIAGNOSIS_SECTIONS = (
    "RESUMO",
    "EVIDENCIAS",
    "O_QUE_MUDOU",
    "HIPOTESES",
    "PROXIMAS_VERIFICACOES",
    "FONTES",
    "RESSALVAS",
)

SCENARIOS = (
    "NORMAL_OPERATION",
    "BELTLOAD_LOW",
    "RATE_LOW",
    "ENCODER_FAILURE",
    "SFT_FAILURE",
    "DRIVE_COMMAND_HIGH",
    "INT_CHANNEL_DEGRADED",
    "COMMUNICATION_FAILURE",
    "STOP_NORMAL",
)

COMMAND_WORDS = re.compile(
    r"\b(run|stop|parar|iniciar|ligar|desligar|reset|resetar|tare|tara|span|calibrar|"
    r"feed factor|zerar|setpoint)\b",
    re.IGNORECASE,
)

"""Botão de explicação do contrato ("Entender esta variável: <nome>"): abre o explanation_pt da
API. O nome da variável (ex.: Setpoint) não é comando; é a única exceção à varredura."""
EXPLAIN_CONTROL = re.compile(r"^<button( expands)?> Entender esta variável\b")

PT_NUMBER = re.compile(r"^-?\d{1,3}(\.\d{3})*(,\d+)?$")
RAW_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")


def is_command_control(text: str) -> bool:
    """True quando um controle acionável carrega palavra de comando (fora do simulador)."""
    if EXPLAIN_CONTROL.match(text):
        return False
    return COMMAND_WORDS.search(text) is not None


def css_ms(value: str) -> float:
    """'80ms' → 80; '0s' → 0; '0.5s' → 500. Navegadores normalizam 0ms para 0s."""
    v = value.strip()
    if v.endswith("ms"):
        return float(v[:-2])
    if v.endswith("s"):
        return float(v[:-1]) * 1000
    return float(v)


# BELTLOAD_LOW: carga cai a 45% entre 5 s e 65 s; regra persiste 10 s. Na Barrilha isso conta
# desde o boot do Edge; na pior ordem de execução ainda sobra folga.
EVENT_TIMEOUT_MS = 150_000
MATERIAL_DROP_TIMEOUT_MS = 60_000

READY_BY_SLUG: dict[str, str] = {
    "plant": "[data-testid='plant-grid']",
    "dashboard": "[data-testid='kpi-grid']",
    "events": "[data-testid='events-list'], [data-testid='empty-state']",
    "diagnostics": "[data-testid='events-list'], [data-testid='empty-state']",
    "simulator": "[data-testid='sim-scenarios']",
    "system-about": "[data-testid='about']",
}


def open_route(page: Page, path: str, slug: str | None = None) -> Locator:
    """Navega com `load` (o SSE nunca deixa a rede ociosa) e espera a página da rota montar.

    Para as rotas com conteúdo assíncrono, espera também o bloco principal (ou o estado vazio).
    Se o Edge responder JSON (`UI_NOT_BUILT`: o dist está sendo reconstruído por outra mesa neste
    instante), tenta de novo algumas vezes com espera curta."""
    for attempt in range(4):
        response = page.goto(path, wait_until="load")
        content_type = (response.headers.get("content-type", "") if response else "").lower()
        if "application/json" not in content_type or attempt == 3:
            break
        time.sleep(1.5)
    page_locator = (
        page.locator(f"[data-testid='page'][data-route='{slug}']")
        if slug
        else page.get_by_test_id("page")
    )
    expect(page_locator).to_be_visible()
    ready = READY_BY_SLUG.get(slug or "", "[data-testid='empty-state']")
    expect(page.locator(ready).first).to_be_visible()
    return page_locator


def overflow_info(page: Page) -> dict[str, Any]:
    """Largura rolável x largura visível, e os primeiros elementos que ultrapassam a viewport."""
    return page.evaluate(
        """() => {
          const doc = document.documentElement;
          const vw = window.innerWidth;
          const wide = [];
          for (const el of document.querySelectorAll('body *')) {
            const r = el.getBoundingClientRect();
            if (r.width > 0 && r.right > vw + 1) {
              const cls = typeof el.className === 'string' ? el.className.split(' ')[0] : '';
              wide.push(`${el.tagName.toLowerCase()}` +
                (el.dataset.testid ? `[${el.dataset.testid}]` : '') +
                (cls ? '.' + cls : '') +
                ` right=${Math.round(r.right)}`);
              if (wide.length >= 6) break;
            }
          }
          return {
            overflow: doc.scrollWidth > doc.clientWidth || document.body.scrollWidth > vw,
            scrollWidth: Math.max(doc.scrollWidth, document.body.scrollWidth),
            clientWidth: doc.clientWidth,
            innerWidth: vw,
            wide,
          };
        }"""
    )


def control_texts(page: Page, within: str = "body") -> list[str]:
    """Texto visível + aria-label + title de tudo que parece acionável (botão, link, summary).

    Cada item vem como `<tag> texto`. Botão com `aria-expanded` (tooltip/disclosure, só revela
    informação) vem como `<button expands>`, para separar de botão que age."""
    return page.evaluate(
        """(sel) => {
          const root = document.querySelector(sel);
          if (!root) return [];
          const nodes = root.querySelectorAll(
            "button, a[href], [role='button'], input[type='button'], input[type='submit'], summary"
          );
          const out = [];
          for (const el of nodes) {
            const parts = [el.textContent, el.getAttribute('aria-label'), el.getAttribute('title'),
              el.value && el.tagName === 'INPUT' ? el.value : ''];
            const text = parts.filter(Boolean).join(' | ').replace(/\\s+/g, ' ').trim();
            const tag = el.tagName.toLowerCase();
            const expands = tag === 'button' && el.hasAttribute('aria-expanded');
            const kind = expands ? 'button expands' : tag;
            out.push(`<${kind}> ${text}`);
          }
          return out;
        }""",
        within,
    )


def input_types(page: Page, within: str = "body") -> list[str]:
    return page.evaluate(
        "(sel) => Array.from(document.querySelector(sel)?.querySelectorAll('input') ?? [])"
        ".map(i => i.type)",
        within,
    )


def set_scenario_via_api(page: Page, equipment_id: str, scenario: str) -> None:
    """Troca de cenário pela API (só 127.0.0.1). Usada para repor o estado após um teste."""
    resp = page.request.post(
        f"/api/v1/simulator/{equipment_id}/scenario", data={"scenario": scenario}
    )
    assert resp.ok, f"POST scenario {scenario} em {equipment_id}: {resp.status} {resp.text()}"


def wait_for_event(
    page: Page,
    equipment_id: str,
    *,
    title_pt: str | None = None,
    timeout_ms: int = EVENT_TIMEOUT_MS,
) -> dict[str, Any]:
    """Espera (pela API local) um evento do equipamento; devolve o mais recente que casar."""
    deadline = time.monotonic() + timeout_ms / 1000
    last: Any = None
    while time.monotonic() < deadline:
        resp = page.request.get(f"/api/v1/equipments/{equipment_id}/events", params={"limit": 20})
        if resp.ok:
            last = resp.json()
            for ev in last.get("events", []):
                if title_pt is None or ev.get("title_pt") == title_pt:
                    return ev
        time.sleep(1.0)
    raise AssertionError(
        f"nenhum evento{' ' + title_pt if title_pt else ''} em {equipment_id} após "
        f"{timeout_ms / 1000:.0f} s; última resposta: {last}"
    )
