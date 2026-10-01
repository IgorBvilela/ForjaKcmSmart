# Auditoria inicial — Forja KCM Intelligence

Data: 2026-09-30 · Pasta: `C:\Users\ivilela\Documents\SIGNA-Q\FKI` · Feita pelo escritório (Pepper + Uatu, Stark, Sexta-feira, Karen, Shuri, Jarvis, Verônica, Edith, verificador, Happy, Ultron).
Nada foi criado ou alterado na pasta do projeto. Este arquivo vive no rascunho da sessão e vai para `docs/auditoria/` depois da aprovação do chefe.
Classificação usada em todo o texto: FACT (verificado nesta máquina) · OFFICIAL_DOC · FIELD_OBSERVED · FORJA_RULE · TECHNICAL_OPINION · HYPOTHESIS · UNKNOWN.

---

## 1. O que já existe

**Na pasta do projeto (FACT):**
- `doc/Forja_KCM_Intelligence_Documento_Mestre_Claude.docx` (2.026.305 bytes, versão 1.0 de 30/09/2026, autor Forja Lógica). 49 seções. Uma imagem embutida: o quadro de identidade visual da Forja Lógica (Grafite #1F1F1F, Chumbo #4B4F56, Cobre #C46A2E, Cinza Técnico #D9D9D9).
- Nada mais. Sem código, sem `.git`, sem README, sem testes, sem `pyproject`, sem `docs/reference/`, sem a versão `.md` do Documento Mestre que a especificação §1 manda ler.

**Fora da pasta (FACT, verificado hoje):**
- O código das Etapas 1–3 existiu nesta máquina em `C:\Users\ivilela\Downloads\forja-kcm-etapa1\forja-kcm`, numa sessão do Claude Code na noite de 21/09/2026 (22:52 às 00:22). A pasta não existe mais. Não está na Lixeira, em outros drives (C, F, G, P) nem em zip em Downloads, Documents, Desktop ou OneDrive.
- Sobrou a transcrição dessa sessão (11 MB) em `C:\Users\ivilela\.claude\projects\c--Users-ivilela-Downloads-forja-kcm-etapa1\`. Ela confirma os três commits do Documento Mestre e os testes: `b77603f` (diagnóstico no formato Resumo→Evidências→Hipóteses, 93 testes), `e6aec44` (contrato JSON versionado com nível de evidência por item, 115 testes), `ddd7a25` (Etapa 3: interface local do Edge, sem build e sem CDN, 135 testes, branch `etapa-3`). A sessão terminou por "session limit".
- A Etapa 1 chegou pronta naquela sessão (o nome da pasta era `forja-kcm-etapa1`, um download). Na sessão foram escritos por completo 23 arquivos (motor de eventos, regras, alarmes, diagnóstico, biblioteca, casos, UI estática em HTML/CSS/JS, 7 arquivos de teste; ~243 KB). Oito arquivos foram só editados e não têm leitura completa na transcrição: README, `cli.py`, `api/main.py`, `drivers/simulator.py`, `config/loader.py`, `acquisition/normalizer.py`, `historian/repository.py`, `tests/test_core.py`. Os arquivos de Etapa 1 nunca tocados (`domain/*`, `drivers/base.py`, `acquisition/scheduler.py`, `app.py`, `config/*.yaml`) não estão na transcrição.
- No Python global desta máquina estão instalados FastAPI 0.141.1, Starlette, pydantic-core e PyInstaller 6.21 (datas 07/2026 e 09/2026): sinal de que o projeto rodou aqui.

**Conclusão:** o código não é recuperável por inteiro. É recuperável o suficiente para preservar decisões e contratos (JSON do diagnóstico v1.0, nomes de tags, qualidades, cenários, nomes de testes, layout da UI).

## 2. Arquitetura atual

Na pasta: não existe. Pela transcrição (estado em 22/09/2026, não verificado em execução):

```
forja-kcm/
├── config/edge.yaml · config/equipment/kcm_gtex_po_base.yaml
├── src/forja/
│   ├── domain/ (models.py, equipment.py)
│   ├── drivers/ (base.py, simulator.py)
│   ├── acquisition/ (normalizer.py, scheduler.py)
│   ├── historian/ (repository.py — SQLite)
│   ├── events/ (engine, rules, models, alarms)
│   ├── diagnostics/ (engine, library, cases)
│   ├── api/ (main.py + static/ — UI sem build, sem CDN)
│   ├── config/loader.py · cli.py · app.py · rag/
├── knowledge/cases/GTEX-PHA-KCM-SPEED-001.yaml
└── tests/ (test_core, test_events, test_diagnostics, test_api, test_end_to_end, test_cli_contract, test_ui)
```

Um Edge, um driver, um equipamento. Contrato oficial `forja diagnose --json` com `diagnosis_schema_version: "1.0"`. Tudo isso é RECUPERADO DA TRANSCRIÇÃO, classificação FIELD_OBSERVED do próprio projeto, não FACT verificado.

## 3. Testes atuais

- Na pasta: nenhum. Nada roda, nada foi instalado, nada foi executado.
- Na transcrição: 135 passed (pytest 9.1.1, venv em Python 3.14) às 00:22 de 22/09, lint limpo. Sete arquivos de teste. Playwright citado para a UI.
- Ferramentas de teste no Python global hoje: nenhuma (pytest, playwright, httpx não instalados — FACT, pip list).

## 4. O que já atende esta especificação

Nada verificável na pasta. O que pode ser **preservado por reconciliação** (extraindo da transcrição para `docs/reference/derived/`): o contrato JSON v1.0 do diagnóstico e sua regra de compatibilidade, a escala de 7 níveis de evidência por item, `evidence_summary` com elo mais fraco, os nomes das tags semânticas, as 6 qualidades, os 9 cenários do simulador WBF, a CLI `forja diagnose --json`, a regra de que a UI consome JSON e nunca reparseia texto, a estrutura das 4 telas e os nomes dos 135 testes.

## 5. O que falta

Matriz do Uatu: 200 requisitos verificáveis. 151 AUSENTE (a especificação pede e nada foi lido), 35 NÃO_LOCALIZADO (o DM §5 diz que existe), 14 BLOQUEADO_POR_CAMPO. 18 dependem de dado da GTEX.

| Tema | Itens | Bloqueados por campo |
|---|---|---|
| Diagnóstico | 16 | 0 |
| UI shell | 14 | 0 |
| Comunicação / wizard | 13 | 1 |
| Processo (auditoria, fases, relatório por fase) | 12 | 0 |
| Alarmes / status (MDU, SFT, STOP BY) | 10 | 3 |
| Documentos / RAG | 10 | 0 |
| Drivers | 9 | 2 |
| Mapping | 8 | 1 |
| Campo / descoberta | 7 | 4 |
| Read-only, produto, multi-equipment, historian, eventos, simulador, conhecimento/evidência | 6–7 cada | 1 (multi) |
| Tags/qualidade, simulador visual, early warning, health/logs/backup | 5 cada | 1 (EW) |
| Arquitetura, tendências/timeline, offline/Windows, resiliência, relatórios, segurança OT | 4 cada | 1 (arq.) |
| Visão da planta, dashboard, testes | 3 cada | 0 |
| Usuários/auditoria, aceite | 2 cada | 0 |

**Conflitos DM × especificação (20, todos resolvidos):** a especificação (mais recente e mais específica) vence em 18; em 2 vale a união das listas. Os principais: sidebar (spec §46, sem item "Equipamentos"), wizard com 6 passos e Simulator como opção (spec §16), 8 estados do teste de conexão, dois vocabulários distintos (conhecimento spec §7 com 9 estados; evidência no diagnóstico spec §29 com 7 níveis; DECISÃO→FORJA_RULE, INFERENCE→HYPOTHESIS), 22 tags (spec §21), fases A–O da spec + P do DM, hierarquia de 9 fontes (spec §8), amostra com 6 campos (spec §23; plant/area/line vêm do perfil), STOP BY com UNKNOWN (spec §36; Calib/Tare ficam UNKNOWN "candidato a PROCEDURE", decisão do chefe), chave de alarme com manufacturer (spec §34), frase central "ajuda a manutenção" (spec §2), FIELD_REQUIRED = estado da funcionalidade, UNKNOWN = valor do dado.

**Fontes locais citadas no DM §42/§43: nenhuma está no repositório** (Análise A–T.pdf, KCM-SMART-MANUAL.html, Manual_Diagnostico_Encoder_Dosador_PHA_GTEX.pdf, Manual_Ligacoes_KCM_GTEX_Forja_Logica.pdf/.md, relatórios GTEX, guias LWF/WBF, fotos, diagramas, manuais Coperion 1090020601-EN Rev 1.2.1 e 0590020601-EN Rev 1.8.0, doc SFT). Sem eles, `knowledge/` nasce vazio e toda fonte do diagnóstico fica HYPOTHESIS ou FIELD_OBSERVED.

## 6. Pontos que considero perigosos

1. **Perda de código já aconteceu uma vez.** O trabalho de 21/09 sumiu com a pasta de Downloads. Sem git local e sem backup fora do disco, pode acontecer de novo. (FACT)
2. **Planejar "preservar" o que não existe.** O DM §5 é estado reportado. Qualquer frase "as Etapas 1–3 estão preservadas" fica barrada até o código aparecer (Verônica).
3. **Sessão do Anybus.** Limite de conexões do módulo real é UNKNOWN (a HMS não publica; o apêndice SCM-1200-075 deu erro 500). O guia Modbus/TCP oficial descreve servidores que fecham a conexão mais antiga quando o pool estoura; uma conexão CIP Exclusive Owner possui as saídas. Conectar sem levantar topologia e sem autorização pode derrubar o supervisório. (OFFICIAL_DOC + UNKNOWN)
4. **Mapa "built-in" do kgr WBF encontrado na pesquisa** (40001 Maximum Flow, 40003 Setpoint, 40007 Massflow, 40009 DriveCommand...). É documento Coperion de 2014 e NÃO confirma a GTEX. Se virar mapping oferecido pelo wizard, vira adivinhação. Entra só como documentação com `confirmed: false`, nunca como template padrão. (OFFICIAL_DOC, aplicabilidade UNKNOWN)
5. **Valores de campo virando regra:** 4,9 V, 0,125 mm, 120/400 PPR, 56 = BELTLOAD LOW, MDU 0046/2006/2046, SFT 00000183/00000181, "Ver 2.5", setpoint 1300 kg/h e 2,0 kg/m. Todos ficam FIELD_OBSERVED ou SIMULATED, nunca threshold, default ou catálogo universal. Origem exata de 4,9 V, 0,125 mm e dos status SFT: perguntar ao chefe (tela ou documento?).
6. **Equipamentos fictícios na demo.** Barrilha, KCM 03 e KCM 04 são exemplos da spec §47; só Pó Base é FIELD_OBSERVED. Entram como perfis rotulados "simulado/exemplo", separados da semente de produção.
7. **Python 3.14.5 e wheels.** A máquina não tem compilador C. greenlet (dependência do Playwright Python), argon2-cffi e tracer C do coverage podem faltar. O gate A0 resolve com prova, não com opinião. (FACT + HYPOTHESIS)
8. **pycomm3** diz "no longer actively developed" e declara só até Python 3.10 (importa em 3.14.5). Só entra vendorizada com hash e testes próprios, ou outra biblioteca. (OFFICIAL_DOC)
9. **Promessa de predição e "causa: encoder queimado".** O contrato v1.0 não tem campo "causa"; `caveats` é obrigatório; Early Warning fala "comportamento diferente do histórico". (FORJA_RULE)
10. **Tentação de usar PLC/SCADA ou MySQL local.** Nenhuma mesa abriu essa porta; fica registrado como regra (FORJA_RULE) e como motivo forte documentado para SQLite (serviço offline único, arquivo único, backup por API, um escritor).
11. **Licenças com impacto comercial:** Inno Setup 7 pede licença comercial; cpppo é dual GPLv3/proprietária (fora, inclusive como fake de teste); Nuitka é AGPL com exceção. PyInstaller tem exceção que libera o binário. (OFFICIAL_DOC)
12. **Tela falsa.** Toda rota sem backend mostra "Não configurado" ou "Disponível após configuração de campo"; teste rastreia botão sem ação.

## 7. O que depende da GTEX (UNKNOWN / FIELD_REQUIRED)

| Item | Como obter em campo (sem alterar nada) |
|---|---|
| Protocolo real do Host/Anybus | Menu `SYSTEM → SW VERSIONS` (ou equivalente real), opção Host Board: campo HW# mostra Profibus, DeviceNet, ModbusPlus, EthIP/ModTCP, ProfinetIO ou Comm Board (OFFICIAL_DOC manual LWF 2.8; menu a confirmar no KCM). Fotografar. |
| Versão real do software do KCM | Mesmo menu, opção KCM CPU: SW#. "Ver 2.5" da etiqueta não vale. |
| HOST PROT, HOST FILE (Kgr File / Small / Full), IP, NM, GW | Communication sub-menu do KCM; fotografar. Com kgr custom, IP é read-only e vem do arquivo. |
| Part number e revisão do Anybus-S em J3 HOST | Etiqueta do módulo (AB4173-x = só EtherNet/IP; AB4582-x = EtherNet/IP + Modbus TCP). Define se existe servidor Modbus TCP em paralelo. |
| KGR carregado, Host File real, mapa de registers/assemblies, datatype, byte order, word order, scale | Arquivo kgr (export do SmartConfig) ou documentação da máquina. Validar cada tag contra a tela do KCM (passo 6 do wizard). Até lá `UNCERTAIN`. |
| Destino do cabo verde, switch, SPAN, peer | Seguir o cabo sem desconectar; fotografar as duas pontas. |
| Conexão existente do peer (I/O Exclusive Owner? MSG explícita? quantas conexões Modbus?) | Inspeção só leitura com o responsável da planta. |
| Limite de sessões do módulo | UNKNOWN em fonte pública; só teste autorizado com o supervisório observado. |
| Contadores Host Read/s, Host Write/s, Host Err | Anotar antes e depois de qualquer conexão da Forja (prova de que Host Write não mudou). |
| Lista e semântica dos alarmes da aplicação WBF na versão real | Fotos da tela e do histórico de alarmes + manual WBF da versão. |
| PICK UP TEETH real | Parâmetro no KCM + etiqueta do encoder/sensor. |
| Modelos e quantidade de SFT, MDU, SIB | Etiquetas. |
| Decodificação de MDU 0046/2006/2046 e SFT 00000183/00000181 | Só com documento do fabricante do modelo e revisão exatos. |
| Produto, modo de operação e faixa de setpoint (para baseline) | Anotar com a operação. |
| Lista real de dosadores/KCMs da planta | Confirmar com a planta. |
| PC da planta: Windows, admin, antivírus, disco, IP fixo, firewall | Levantar antes da fase N. |

Perguntas de proveniência ao chefe (não travam): origem de 4,9 V e 0,125 mm; origem dos status SFT 00000183/00000181; documento/revisão/página dos 13 alarmes de referência (06–47) e dos termos STOP BY.

## 8. Pesquisa externa

**Feita nesta rodada** (Sexta-feira, 51 fontes registradas com fabricante, documento, URL, revisão e data; verificador conferiu 51 grupos de afirmações em fonte primária: 47 confirmadas, 3 refutadas, 1 não verificável):
- Bibliotecas comparadas: Modbus (pymodbus 3.15 BSD-3 com CI em 3.14 e Windows; pyModbusTCP; uModbus, modbus-tk, async-modbus descartados), EtherNet/IP (pycomm3 1.2.16 MIT; python-ethernetip 1.2.0 MIT; cpppo dual-GPL fora; pylogix só Logix; EEIP.py sem PyPI; aphyt só Omron), FastAPI 0.142 + uvicorn 0.54 + pydantic 2.13, pywin32 312 (wheel cp314), NSSM (sem release desde 2014), WinSW (2.12.0 é de 2023-01, não 2025 — refutado), PyInstaller 6.22 (3.8–3.15), Nuitka (AGPL), PyOxidizer (morto), pyapp (baixa Python em runtime), Briefcase, Inno Setup 7.1 (licença comercial), NSIS 3.13, WiX 7, sqlite3 stdlib (SQLite 3.50.4 com FTS5 nesta máquina — FACT), APSW, SQLAlchemy, alembic, pytest 9, pytest-asyncio, playwright 1.63, hypothesis, ruff, mypy 2.3 (wheel cp314), pyright, PyYAML, ruamel.yaml, jsonschema.
- Fatos públicos úteis (OFFICIAL_DOC, nenhum confirma a GTEX): manual Coperion KCM LWF Programming 0590020601-EN Rev 1.8.0 lista os protocolos Host selecionáveis (Modbus, AB-CIF, Siemens 3964R, ProfibusDP, Modbus/TCP, DeviceNet, Ethernet/IP, ModbusPlus, Profinet IO) e o menu SW VERSIONS; RDTB-0027 Rev E (2015) descreve Input Assembly 100 / Output Assembly 150 e byte/word order como configuração do kgr; folha Smart K-Link I-070302-en (2014) com mapa built-in por aplicação; HMS Anybus-S está em fase "Mature" (sem desenvolvimento); ODVA define Exclusive Owner, Input Only, Listen Only e recomenda que adapters aceitem controlador + dispositivo de monitoração; Modbus V1.1b3 define FC de leitura (01–04, 43/14) e de escrita (05, 06, 15, 16, 22, 23); Microsoft `sc.exe config start= delayed-auto` e `sc.exe failure`.
- Dado refutado que muda o desenho: pymodbus 3.15 só fecha a conexão após `retries + 3` tentativas (até ~70 s). Decisão: `retries=0`, `reconnect_delay=0`, backoff só no supervisor da Forja.

**Ainda necessária:** apêndice HMS SCM-1200-075 (limite de conexões do Anybus-S); manuais Coperion 0590020612-EN (Protocol), 0590020611-EN (Smart K-Link Design), 0590020610-EN (Ethernet Adapter) e o manual de programação WBF da versão instalada; CIP Vol. 1 da ODVA (só membros); escolha final da biblioteca EtherNet/IP na fase I com a régua fixada; suporte do Biome a `.svelte` e comportamento do uPlot sob CSP sem `unsafe-inline` (gates das fases B e E).

## 9. Arquitetura proposta

Um processo Windows (`ForjaKCM.exe`, serviço via pywin32) contém tudo: supervisor de aquisição com uma task asyncio por equipamento, normalização por mapping externo, historian SQLite, motor de regras determinístico, motor de diagnóstico que emite o JSON v1.0, biblioteca de conhecimento local (FTS5), API FastAPI (REST + SSE) e UI estática servida em `127.0.0.1:8765`. Camadas com portas: `domain` no centro, `drivers` como única camada que fala protocolo, `acquisition` orquestrando, `api/ui` na borda. Nada da GTEX no código.

**Read-only por construção em 8 camadas:** (1) porta `ReadOnlyDriver` só com connect/disconnect/read/health/capabilities, com `__init_subclass__` recusando `write*`; (2) wrapper por composição que expõe só leitura, sem `__getattr__`; (3) fronteira de import (pymodbus/EIP só em `drivers/<protocolo>/_client.py`); (4) guard fail-closed no fio (Modbus `trace_pdu` só FC 01–04; CIP só 0x01/0x03/0x0E, cobrindo Multiple_Service_Packet e Unconnected_Send); (5) varredura AST de nomes proibidos; (6) OpenAPI sem rota de comando (snapshot versionado); (7) UI sem controle de comando fora do simulador; (8) perfis sem permissão de escrita no KCM e IA sem ferramenta com efeito. Testes T01–T32 da Verônica provam cada camada e plantam violações para provar que o teste morde.

**Decisões fechadas (as 23 contradições das mesas, resolvidas pelo Happy; todas TECHNICAL_OPINION, "sugiro fortemente", pendentes de aprovação):**

| Tema | Decisão | Alternativa / o que mudaria |
|---|---|---|
| Python | 3.14 (o da máquina), `>=3.13,<3.15`; gate A0 prova instalação completa + build PyInstaller | cai para 3.13 via uv se faltar wheel |
| Lock | uv (`uv lock` + export com hashes) | pip-tools se vetar uv |
| Web | FastAPI + uvicorn embutido, 1 processo, bind 127.0.0.1:8765 | — |
| Banco | SQLite WAL em 2 arquivos: `forja_core.db` + `forja_historian.db`; STRICT; `samples` WITHOUT ROWID (27,8 B/linha medido) | PostgreSQL/Timescale atrás da porta `HistorianRepository` |
| Acesso a dados | SQL à mão atrás de repositórios + runner próprio de migrações (`schema_migrations`) | SQLAlchemy Core só se o código antigo já usar |
| Configuração | banco é a fonte da verdade em runtime; YAML/JSON = semente, import/export e backup legível | — |
| STALE | estado derivado (idade por relógio monotônico), nunca linha gravada; historian grava COMM_ERROR por tentativa | — |
| Modbus | pymodbus 3.15 embrulhado; `retries=0`, `reconnect_delay=0`; backoff só no supervisor | pyModbusTCP |
| EtherNet/IP | decide na fase I com régua: MIT/BSD/Apache sem dual, wheel/sdist puro, Get_Attribute_Single contra fake próprio, superfície de escrita enumerada; só explícita na v1; pycomm3 só vendorizada | implícita Input Only só em P com documento do módulo |
| Serviço Windows | pywin32 ServiceFramework + `sc.exe` (delayed-auto, failure actions); spike cedo na fase L | WinSW 2.12 com hash se falhar 2× |
| Empacotamento | PyInstaller onedir; instalador Inno Setup (licença comercial) ou NSIS (grátis): decisão do chefe na fase N | — |
| Front | Vite + Svelte 5 + TypeScript, SPA estática em `/app/*`, servida pelo FastAPI, zero CDN, tipos gerados do OpenAPI | Vue 3 se o chefe preferir; HTML sem build se vetar Node |
| Gráficos | uPlot (MIT, ~45 KB) para gráficos com eixo; SVG próprio para sparkline, timeline e dosador | — |
| Tempo real | SSE: 1 stream por aba com todos os equipamentos, heartbeat 5 s, Last-Event-ID, `/snapshot` antes | polling como reserva |
| Rótulos pt-BR | vêm do backend no JSON (`knowledge/i18n/pt_BR.yaml`); front só fallback | — |
| Tokens | `forja-tokens.css` da Shuri é a única fonte; breakpoints 768/1024/1440; sidebar recolhida em 1366 | — |
| Seletor de equipamento | `<select>` nativo estilizado | listbox custom se o chefe pedir |
| Alerta de processo | nunca toast; toast só para evento de sistema | — |
| Senha | `hashlib.scrypt` da stdlib (N=2^17, r=8, p=1) com `needs_rehash` | Argon2id se wheel cp314 instalar no gate |
| Sessão | no servidor (tabela), token opaco como hash; cookie `forja_session` em loopback; `__Host-` + Secure só com TLS | — |
| Audit log | tabela no core, append-only por trigger, cadeia de hash, `forja audit verify`, export JSONL | — |
| Logs | comm e audit em tabela; app e event em arquivo rotativo; 4 exportáveis pela API | — |
| Testes UI | Playwright em Python (pytest-playwright), um runner só | Node só se o gate A0 falhar, migrando tudo |
| Tipos / lint | mypy strict + plugin Pydantic; ruff; front Biome + svelte-check | eslint-plugin-svelte se Biome não cobrir |
| Hooks | `tools/check.py` + `check.cmd` + hook git nativo (zero rede) | — |
| CSP | `default-src 'self'` sem `unsafe-inline`; Svelte sem `style=` literal | nonce por resposta, nunca unsafe-inline |
| Early Warning | fase F com regras sem baseline + estado honesto; baseline estatístico em P | — |
| STOP BY | enum da spec §36; Calib/Tare como UNKNOWN "candidato a PROCEDURE" (pergunta ao chefe) | — |
| .md derivado | `docs/derived/Documento_Mestre_DERIVADO_do_DOCX_2026-09-30.md`, nunca com o nome do canônico | — |

**Modelo de dados (Karen, medido nesta máquina):** 20 tags × 1 Hz × 1 KCM = 1,73 M linhas/dia = 48 MB/dia; retenção padrão bruto [30 d], agregado 1 min [180 d], 1 h sem limite → ~2,2 GB por KCM em regime; com [4 KCMs] ~8,9 GB. Backup consistente com o serviço rodando (`VACUUM INTO` 0,4 s por 48 MB; API de backup paginada). Janela do evento copiada fisicamente para o core (sobrevive ao purge). `UNKNOWN` literal nas chaves compostas de alarme e STOP BY. `status_decoders` nasce vazia e só aceita MANUFACTURER_DOC/MACHINE_DOC. Dados SIMULATED nunca entram em baseline nem casos.

**Design (Shuri):** painel de instrumentos, não site. Grafite em camadas, borda 1 px no lugar de sombra, cobre só onde a Forja aponta ou age (nunca status). Estado por verde/âmbar/vermelho/ciano; qualidade por FORMA + cor (● hachura tracejado desbotado ○ ✕); lilás reservado a SIMULADO. IBM Plex Sans + IBM Plex Mono (OFL 1.1) vendorizadas em woff2 com subset. Contraste AA calculado em todos os pares. Nada pisca. Dosador em corte lateral 2D, linha + preenchimento plano; em ENCODER_FAILURE a correia fica tracejada ("movimento inferido do comando") porque a Forja não mede movimento.

## 10. Plano em fases (com ordem de grandeza)

Unidade: "sessão" = um bloco de trabalho com o Claude Code (a sessão de 21/09 durou 1h30 e caiu por limite). Estimativas são TECHNICAL_OPINION e vão entre colchetes.

| Fase | Conteúdo | Depende de campo | Estimativa |
|---|---|---|---|
| **A0** (agora, neutro) | 3 perguntas ao chefe; gate de ambiente (venv 3.14.5, instalação pinada completa, smoke, build PyInstaller) gravado em `docs/gates/A0_python.md`; pyproject + lock com hashes; ruff, mypy, import-linter; `tools/check.py` + hook; contratos congelados em `docs/contracts/`; ADRs 0001–0012 com as 23 decisões; `docs/research/drivers.md`; kit de campo v0; extração dos 23 arquivos recuperáveis da transcrição para `docs/reference/derived/`; `git init`, branch `fase-a0`, commit | não | [1 sessão] |
| **A1** nascer limpo (ou **A1'** reconciliar, se o código aparecer) | domínio e portas; SimulatorDriver com 9 cenários, relógio injetável e `advance(s)`; normalização; SqliteHistorian (2 arquivos, migração 0001); EquipmentManager multi desde o dia 1 com backoff, watchdog e COMM_ERROR ≠ STALE; RuleEngine (R-BELTLOAD-001, R-SPEED-001, R-COMM-001); DiagnosisEngine v1.0; API mínima + SSE + snapshot; CLI `run / diagnose --json / doctor`; suíte de contrato (≥ 90 testes) | não | [3–4 sessões] |
| **Trilho FRONT** B → C → D → E-UI → F | B: tokens, shell, sidebar, `<select>`, faixa de fonte de dados, selo SOMENTE LEITURA, tema claro por tokens, Playwright base 4 viewports · C: planta + dashboard · D: dosador animado + sliders + DADOS SIMULADOS · E-UI: tendências uPlot com GAP/STALE, timeline, histórico · F: diagnóstico 7 seções, impressão, Early Warning fase 1. Fecha com **Aceite DEMO 18/18** | não | [B 2 · C 2 · D 2 · E-UI 2 · F 2–3 = 10–11 sessões] |
| **Trilho IO** E-core → I → spike → J → K (em paralelo ao FRONT) | E-core: rollups 1 min/1 h, retenção, downsampling, store-on-change · I: codec + ReadPlanCompiler + hypothesis + fake Modbus + fake EIP + `drivers.md` fechado · spike: serviço congelado (pywin32 + PyInstaller + SvcStop) · J: Modbus TCP EXPERIMENTAL · K: EtherNet/IP EXPERIMENTAL, só explícita | não | [E-core 1 · I 2 · spike 1 · J 2 · K 2–3 = 8–9 sessões] |
| **G** Communication Center | wizard 6 passos com gate de autorização no passo 4; editor de mapping com versão imutável, 409 em versão divergente e auditoria na mesma transação; qualidade; log técnico; checklist de descoberta como dado. Aceite CAMPO 1–2 e 4–11 com simulador | não | [3–4 sessões] |
| **H** Multi-equipment na UI | adicionar/remover/arquivar, reload a quente, teste chaos. **Aceite CAMPO 12/12** com fake Modbus | não | [1–2 sessões] |
| **L ‖ M** | L: saúde, logs, auditoria, graceful shutdown · M: relatórios HTML de impressão, backup/restore, usuários, telas de CONHECIMENTO (upload, metadados, FTS5) | não | [L 2 · M 2–3 sessões] |
| **N** Empacotamento | PyInstaller onedir, serviço pywin32 + sc.exe, instalador (Inno ou NSIS), ACL de `%ProgramData%\ForjaKCM`, antivírus, firewall; teste em VM limpa (chefe providencia) | não | [2–3 sessões + VM] |
| **O** Campo GTEX | kit impresso, autorização escrita no app, topologia antes de conectar, explícita antes de implícita, contadores Host antes/depois, validação tag a tag | **sim** | [1–2 dias em campo] |
| **P** Pós-campo | mapping real como fixture de replay, catálogo de alarmes por versão real, `forja catalog merge-version`, baseline estatístico, RAG LOCAL só se o chefe quiser | sim | contínuo |

**Total até a fábrica (A0–N): [32–40 sessões]. Com 1 a 2 sessões por dia útil: [4 a 8 semanas].** Linha de corte do DEMO (§89): fim de F. Linha de corte do CAMPO (§90): fim de H com J pronto.

**Dinheiro:** tudo open-source e gratuito, exceto: licença comercial do Inno Setup [valor a confirmar no site; alternativa NSIS grátis], certificado de assinatura de código [opcional, a confirmar], um PC ou VM limpa para testar o instalador [o chefe providencia]. O custo recorrente real é o uso do Claude Code em sessões.

## 11. Arquivos que pretendo alterar

Nenhum existe para alterar. O DOCX em `doc/` não será movido nem editado. Se o código das Etapas 1–3 aparecer (A1'): rodar os 135 testes no ambiente dele antes de tocar; depois `pyproject.toml`, `README.md`, `src/forja/**` (mover por `git mv` para a estrutura abaixo com tabela módulo antigo → módulo novo), `tests/**` (marcadores e pastas), `config/*.yaml` (semente). Conflitos registrados, nunca corrigidos em silêncio. Regra de versão única: o 1.0 dele vence; o nosso vira 1.1 com adaptador.

## 12. Arquivos novos (resumo da árvore do Stark)

```
FKI/
├── README.md · CLAUDE.md · pyproject.toml · uv.lock · .python-version · .importlinter · .githooks/pre-commit · check.cmd
├── doc/  (JÁ EXISTE: Documento Mestre .docx; não mover)
├── docs/ adr/ · contracts/ (diagnosis-v1.0.schema.json, mapping.schema.json, equipment-profile.schema.json, rule.schema.json, openapi.snapshot.json)
│       · field/ (checklist, FIELD_REQUIRED.md) · reference/ (originals/ gtex/ manuals/ photos/ derived/ + INDEX.md) · research/ · gates/ · derived/ · UNKNOWN.md
├── config/ forja.yaml · equipment/ (gtex_pha_po_base.yaml, _template.yaml, exemplos simulados separados) · mappings/ (simulator_wbf.yaml, gtex_pha_po_base.yaml tudo UNKNOWN, _template_modbus_tcp.yaml, _template_ethernet_ip.yaml)
│          · rules/ (R-BELTLOAD-001, R-SPEED-001, R-DRIVE-001, R-COMM-001, R-STALE-001) · alarms/ (coperion_ktron__kcm__wbf__UNKNOWN.yaml) · stop_by/ · schema/
├── knowledge/ diagnostics/ · cases/ (2026-09_gtex_pha_po_base_velocidade.yaml, causa UNKNOWN) · documents/ · i18n/pt_BR.yaml
├── src/forja/ domain/ · config/ · infra/ · drivers/ (base, registry, support, codec; simulator/, modbus_tcp/{driver,_client}, ethernet_ip/{driver,_client})
│            · normalization/ · acquisition/ · historian/ (sqlite, writer, queries, rollups, retention, backup, migrations/) · events/ · diagnostics/
│            · knowledge/ (rag/provider, none, local, cloud só interface) · security/ · reports/ · backup/ · api/ (app, routers/*) · service/ · tools/ (cli) · ui/dist (build, gitignored)
├── frontend/ (Vite + Svelte 5 + TS: src/{styles/tokens.css, lib/{api,live,state,router,format,charts,i18n,a11y,testids.ts}, components/{shell,ui,data,wbf}}, public/{fonts,icons,brand}, licenses/)
├── tests/ unit/ · integration/ · contract/ (readonly AST, import fence, schema v1.0, openapi, registry) · e2e/ (pytest-playwright) · fixtures/ (fake_modbus_server, fake_eip_responder, series)
├── scripts/ dev.ps1 · build_ui.ps1 · build_exe.ps1 · build_installer.ps1 · forja.spec · installer.iss · field_kit/
└── var/ (dev, gitignored) — produção: %ProgramData%\ForjaKCM\{config,knowledge,data,logs,backups}
```

Árvore completa, contratos (assinaturas de `ReadOnlyDriver`, `DriverRegistry`, `EquipmentManager`, `HistorianRepository`, `RuleEngine`, `DiagnosisEngine` v1.0, `MappingSchema`, `EquipmentProfile`, rotas `/api/v1`, `forja.yaml`) e modelo de 30 tabelas estão nos digests das mesas (`scratchpad/mesas/*.json`).

## 13. Ordem de implementação

1. **A0 agora**, sem esperar resposta: perguntas, gate de ambiente, tooling, contratos congelados, ADRs, pesquisa registrada, kit de campo v0, recuperação da transcrição para `docs/reference/derived/`, `git init` local.
2. **A1 ou A1'** após a resposta sobre o código (prazo sugerido: [5 dias úteis]; sem resposta, nasce limpo). A mecânica de L (backoff, watchdog, COMM_ERROR ≠ STALE) nasce aqui porque C e D precisam dela.
3. **Dois trilhos em paralelo** em branches locais (`front` e `io`) com o OpenAPI congelado: FRONT B→C→D→E-UI→F; IO E-core→I→spike do serviço→J→K. I e J correm antes de G fechar para o wizard testar leitura contra fake real.
4. **G** junta os trilhos. **H** fecha o Aceite CAMPO com fake Modbus.
5. **L ‖ M**, depois **N**, depois **O** (campo) e **P**.
6. Transversal: `check full` verde, relatório da fase no formato da spec §85, `docs/UNKNOWN.md` e `field_required.yaml` atualizados, commit local por fase. Nenhuma fase avança com teste vermelho, botão falso ou valor da GTEX hardcoded.

## 14. Critério de pronto de cada fase

**Gate padrão (toda fase):** `python tools/check.py --full` retorna 0 (ruff + mypy + pytest + tests/readonly + Playwright nos viewports da fase + cobertura ≥ 95 % em drivers/domain/acquisition e ≥ 80 % no resto); nenhum skip/xfail novo sem registro; crawler "sem tela falsa" verde; nenhum request externo (pytest-socket + interceptação Playwright); `docs/UNKNOWN.md` atualizado; relatório da fase (spec §85); commit local.

| Fase | Pronto quando |
|---|---|
| A0 | gate de ambiente gravado com resultado; `check quick` verde num pacote vazio; hook instalado; git local iniciado; contratos e ADRs commitados |
| A1 | ≥ 90 testes; `forja run` sobe 3 simuladores em 127.0.0.1:8765; `forja diagnose --json` valida contra `diagnosis-v1.0.schema.json` e é igual ao da API; um simulador em COMMUNICATION_FAILURE não altera samples/min dos outros; AST anti-write, fence de import e OpenAPI sem escrita verdes |
| B | `npm run build` sem nenhuma URL externa; Playwright em 1920/1366/768/375 sem overflow horizontal; sidebar, seletor e selo SOMENTE LEITURA testados; tokens da marca verificados por computed style; reduced-motion respeitado |
| C | planta com Normal / Atenção / Sem comunicação corretos com 3 simuladores; card abre o dashboard certo; STALE renderizado como antigo com idade; número não anima com reduced-motion |
| D | 4 estados visuais testáveis por `data-*` (NORMAL, BELTLOAD_LOW, ENCODER_FAILURE, COMMUNICATION_FAILURE); sliders; ≤ 4 ms por quadro em 1366×768; Aceite DEMO 1–9 |
| E | série com buraco retorna null e o gráfico não liga; 30 dias ≤ 2000 pontos em < 300 ms com 5 M amostras sintéticas; retenção apaga bruto e preserva agregados; GAP e STALE preservados nos agregados (hypothesis) |
| F | Aceite DEMO 18/18 em < 60 s; nenhum título com código interno; nenhuma hipótese afirma causa; `evidence_summary.weakest_level` nunca mais forte que o item mais fraco; impressão do diagnóstico |
| G | equipamento criado pelo wizard com driver simulator aparece no seletor sem reiniciar; mapping inválido rejeitado com 422; toda gravação gera auditoria na mesma transação; 409 em versão divergente; fake Modbus só recebe FC 03/04; drivers reais nunca AVAILABLE |
| H | teste chaos: driver que explode por 10 min não altera samples/min dos demais; Aceite CAMPO 12/12 com fake Modbus |
| I | `decode(encode(x))` para todos os datatypes × 4 ordens (hypothesis); nenhum endereço literal em `drivers/`; pesquisa registrada por afirmação |
| J / K | leitura correta nas 4 ordens contra fake; timeout vira COMM_ERROR em ≤ timeout × (retries+1); nunca 2 sockets abertos; fake nunca recebe função/serviço de escrita; estado EXPERIMENTAL afirmado por teste |
| L | task travada reinicia em ≤ 3× poll_interval; Ctrl+C não perde lote; `/health` < 50 ms; 4 logs exportáveis; spike do serviço congelado para e sobe limpo |
| M | backup → apagar `var/` → restaurar → mesmas contagens; VIEWER recebe 403 em toda escrita de configuração; nenhuma rota de comando para nenhum papel; relatórios com marca d'água DADOS SIMULADOS quando a fonte é simulador |
| N | em VM limpa: instalar → reiniciar → serviço UP sem login → coleta com navegador fechado; parada pelo services.msc gera shutdown gracioso; instalador roda sem rede; checklist manual de 8 itens assinado pelo chefe |
| O | tabela de validação preenchida tag a tag com hora e foto; historian real ≥ 24 h sem intervenção; nenhum campo do perfil preenchido sem evidência anexada; Host Write igual antes e depois |
| P | cada alarme/status com fonte rastreável ou FIELD_OBSERVED; baseline só compara mesmo produto/modo/faixa; IA (se houver) nunca chama rota de configuração |

---

## Perguntas ao chefe (travam A1, não A0)

1. **Código:** a pasta `Downloads\forja-kcm-etapa1` sumiu. Existe outra cópia (o zip da Etapa 1, outro PC, e-mail, projeto no claude.ai)? Se não, autoriza nascer limpo (A1) preservando o contrato v1.0 recuperado da transcrição? Prazo sugerido: [5 dias úteis].
2. **Documentos:** onde estão o `.md` original do Documento Mestre e os arquivos do DM §42/§43 (PDFs, Smart Manual, fotos, manuais Coperion)? Sem eles `knowledge/` nasce vazio.
3. **Front:** pode entrar Node/npm no projeto (Vite + Svelte 5, build estático, zero CDN)? Você já programa em Vue ou React e prefere seguir o que conhece?

Perguntas de segunda rodada (não travam): origem de 4,9 V e 0,125 mm; origem dos status SFT 00000183/00000181; documento dos alarmes 06–47 e dos termos STOP BY; Calib/Tare como categoria PROCEDURE de STOP BY; Inno Setup (pago) ou NSIS (grátis).

## Sugestões extras (opcionais, com motivo)

- **Backup automático da pasta do projeto para outro disco ou pendrive**, por script local diário. O sumiço de Downloads justifica.
- **`forja config export` versionado no git local** a cada mudança de mapping: a configuração vira histórico legível.
- **Kit de campo imprimível dentro do app** (checklist da spec §18 com espaço para foto e valor) já na fase G, não só em `docs/`.
- **`forja doctor`** na CLI: versão, Python, bibliotecas, portas, disco, relógio. Diagnóstico da instalação em 10 segundos, em campo.
- **Glossário KCM em português** (K-Port, Host, KGR, SFT, MDU, SIB, Feed Factor...) na tela Sobre/Conhecimento.

## Inspeção (formato /inspetor)

**O que entendi.** Sistema: observador read-only de controladores Coperion K-Tron KCM que historiza, detecta o que mudou e ajuda a manutenção a diagnosticar; não comanda nada. Stack prevista: Python/FastAPI (API local), SQLite (banco em arquivo, sem servidor), UI servida em localhost, serviço Windows. Tamanho: 1 arquivo (DOCX), 0 linhas de código, 0 commits (sem git). Estado: nada roda; nada para buildar; 0 testes.

| Área | Nota | Evidência |
|---|---|---|
| Design/UX | n/a | sem UI na pasta |
| Front-end | n/a | idem |
| Responsivo mobile | n/a | idem |
| Animações/interação | n/a | idem |
| Back-end | n/a | sem código |
| API | n/a | sem código |
| Banco de dados | n/a | sem código |
| Segurança | n/a | sem código (regras do DM §1.3/§35 são boas, mas não há o que auditar) |
| Testes | 0 | nada para rodar; 135 testes só na transcrição de 21/09 |
| Performance | n/a | sem código |
| Documentação | 7 | Documento Mestre completo e bem classificado (49 seções, evidência marcada); perde por afirmar código que não está aqui e por citar 16 fontes ausentes |
| Organização do git | n/a | sem repositório |

**Nota geral: 2/10.** Como software, a pasta não tem nada que rode. Como pacote de contexto, o Documento Mestre vale 7.

**Top 5 problemas.** (1) Código das Etapas 1–3 ausente; existiu em Downloads em 21/09 e sumiu; só a transcrição sobrou. (2) O `.md` canônico e os 16 documentos de referência não estão no repositório. (3) Sem git e sem backup, a perda pode repetir. (4) 20 conflitos entre DM e especificação exigiam decisão antes de codar (resolvidos: spec vence em 18). (5) 20 valores de campo com risco de virar fato ou default.

**O que eu faria primeiro.** (1) Sugiro fortemente: responder as 3 perguntas hoje. (2) Sugiro fortemente: aprovar A0 (git local, gate de ambiente, contratos, ADRs, recuperação da transcrição) porque não depende de nenhuma resposta. (3) Sugiro fortemente: copiar os documentos do §42/§43 para `docs/reference/`. (4) Decidir A1 × A1' em [5 dias úteis]. (5) Instalador (Inno × NSIS) só na fase N.

**Kit de skills para continuar** (gravo no CLAUDE.md do projeto se você aprovar):

| Área | Skill | Por quê |
|---|---|---|
| Fluxo | agent-skills:incremental-implementation + agent-skills:test-driven-development | fases pequenas, teste antes do código, read-only provado |
| Design | design-taste-frontend + dataviz | anti-template; gráficos honestos (GAP, STALE) |
| UI/UX | agent-skills:frontend-ui-engineering | acessível, responsivo, sem tela falsa |
| Front | agent-skills:frontend-ui-engineering | Svelte, tokens, Playwright |
| Animações | genjutsu:cast | só depois do shell parado funcionar |
| API | agent-skills:api-and-interface-design | contratos v1.0 estáveis, OpenAPI snapshot |
| Back | agent-skills:source-driven-development | decisão com documentação oficial das bibliotecas |
| Segurança | agent-skills:security-and-hardening | read-only por construção, OT |
| Auditoria | agent-skills:code-review-and-quality + agent-skills:documentation-and-adrs | ADRs das 23 decisões, revisão por fase |
