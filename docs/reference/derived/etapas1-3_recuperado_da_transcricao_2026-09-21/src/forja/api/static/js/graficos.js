/* ===========================================================================
   Gráficos em SVG puro.

   Sem biblioteca e sem CDN de propósito: o Edge roda num notebook dentro da
   planta e pode não ter internet. Uma série temporal com linha, área e
   marcação de trecho sem dado não justifica 300 kB de dependência.

   O que este módulo NÃO faz:
   - não interpola trecho sem leitura. Buraco no dado aparece como buraco,
     nunca como linha reta ligando os dois lados;
   - não esconde valor STALE: o trecho fica hachurado, para que ninguém leia
     um patamar plano como se a máquina estivesse estável.
   =========================================================================== */
(function (global) {
  "use strict";

  const NS = "http://www.w3.org/2000/svg";
  const L = 40, R = 8, T = 10, B = 18;      // margens internas
  const FRESCO = new Set(["GOOD", "SIMULATED", "UNCERTAIN"]);

  function el(nome, attrs) {
    const n = document.createElementNS(NS, nome);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    return n;
  }

  /** Formata número para eixo: curto, sem ruído de casas decimais. */
  function fmt(v) {
    const a = Math.abs(v);
    if (a >= 1000) return Math.round(v).toLocaleString("pt-BR");
    if (a >= 100)  return v.toFixed(0);
    if (a >= 10)   return v.toFixed(1);
    if (a >= 1)    return v.toFixed(2);
    return v.toFixed(3);
  }

  function horaCurta(iso) {
    const d = new Date(iso);
    return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  }

  /**
   * Desenha a série num <svg>.
   * pontos: [{ts, value, quality}] em ordem crescente de tempo.
   */
  function desenhar(svg, pontos, opcoes) {
    opcoes = opcoes || {};
    while (svg.firstChild) svg.removeChild(svg.firstChild);

    const numericos = pontos.filter(p => typeof p.value === "number" && isFinite(p.value));
    if (numericos.length < 2) {
      svg.appendChild(el("text", {
        x: "50%", y: "50%", "text-anchor": "middle", "dominant-baseline": "middle",
        fill: "currentColor", "font-size": "11.5", opacity: ".45"
      })).textContent = "dados insuficientes";
      return null;
    }

    const cx = svg.clientWidth || 320;
    const cy = svg.clientHeight || 108;
    svg.setAttribute("viewBox", `0 0 ${cx} ${cy}`);
    svg.setAttribute("preserveAspectRatio", "none");

    const larg = cx - L - R;
    const alt = cy - T - B;

    const t0 = new Date(pontos[0].ts).getTime();
    const t1 = new Date(pontos[pontos.length - 1].ts).getTime();
    const dt = Math.max(1, t1 - t0);

    let min = Math.min(...numericos.map(p => p.value));
    let max = Math.max(...numericos.map(p => p.value));
    if (min === max) { min -= 1; max += 1; }         // série plana ainda precisa de altura
    const folga = (max - min) * 0.12;
    min -= folga; max += folga;

    const px = ts => L + ((new Date(ts).getTime() - t0) / dt) * larg;
    const py = v => T + alt - ((v - min) / (max - min)) * alt;

    // --- grade horizontal discreta
    for (let i = 0; i <= 2; i++) {
      const v = min + (max - min) * (i / 2);
      const y = py(v);
      svg.appendChild(el("line", {
        x1: L, y1: y, x2: cx - R, y2: y,
        stroke: "currentColor", "stroke-width": ".5", opacity: ".12"
      }));
      const t = el("text", {
        x: L - 5, y: y + 3.5, "text-anchor": "end",
        fill: "currentColor", "font-size": "9.5", opacity: ".5"
      });
      t.textContent = fmt(v);
      svg.appendChild(t);
    }

    // --- faixas onde o dado não era fresco (STALE ou COMM_ERROR)
    let inicio = null;
    pontos.forEach((p, i) => {
      const velho = !FRESCO.has(p.quality);
      if (velho && inicio === null) inicio = p.ts;
      if ((!velho || i === pontos.length - 1) && inicio !== null) {
        const x1 = px(inicio), x2 = px(p.ts);
        if (x2 - x1 >= 1) {
          svg.appendChild(el("rect", {
            x: x1, y: T, width: Math.max(2, x2 - x1), height: alt,
            class: "marca-stale"
          }));
        }
        inicio = null;
      }
    });

    // --- linha de referência (setpoint, por exemplo)
    if (typeof opcoes.referencia === "number" &&
        opcoes.referencia >= min && opcoes.referencia <= max) {
      svg.appendChild(el("line", {
        x1: L, y1: py(opcoes.referencia), x2: cx - R, y2: py(opcoes.referencia),
        class: "linha-ref"
      }));
    }

    // --- caminho da série, quebrando em trechos sem dado fresco
    const trechos = [];
    let atual = [];
    for (const p of pontos) {
      const ok = typeof p.value === "number" && isFinite(p.value) && FRESCO.has(p.quality);
      if (ok) {
        atual.push(p);
      } else if (atual.length) {
        trechos.push(atual); atual = [];
      }
    }
    if (atual.length) trechos.push(atual);

    let d = "";
    for (const trecho of trechos) {
      if (trecho.length === 1) {
        // ponto isolado: marca, não inventa linha
        svg.appendChild(el("circle", {
          cx: px(trecho[0].ts), cy: py(trecho[0].value), r: 1.8,
          fill: "currentColor", class: "linha-serie", "stroke-width": "0"
        }));
        continue;
      }
      d += trecho.map((p, i) => `${i ? "L" : "M"}${px(p.ts).toFixed(1)},${py(p.value).toFixed(1)}`).join("");
    }

    if (d) {
      // área sob a curva, só do primeiro trecho contínuo mais longo
      const maior = trechos.reduce((a, b) => (b.length > a.length ? b : a), []);
      if (maior.length > 1) {
        const dArea = maior.map((p, i) => `${i ? "L" : "M"}${px(p.ts).toFixed(1)},${py(p.value).toFixed(1)}`).join("")
          + `L${px(maior[maior.length - 1].ts).toFixed(1)},${(T + alt).toFixed(1)}`
          + `L${px(maior[0].ts).toFixed(1)},${(T + alt).toFixed(1)}Z`;
        svg.appendChild(el("path", { d: dArea, class: "area-serie" }));
      }

      const linha = el("path", { d: d, class: "linha-serie" });
      svg.appendChild(linha);

      // desenho progressivo, só quando o movimento é bem-vindo
      const reduzir = global.matchMedia &&
                      global.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (!reduzir && opcoes.animar !== false) {
        try {
          const comp = linha.getTotalLength();
          if (comp && isFinite(comp)) {
            linha.style.setProperty("--comprimento", comp);
            linha.classList.add("is-desenhando");
          }
        } catch (_) { /* getTotalLength pode falhar em SVG oculto; segue sem animar */ }
      }
    }

    // --- último ponto em destaque
    const ultimoFresco = [...pontos].reverse()
      .find(p => typeof p.value === "number" && FRESCO.has(p.quality));
    if (ultimoFresco) {
      svg.appendChild(el("circle", {
        cx: px(ultimoFresco.ts), cy: py(ultimoFresco.value), r: 3,
        fill: "var(--acento)", stroke: "var(--superficie)", "stroke-width": "1.6"
      }));
    }

    return { min: min, max: max, t0: pontos[0].ts, t1: pontos[pontos.length - 1].ts };
  }

  global.Graficos = { desenhar: desenhar, fmt: fmt, horaCurta: horaCurta };

})(window);
