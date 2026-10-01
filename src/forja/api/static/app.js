/* Forja KCM Intelligence: estado do Edge e equipamentos, lendo só a API local.
   Sem bibliotecas, sem CDN, sem innerHTML com dados (só textContent). */
(function () {
  "use strict";

  var API = "/api/v1";
  var INTERVALO_MS = 5000;

  function $(id) { return document.getElementById(id); }

  function el(tag, cls, texto) {
    var node = document.createElement(tag);
    if (cls) { node.className = cls; }
    if (texto !== undefined && texto !== null) { node.textContent = String(texto); }
    return node;
  }

  function limpar(node) { while (node.firstChild) { node.removeChild(node.firstChild); } }

  function fmtDuracao(segundos) {
    if (segundos === null || segundos === undefined || isNaN(segundos)) { return "—"; }
    var s = Math.floor(segundos);
    var d = Math.floor(s / 86400); s -= d * 86400;
    var h = Math.floor(s / 3600); s -= h * 3600;
    var m = Math.floor(s / 60); s -= m * 60;
    var partes = [];
    if (d) { partes.push(d + " d"); }
    if (d || h) { partes.push(h + " h"); }
    if (d || h || m) { partes.push(m + " min"); }
    partes.push(s + " s");
    return partes.join(" ");
  }

  function fmtNumero(valor, decimais) {
    if (valor === null || valor === undefined || isNaN(valor)) { return "—"; }
    return Number(valor).toLocaleString("pt-BR", {
      minimumFractionDigits: decimais, maximumFractionDigits: decimais
    });
  }

  function fmtHora(iso) {
    if (!iso) { return "—"; }
    var d = new Date(iso);
    if (isNaN(d.getTime())) { return "—"; }
    return d.toLocaleString("pt-BR");
  }

  function origemTexto(origem) {
    if (origem === "SIMULATED") { return "Dados simulados"; }
    if (origem === "EQUIPMENT") { return "Dados do equipamento"; }
    if (origem === "MIXED") { return "Dados mistos"; }
    return "Origem desconhecida";
  }

  function buscar(caminho) {
    return fetch(API + caminho, { headers: { "Accept": "application/json" }, cache: "no-store" })
      .then(function (r) {
        if (!r.ok) { throw new Error("HTTP " + r.status); }
        return r.json();
      });
  }

  function mostrarErro(id, mensagem) {
    var node = $(id);
    node.textContent = mensagem;
    node.hidden = false;
  }

  function esconderErro(id) { $(id).hidden = true; }

  function renderAbout(a) {
    $("f-nome").textContent = a.edge_name || a.name || "—";
    $("f-versao").textContent = a.version || "—";
    $("f-uptime").textContent = fmtDuracao(a.uptime_s);
    $("f-equip").textContent = a.equipment_count !== undefined ? a.equipment_count : "—";
    $("f-python").textContent = a.python || "—";
    $("f-sqlite").textContent = a.sqlite || "—";
    $("f-schema").textContent = a.diagnosis_schema_version ? "v" + a.diagnosis_schema_version : "—";
    $("f-tz").textContent = a.timezone || "—";

    var selo = $("selo-origem");
    selo.setAttribute("data-origem", a.data_source || "");
    selo.textContent = origemTexto(a.data_source);

    var docs = $("docs-estado");
    limpar(docs);
    if (a.docs_url) {
      var link = el("a", null, "abrir " + a.docs_url);
      link.href = a.docs_url;
      docs.appendChild(link);
      docs.appendChild(document.createTextNode(" (modo desenvolvimento)"));
    } else {
      docs.textContent = "disponível apenas em modo de desenvolvimento.";
    }
    $("f-host").textContent = window.location.host || "127.0.0.1";
  }

  function renderCard(c) {
    var li = el("li", "card");
    li.setAttribute("data-estado", c.state_pt || "Desconhecido");

    var topo = el("div", "card__topo");
    var titulo = el("div");
    titulo.appendChild(el("h3", "card__nome", c.name || c.id));
    titulo.appendChild(el("div", "card__id", c.id));
    topo.appendChild(titulo);
    var estado = el("span", "card__estado", c.state_pt || "Desconhecido");
    estado.setAttribute("data-estado", c.state_pt || "Desconhecido");
    topo.appendChild(estado);
    li.appendChild(topo);

    var valor = el("div", "card__valor");
    if (c.mass_flow) {
      var usavel = c.mass_flow.is_usable;
      valor.appendChild(el("span", "card__numero", usavel ? fmtNumero(c.mass_flow.value, c.mass_flow.decimals) : "—"));
      valor.appendChild(el("span", "card__unidade", c.mass_flow.unit || ""));
      var q = c.mass_flow.quality_pt || "";
      if (c.mass_flow.quality === "STALE" && c.mass_flow.age_s !== null) {
        q += " · " + fmtDuracao(c.mass_flow.age_s) + " atrás";
      }
      valor.appendChild(el("span", "card__qualidade", q));
    } else {
      valor.appendChild(el("span", "card__numero", "—"));
      valor.appendChild(el("span", "card__qualidade", "sem leitura de vazão"));
    }
    li.appendChild(valor);

    if (c.active_anomaly_pt) {
      li.appendChild(el("p", "card__anomalia", c.active_anomaly_pt));
    }

    li.appendChild(el("p", "card__linha", "Conexão: " + (c.connection_pt || "—") +
      " · Última leitura: " + fmtHora(c.last_read_utc)));

    var etiquetas = el("div", "etiquetas");
    etiquetas.appendChild(el("span", "etiqueta", c.application && c.application !== "UNKNOWN" ? c.application : "aplicação desconhecida"));
    etiquetas.appendChild(el("span", "etiqueta", c.data_source === "SIMULATED" ? "simulado" : "equipamento"));
    if (c.is_example) { etiquetas.appendChild(el("span", "etiqueta", "exemplo")); }
    if (c.needs_configuration) { etiquetas.appendChild(el("span", "etiqueta", "não configurado")); }
    li.appendChild(etiquetas);
    return li;
  }

  function renderPlanta(p) {
    var lista = $("cards");
    limpar(lista);
    var cards = p.cards || [];
    if (!cards.length) {
      lista.appendChild(el("li", "card__linha", "Nenhum equipamento configurado em config/equipment."));
    }
    cards.forEach(function (c) { lista.appendChild(renderCard(c)); });
    $("origem-planta").textContent = p.data_source_pt || origemTexto(p.data_source);
  }

  function atualizar() {
    buscar("/system/about")
      .then(function (a) { esconderErro("erro-edge"); renderAbout(a); })
      .catch(function (e) {
        mostrarErro("erro-edge", "Edge sem resposta em /api/v1/system/about (" + e.message + ").");
        var selo = $("selo-origem");
        selo.setAttribute("data-origem", "OFFLINE");
        selo.textContent = "Sem resposta";
      });

    buscar("/plant")
      .then(function (p) { esconderErro("erro-planta"); renderPlanta(p); })
      .catch(function (e) {
        mostrarErro("erro-planta", "Não foi possível carregar a planta (" + e.message + ").");
      });

    $("atualizado").textContent = "atualizado às " + new Date().toLocaleTimeString("pt-BR");
  }

  atualizar();
  window.setInterval(atualizar, INTERVALO_MS);
})();
