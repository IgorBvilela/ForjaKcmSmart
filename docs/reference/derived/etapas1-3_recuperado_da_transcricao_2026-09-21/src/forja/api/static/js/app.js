/* ===========================================================================
   Forja KCM — Edge (interface local)

   Esta tela consome o JSON da API. Em especial, o diagnóstico vem de
   GET /api/events/{id}/diagnosis, que é o CONTRATO versionado
   (diagnosis_schema_version). Nada aqui reparseia texto formatado.

   Princípio de apresentação: a tela nunca é mais confiante que o dado.
   - origem simulada fica visível o tempo todo;
   - valor antigo mostra a idade, nunca se passa por leitura de agora;
   - cada hipótese e cada verificação exibem o próprio nível de evidência.
   =========================================================================== */
(function () {
  "use strict";

  const CONTRATO_SUPORTADO = "1.";        // esta UI lê a família 1.x

  const TAGS_PAINEL = [
    "machine_state", "setpoint", "mass_flow", "drive_command", "rpm",
    "belt_load", "net_weight", "alarm_code", "stop_by", "motor_load_pct",
    "int_channel_pct", "sft_list"
  ];
  const TAGS_GRAFICO = ["mass_flow", "drive_command", "rpm", "belt_load",
                        "motor_load_pct", "int_channel_pct"];

  const estado = {
    aba: "painel",
    janelaMin: 5,
    filtroEventos: "todos",
    ultimoValor: {},
    status: null,
    timerAoVivo: null,
    diagAberto: null,
  };

  const $ = s => document.querySelector(s);
  const $$ = s => Array.from(document.querySelectorAll(s));

  /* ------------------------------------------------------------------ util */

  function esc(v) {
    if (v === null || v === undefined) return "";
    return String(v)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  async function api(caminho) {
    const r = await fetch(caminho, { headers: { "Accept": "application/json" } });
    if (!r.ok) throw new Error(caminho + " → " + r.status);
    return r.json();
  }

  function numero(v, casas) {
    if (typeof v !== "number") return String(v);
    return v.toLocaleString("pt-BR", {
      minimumFractionDigits: casas === undefined ? 0 : casas,
      maximumFractionDigits: casas === undefined ? 2 : casas
    });
  }

  function duracao(seg) {
    if (seg < 60) return Math.round(seg) + " s";
    if (seg < 3600) return Math.round(seg / 60) + " min";
    return (seg / 3600).toFixed(1) + " h";
  }

  function dataHora(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleString("pt-BR", {
      day: "2-digit", month: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit"
    });
  }

  function desde(iso) {
    if (!iso) return "";
    const s = (Date.now() - new Date(iso).getTime()) / 1000;
    if (s < 0) return "agora";
    return "há " + duracao(s);
  }

  /* --------------------------------------------------------------- navegação */

  function trocarAba(nome) {
    estado.aba = nome;
    $$(".nav__item").forEach(b => b.classList.toggle("is-ativo", b.dataset.aba === nome));
    $$(".aba").forEach(s => {
      const ativa = s.id === "aba-" + nome;
      s.classList.toggle("is-ativa", ativa);
      s.hidden = !ativa;
    });
    fecharDrawer();
    if (nome === "tendencias") carregarTendencias();
    if (nome === "eventos") carregarEventos();
    if (nome === "maquina") carregarFicha();
  }

  function abrirDrawer() {
    $("#nav").classList.add("is-aberta");
    $("#menuBotao").setAttribute("aria-expanded", "true");
    $("#sombraDrawer").hidden = false;
  }
  function fecharDrawer() {
    $("#nav").classList.remove("is-aberta");
    $("#menuBotao").setAttribute("aria-expanded", "false");
    $("#sombraDrawer").hidden = true;
  }

  /* ------------------------------------------------------------------ status */

  async function atualizarStatus() {
    let st;
    try {
      st = await api("/api/status");
    } catch (_) {
      const selo = $("#seloConexao");
      selo.className = "selo is-offline";
      $("#textoConexao").textContent = "sem resposta do Edge";
      return;
    }
    estado.status = st;

    $("#equipamentoTag").textContent =
      st.equipment_id + (st.driver_detail && st.driver_detail.scenario
        ? " · " + st.driver_detail.scenario : "");

    // origem do dado — o selo que nunca pode sumir
    const origem = $("#seloOrigem");
    origem.hidden = false;
    if (st.data_is_simulated) {
      origem.textContent = "dado simulado";
      origem.classList.remove("is-real");
      const rod = $("#rodapeOrigem");
      rod.hidden = false;
      rod.textContent = "Estes números vêm do simulador, não de uma máquina real.";
    } else {
      origem.textContent = "leitura real";
      origem.classList.add("is-real");
      $("#rodapeOrigem").hidden = true;
    }

    const selo = $("#seloConexao");
    selo.className = "selo " + (st.connected ? "is-online" : "is-offline");
    $("#textoConexao").textContent = st.connected ? "coletando" : "sem leitura";

    // faixa de aviso quando a comunicação está degradada
    const faixa = $("#faixaAviso");
    const falhas = st.acquisition.consecutive_failed_cycles || 0;
    if (falhas > 0) {
      faixa.hidden = false;
      faixa.className = "faixa-aviso faixa-aviso--critico";
      faixa.innerHTML =
        '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 2 20h20L12 3Z"/>' +
        '<line x1="12" y1="10" x2="12" y2="14"/><circle cx="12" cy="17" r="1"/></svg>' +
        "<div><b>A leitura está falhando.</b> " + falhas +
        " ciclo(s) seguido(s) sem resposta. Os valores abaixo são os últimos " +
        "conhecidos e estão marcados com a idade — não são leituras de agora.</div>";
    } else {
      faixa.hidden = true;
    }

    const abertos = (st.events && st.events.open_now) ? st.events.open_now.length : 0;
    const cont = $("#contadorEventos");
    cont.hidden = abertos === 0;
    cont.textContent = abertos;

    renderMedidores(st);
  }

  function renderMedidores(st) {
    const a = st.acquisition, h = st.historian;
    const itens = [
      ["ciclos", numero(a.cycles), false],
      ["amostras", numero(h.samples_total), false],
      ["falhas de leitura", numero(a.read_failures), a.read_failures > 0],
      ["ciclos sem resposta", numero(a.consecutive_failed_cycles), a.consecutive_failed_cycles > 0],
      ["eventos", numero(h.events_total), false],
      ["última leitura boa", desde(a.last_good_cycle_ts) || "—", false],
    ];
    $("#medidores").innerHTML = itens.map(([r, v, ruim]) =>
      '<div class="medidor"><div class="medidor__rotulo">' + esc(r) + "</div>" +
      '<div class="medidor__valor num' + (ruim ? " is-ruim" : "") + '">' + esc(v) + "</div></div>"
    ).join("");
  }

  /* ------------------------------------------------------------------ painel */

  async function atualizarPainel() {
    let dados;
    try { dados = await api("/api/latest"); } catch (_) { return; }

    const alvo = $("#cartoes");
    const ordenadas = TAGS_PAINEL.filter(t => dados[t]);
    Object.keys(dados).forEach(t => { if (!ordenadas.includes(t)) ordenadas.push(t); });

    alvo.innerHTML = ordenadas.map(tag => {
      const s = dados[tag];
      const ehNum = typeof s.value === "number";
      const mudou = estado.ultimoValor[tag] !== undefined &&
                    estado.ultimoValor[tag] !== s.value;
      estado.ultimoValor[tag] = s.value;

      const idade = s.age_s !== undefined && s.age_s > 0
        ? '<span class="idade">de ' + duracao(s.age_s) + " atrás</span>" : "";

      return '<article class="cartao' + (mudou ? " is-novo" : "") + '" data-q="' + esc(s.quality) + '">' +
        '<div class="cartao__rotulo">' + esc(s.display_name) + "</div>" +
        '<div class="cartao__valor num' + (ehNum ? "" : " is-texto") + '">' +
          esc(ehNum ? numero(s.value, casasDe(tag)) : (s.value === "" ? "—" : s.value)) +
          (s.unit ? '<span class="cartao__unidade">' + esc(s.unit) + "</span>" : "") +
        "</div>" +
        '<div class="cartao__pe">' +
          '<span class="etiqueta-q" data-q="' + esc(s.quality) + '">' + esc(s.quality) + "</span>" +
          idade +
        "</div></article>";
    }).join("");
  }

  function casasDe(tag) {
    if (tag === "belt_load" || tag === "vol_belt_load") return 3;
    if (tag === "net_weight" || tag === "gross_weight" || tag === "tare") return 4;
    if (tag === "alarm_code") return 0;
    return 1;
  }

  /* -------------------------------------------------------------- tendências */

  async function carregarTendencias() {
    const alvo = $("#graficos");
    alvo.innerHTML = '<div class="carregando">carregando séries</div>';

    let setpoint = null;
    try {
      const ult = await api("/api/latest");
      if (ult.setpoint && typeof ult.setpoint.value === "number") setpoint = ult.setpoint.value;
    } catch (_) { /* segue sem referência */ }

    const blocos = await Promise.all(TAGS_GRAFICO.map(async tag => {
      try {
        const r = await api("/api/samples?tag=" + encodeURIComponent(tag) +
                            "&minutes=" + estado.janelaMin + "&limit=1200");
        return { tag: tag, dados: r };
      } catch (_) { return null; }
    }));

    const validos = blocos.filter(b => b && b.dados.samples.length);
    if (!validos.length) {
      alvo.innerHTML = '<div class="vazio">Ainda não há histórico nesta janela. ' +
                       'Deixe a coleta rodar alguns minutos.</div>';
      return;
    }

    alvo.innerHTML = validos.map(b => {
      const s = b.dados.samples;
      const ultimo = s[s.length - 1];
      const unidade = ultimo.unit ? " <small>" + esc(ultimo.unit) + "</small>" : "";
      return '<section class="grafico" data-tag="' + esc(b.tag) + '">' +
        '<div class="grafico__topo">' +
          '<span class="grafico__nome">' + esc(ultimo.display_name) + "</span>" +
          '<span class="grafico__atual num">' +
            esc(typeof ultimo.value === "number" ? numero(ultimo.value, casasDe(b.tag)) : ultimo.value) +
            unidade + "</span>" +
        "</div><svg></svg>" +
        '<div class="grafico__faixa"><span>' + esc(Graficos.horaCurta(s[0].ts)) + "</span>" +
        "<span>" + esc(Graficos.horaCurta(ultimo.ts)) + "</span></div></section>";
    }).join("");

    // desenha depois de o SVG existir no DOM (precisa de largura medida)
    requestAnimationFrame(() => {
      validos.forEach(b => {
        const svg = alvo.querySelector('[data-tag="' + b.tag + '"] svg');
        if (!svg) return;
        Graficos.desenhar(svg, b.dados.samples,
          { referencia: b.tag === "mass_flow" ? setpoint : null });
      });
    });
  }

  /* ----------------------------------------------------------------- eventos */

  async function carregarEventos() {
    const alvo = $("#listaEventos");
    let r;
    try {
      r = await api("/api/events?minutes=1440&limit=200");
    } catch (_) {
      alvo.innerHTML = '<div class="vazio">Não foi possível carregar os eventos.</div>';
      return;
    }

    let lista = r.events;
    if (estado.filtroEventos === "abertos") lista = lista.filter(e => e.open);

    $("#contagemEventos").textContent =
      lista.length + (lista.length === 1 ? " evento" : " eventos");

    if (!lista.length) {
      alvo.innerHTML = '<div class="vazio">' +
        (estado.filtroEventos === "abertos"
          ? "Nenhum evento aberto agora."
          : "Nenhum evento nas últimas 24 h.") + "</div>";
      return;
    }

    alvo.innerHTML = lista.map(e => {
      const dur = e.ts_end
        ? duracao((new Date(e.ts_end) - new Date(e.ts_start)) / 1000)
        : desde(e.ts_start);
      return '<button class="evento" data-sev="' + esc(e.severity) + '" data-id="' + e.id + '">' +
        '<div class="evento__linha1">' +
          '<span class="sev" data-sev="' + esc(e.severity) + '">' + esc(e.severity) + "</span>" +
          '<span class="evento__tipo">' + esc(e.type) + "</span>" +
          (e.open ? '<span class="aberto-agora">aberto</span>' : "") +
        "</div>" +
        '<div class="evento__resumo">' + esc(e.summary || "—") + "</div>" +
        '<div class="evento__linha3">' +
          "<span>" + esc(dataHora(e.ts_start)) + "</span>" +
          "<span>" + esc(e.open ? dur : "durou " + dur) + "</span>" +
          "<span>" + esc(e.rule_id) + " v" + esc(e.rule_version) + "</span>" +
        "</div></button>";
    }).join("");
  }

  /* ------------------------------------------------------------- diagnóstico */

  async function abrirDiagnostico(id) {
    const painel = $("#diagnostico");
    const corpo = $("#diagCorpo");
    painel.hidden = false;
    $("#sombraPainel").hidden = false;
    document.body.style.overflow = "hidden";
    estado.diagAberto = id;
    $("#diagTipo").textContent = "carregando";
    $("#diagResumo").textContent = "…";
    corpo.innerHTML = '<div class="carregando">montando diagnóstico</div>';
    $("#fecharDiag").focus();

    let d;
    try {
      d = await api("/api/events/" + id + "/diagnosis");
    } catch (_) {
      corpo.innerHTML = '<div class="vazio">Não foi possível carregar o diagnóstico.</div>';
      return;
    }

    // A UI declara que família de contrato entende. Se o backend saltar para
    // 2.x, é melhor avisar do que renderizar errado em silêncio.
    const versao = d.diagnosis_schema_version || "?";
    const incompativel = !String(versao).startsWith(CONTRATO_SUPORTADO);

    $("#diagTipo").textContent = d.event_type + " · " + (d.severity || "");
    $("#diagResumo").textContent = d.summary || "(sem resumo)";

    const partes = [];

    if (incompativel) {
      partes.push('<div class="ressalva ressalva--forte">Esta tela lê o contrato ' +
        CONTRATO_SUPORTADO + 'x e recebeu ' + esc(versao) +
        ". Alguns campos podem não aparecer.</div>");
    }

    if (!d.available) {
      partes.push('<div class="vazio">' + esc(d.reason || "sem diagnóstico") + "</div>");
      corpo.innerHTML = partes.join("");
      return;
    }

    /* ---- Resumo ---- */
    partes.push('<div class="pergunta">' + esc(d.question) + "</div>");
    if (d.data_origin === "SIMULADO") {
      partes.push('<div class="ressalva ressalva--forte">' +
        "Origem simulada: estas evidências vieram do simulador, não de uma máquina real.</div>");
    }

    /* ---- Evidências ---- */
    if (d.evidences && d.evidences.length) {
      partes.push(secao("Evidências", d.evidences.map(e =>
        '<div class="evidencia">' +
          '<span class="evidencia__rotulo">' + esc(e.label) + "</span>" +
          '<span class="evidencia__valor">' +
            esc(typeof e.value === "number" ? numero(e.value, 2) : e.value) +
            (e.unit ? " " + esc(e.unit) : "") + "</span>" +
          '<span class="etiqueta-q" data-q="' + esc(e.quality) + '">' + esc(e.quality) + "</span>" +
          (e.note ? '<span class="evidencia__nota">' + esc(e.note) + "</span>" : "") +
        "</div>"
      ).join("")));
    }

    /* ---- O que mudou ---- */
    if (d.changed && d.changed.length) {
      partes.push(secao("O que mudou desde antes do evento", d.changed.map(c => {
        const temDelta = typeof c.delta === "number";
        const classe = temDelta ? (c.delta > 0 ? " is-sobe" : " is-desce") : "";
        return '<div class="mudanca">' +
          "<span>" + esc(c.label) + "</span>" +
          '<span class="mudanca__de num">' + esc(numero(c.before, 2)) + "</span>" +
          '<span class="mudanca__seta">→</span>' +
          '<span class="mudanca__para num">' + esc(numero(c.after, 2)) + "</span>" +
          (temDelta ? '<span class="mudanca__delta' + classe + ' num">' +
            (c.delta > 0 ? "+" : "") + esc(numero(c.delta, 2)) + "</span>" : "") +
          "</div>";
      }).join("")));
    }

    /* ---- Hipóteses ---- */
    if (d.hypotheses && d.hypotheses.length) {
      partes.push(secao("Hipóteses", d.hypotheses.map(h =>
        '<article class="hipotese" data-rank="' + esc(h.rank) + '">' +
          '<div class="hipotese__topo">' +
            '<span class="hipotese__nome">' + esc(h.name) + "</span>" +
            '<span class="ordem" data-rank="' + esc(h.rank) + '">' +
              esc(String(h.rank).replace(/_/g, " ")) + "</span>" +
            nivelHtml(h) +
          "</div>" +
          (h.statement ? '<p class="hipotese__campo"><b>O que seria:</b> ' + esc(h.statement) + "</p>" : "") +
          (h.rationale ? '<p class="hipotese__campo"><b>Por que está na lista:</b> ' + esc(h.rationale) + "</p>" : "") +
          (h.discriminator ? '<p class="hipotese__campo"><b>Confirma ou descarta:</b> ' + esc(h.discriminator) + "</p>" : "") +
          referenciaHtml(h.doc_reference) +
        "</article>"
      ).join("") +
      '<p class="resumo-evidencia">As hipóteses estão em <b>ordem de verificação</b>, ' +
      "não em probabilidade calculada. Não há estatística por trás.</p>"));
    }

    /* ---- Próximas verificações ---- */
    if (d.checks && d.checks.length) {
      partes.push(secao("Próximas verificações", d.checks.map(c => {
        const marcas = [];
        if (c.invasive) marcas.push('<span class="marca-aviso marca-aviso--invasiva">invasiva</span>');
        if (c.requires_stop) marcas.push('<span class="marca-aviso marca-aviso--parada">exige máquina parada</span>');
        if (c.tool) marcas.push('<span class="marca-aviso marca-aviso--ferramenta">' + esc(c.tool) + "</span>");
        return '<div class="verificacao">' +
          '<div class="verificacao__n num">' + esc(c.order) + "</div>" +
          "<div>" +
            '<div class="verificacao__acao">' + esc(c.action) + "</div>" +
            '<div class="verificacao__linha"><b>Esperado:</b> ' + esc(c.expected) + "</div>" +
            '<div class="verificacao__marcas">' + nivelHtml(c) + marcas.join("") + "</div>" +
            (c.safety_note ? '<div class="seguranca">' +
              '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 2 20h20L12 3Z"/>' +
              '<line x1="12" y1="10" x2="12" y2="14"/><circle cx="12" cy="17" r="1"/></svg>' +
              esc(c.safety_note) + "</div>" : "") +
          "</div></div>";
      }).join("") +
      '<p class="resumo-evidencia">Todas as verificações são executadas por uma pessoa. ' +
      "Este sistema <b>nunca escreve no controlador</b>.</p>"));
    }

    /* ---- Casos relacionados ---- */
    if (d.related_cases && d.related_cases.length) {
      partes.push(secao("Casos de campo relacionados", d.related_cases.map(c =>
        '<article class="caso">' +
          '<div class="hipotese__topo"><span class="caso__id">' + esc(c.case_id) + "</span>" +
            nivelHtml(c) + "</div>" +
          '<p class="caso__campo">' + esc(c.symptom) + "</p>" +
          '<p class="caso__campo"><b>Causa confirmada:</b> ' + esc(c.confirmed_cause) + "</p>" +
          '<p class="caso__campo">' + esc(c.scope_note) + "</p>" +
          (c.lessons && c.lessons.length
            ? '<ul class="caso__licoes">' + c.lessons.map(l => "<li>" + esc(l) + "</li>").join("") + "</ul>"
            : "") +
        "</article>"
      ).join("")));
    }

    /* ---- Fontes ---- */
    if (d.sources && d.sources.length) {
      const ordenadas = d.sources.slice().sort((a, b) =>
        (b.evidence_rank || 0) - (a.evidence_rank || 0));
      const resumo = d.evidence_summary || {};
      partes.push(secao("Fontes", ordenadas.map(s =>
        '<div class="fonte">' +
          '<div class="fonte__topo">' +
            '<span class="fonte__tipo">' + esc(s.kind) + "</span>" +
            '<span class="fonte__ref">' + esc(s.reference) + "</span>" +
            nivelHtml(s) +
          "</div>" +
          (s.detail ? '<div class="fonte__detalhe">' + esc(s.detail) + "</div>" : "") +
          referenciaHtml(s.doc_reference) +
        "</div>"
      ).join("") +
      '<div class="resumo-evidencia">' +
        "Elo mais fraco entre as hipóteses: <b>" +
        esc(resumo.weakest_hypothesis_label || "—") + "</b>.<br>" +
        (resumo.has_manufacturer_documentation
          ? "Há afirmações documentadas pelo fabricante neste diagnóstico."
          : "<b>Nenhuma afirmação deste diagnóstico está documentada pelo fabricante.</b>") +
      "</div>"));
    }

    /* ---- Ressalvas ---- */
    if (d.caveats && d.caveats.length) {
      partes.push(secao("Ressalvas", d.caveats.map(c =>
        '<div class="ressalva">' +
          '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/>' +
          '<line x1="12" y1="8" x2="12" y2="13"/><circle cx="12" cy="16" r="1"/></svg>' +
          "<span>" + esc(c) + "</span></div>"
      ).join("")));
    }

    partes.push('<p class="resumo-evidencia">Contrato <b>' + esc(versao) +
      "</b> · evento #" + esc(d.event_id) + " · regra " +
      esc((d.rule && d.rule.id) || "—") + " v" + esc((d.rule && d.rule.version) || "—") + "</p>");

    corpo.innerHTML = partes.join("");
    corpo.scrollTop = 0;
  }

  function secao(titulo, conteudo) {
    return '<section class="secao"><h3 class="secao__titulo">' + esc(titulo) +
           "</h3>" + conteudo + "</section>";
  }

  /** Selo de nível de evidência. Aparece em hipótese, verificação, fonte e caso. */
  function nivelHtml(item) {
    if (!item || !item.evidence_level) return "";
    return '<span class="nivel" data-n="' + esc(item.evidence_level) + '" title="' +
      esc(item.evidence_level) + '">' + esc(item.evidence_label || item.evidence_level) + "</span>";
  }

  /** Referência rastreável, com o que falta para promover. */
  function referenciaHtml(ref) {
    if (!ref || !ref.citation || ref.citation === "UNKNOWN") return "";
    let html = '<div class="referencia">' + esc(ref.citation);
    if (ref.missing && ref.missing.length) {
      html += '<br><span class="referencia__falta">falta para promover: ' +
              esc(ref.missing.join(", ")) + "</span>";
    }
    if (ref.note) html += "<br>" + esc(ref.note);
    return html + "</div>";
  }

  function fecharDiagnostico() {
    $("#diagnostico").hidden = true;
    $("#sombraPainel").hidden = true;
    document.body.style.overflow = "";
    const alvo = estado.diagAberto
      ? document.querySelector('.evento[data-id="' + estado.diagAberto + '"]') : null;
    estado.diagAberto = null;
    if (alvo) alvo.focus();
  }

  /* ------------------------------------------------------------------ ficha */

  async function carregarFicha() {
    const alvo = $("#ficha");
    let eq;
    try { eq = await api("/api/equipment"); }
    catch (_) { alvo.innerHTML = '<div class="vazio">Não foi possível carregar a ficha.</div>'; return; }

    const grupos = [];

    grupos.push(grupoFicha("Identificação", [
      ["Equipamento", eq.equipment_id], ["Planta", eq.plant], ["Área", eq.area],
      ["Linha", eq.line], ["TAG de campo", eq.tag], ["Descrição", eq.description],
    ]));

    const c = eq.controller || {};
    grupos.push(grupoFicha("Controlador", [
      ["Fabricante", c.manufacturer], ["Modelo", c.model], ["Aplicação", c.application],
      ["Firmware", c.firmware], ["Placa host", c.host_board], ["Protocolo", c.protocol],
      ["IP", c.ip], ["Arquivo host", c.host_file], ["K-PROM", c.kprom_present],
    ]));

    if (eq.environment) {
      grupos.push(grupoFicha("Ambiente",
        Object.entries(eq.environment).map(([k, v]) => [k.replace(/_/g, " "), v])));
    }

    (eq.components || []).forEach(comp => {
      const linhas = [["Part number", comp.part_number],
                      ["Verificado", comp.verified ? "sim" : "não"],
                      ["Fonte", comp.source]];
      Object.entries(comp.params || {}).forEach(([k, v]) => linhas.push([k.replace(/_/g, " "), v]));
      grupos.push(grupoFicha("Componente · " + comp.kind, linhas));
    });

    const mapeadas = (eq.mappings || []).filter(m => m.confirmed).length;
    grupos.push(grupoFicha("Mapeamento de tags", [
      ["Tags mapeadas", String((eq.mappings || []).length)],
      ["Confirmadas contra a máquina", String(mapeadas)],
      ["Endereços pendentes", String((eq.mappings || []).length - mapeadas)],
    ]));

    alvo.innerHTML = grupos.join("");
  }

  function grupoFicha(titulo, linhas) {
    return '<section class="ficha__grupo"><h3 class="ficha__titulo">' + esc(titulo) + "</h3>" +
      linhas.filter(([, v]) => v !== undefined && v !== null && v !== "").map(([k, v]) => {
        const desconhecido = String(v).toUpperCase() === "UNKNOWN";
        return '<div class="ficha__linha"><span class="ficha__chave">' + esc(k) + "</span>" +
          '<span class="ficha__valor' + (desconhecido ? " is-desconhecido" : "") + '">' +
          esc(desconhecido ? "não confirmado" : v) + "</span></div>";
      }).join("") + "</section>";
  }

  /* ------------------------------------------------------------------ eventos DOM */

  function ligar() {
    $("#menuBotao").addEventListener("click", () => {
      $("#nav").classList.contains("is-aberta") ? fecharDrawer() : abrirDrawer();
    });
    $("#sombraDrawer").addEventListener("click", fecharDrawer);

    $$(".nav__item").forEach(b =>
      b.addEventListener("click", () => trocarAba(b.dataset.aba)));

    $("#janelaTempo").addEventListener("click", ev => {
      const b = ev.target.closest("button");
      if (!b) return;
      estado.janelaMin = Number(b.dataset.min);
      $$("#janelaTempo button").forEach(x => x.classList.toggle("is-ativo", x === b));
      carregarTendencias();
    });
    $("#recarregarTend").addEventListener("click", carregarTendencias);

    $("#filtroEventos").addEventListener("click", ev => {
      const b = ev.target.closest("button");
      if (!b) return;
      estado.filtroEventos = b.dataset.filtro;
      $$("#filtroEventos button").forEach(x => x.classList.toggle("is-ativo", x === b));
      carregarEventos();
    });

    $("#listaEventos").addEventListener("click", ev => {
      const cartao = ev.target.closest(".evento");
      if (cartao) abrirDiagnostico(cartao.dataset.id);
    });

    $("#fecharDiag").addEventListener("click", fecharDiagnostico);
    $("#sombraPainel").addEventListener("click", fecharDiagnostico);

    document.addEventListener("keydown", ev => {
      if (ev.key !== "Escape") return;
      if (!$("#diagnostico").hidden) fecharDiagnostico();
      else if ($("#nav").classList.contains("is-aberta")) fecharDrawer();
    });

    // redesenha os gráficos quando a janela muda de largura
    let t;
    window.addEventListener("resize", () => {
      clearTimeout(t);
      t = setTimeout(() => { if (estado.aba === "tendencias") carregarTendencias(); }, 280);
    });

    // pausa o polling quando a aba do navegador não está visível
    document.addEventListener("visibilitychange", () => {
      document.hidden ? pararAoVivo() : iniciarAoVivo();
    });
  }

  /* ------------------------------------------------------------------ ao vivo */

  async function tick() {
    await atualizarStatus();
    if (estado.aba === "painel") await atualizarPainel();
    if (estado.aba === "eventos") await carregarEventos();
  }

  function iniciarAoVivo() {
    pararAoVivo();
    tick();
    estado.timerAoVivo = setInterval(tick, 2000);
  }
  function pararAoVivo() {
    if (estado.timerAoVivo) clearInterval(estado.timerAoVivo);
    estado.timerAoVivo = null;
  }

  /* ------------------------------------------------------------------ início */

  ligar();
  iniciarAoVivo();

})();
