# Contratos da Fase B/C/D — interface do Forja KCM Intelligence

Quem implementa um bloco lê isto inteiro, lê `docs/reference/design/README.md` (o que da referência visual entra e o que não entra),
`frontend/src/styles/tokens.css` (tokens da Shuri: única fonte de cor, espaço, raio, tipografia e duração), `CLAUDE.md`, e a API
em `src/forja/api/routers/*.py` (rotas reais). Backend já roda: `.\.venv\Scripts\forja.exe run --port 8799` (3 simuladores).

## Regras da interface (valem para todo bloco)
- Offline: zero CDN, zero fonte remota, zero script externo. Fontes vêm de `node_modules/@ibm/plex-*` (OFL 1.1) via `base.css`.
  Ícones: `@lucide/svelte` (ISC). Gráficos: `uplot` (MIT). Licenças copiadas para `frontend/licenses/` e listadas em "Sobre".
- Tokens: nunca inventar cor, tamanho ou duração; usar `var(--...)` de `tokens.css`. Cobre só em ação primária, nav ativa, foco e
  seleção; nunca status. Estados: verde Normal, âmbar Atenção, vermelho Crítico, ciano informação/comunicação. Lilás só SIMULADO.
- Qualidade do dado sempre visível ao lado do valor: GOOD quieto; SIMULATED badge lilás; UNCERTAIN tracejado "Não validado";
  STALE desbotado + tracejado + idade ("há 12 s") e NUNCA parece atual; COMM_ERROR anel oco ciano, valor "—", máquina DESCONHECIDA; BAD contorno ✕.
- Texto em português do Brasil. Código interno (`BELT_LOAD_LOW`) só em "Detalhes técnicos" (disclosure).
- Sem tela falsa: rota sem backend mostra estado vazio honesto: "Disponível na fase X" ou "Não configurado", com uma frase do motivo.
  Nenhum botão de comando (RUN, STOP, setpoint, reset, tara, span, calibrar) em lugar nenhum fora do painel do simulador, e lá só cenário/sliders.
- Banner permanente de fonte de dados: "DADOS SIMULADOS" (lilás, hachura) quando `data_source == SIMULATED`; "DADOS DO EQUIPAMENTO" quando real.
  Selo 🔒 "Somente leitura" permanente no header (SVG + texto); abaixo de 768 px migra para a faixa de fonte de dados, nunca some.
- Movimento: só com token `--dur-*`; respeita `prefers-reduced-motion` (tokens caem para 0/80 ms; pulso do ONLINE vira ponto fixo;
  números não animam em STALE/COMM_ERROR). Nada pisca. Alerta de processo nunca é toast; toast só para evento de sistema.
- Responsivo: 1920×1080 (sidebar aberta 264 px), 1366×768 (sidebar recolhida 64 px por padrão), tablet 768–1023 (2 colunas, drawer),
  375 px (1 coluna, drawer com scrim, header de 56 px, zero scroll horizontal). Toque mínimo 44×44 px. Nada depende de hover.
- Acessibilidade: foco visível (`--focus`), `aria-current` na nav, `<select>` nativo para o seletor de equipamento, `lang="pt-BR"`,
  números com `Intl.NumberFormat('pt-BR')` (vírgula decimal), datas no fuso da máquina.
- Testes: todo elemento que o Playwright toca tem `data-testid="area-elemento[-detalhe]"` e estado em `data-state`/`data-quality`/`data-conn`.
  Lista central em `frontend/src/lib/testids.ts`. Convenção: `header-equipment-select`, `header-readonly-badge`, `banner-data-source`,
  `sidebar`, `sidebar-toggle`, `sidebar-link-<rota>`, `plant-card-<EQUIPMENT_ID>`, `kpi-<tag>-value`, `kpi-<tag>-quality`,
  `system-view`, `system-view-chip`, `timeline`, `diagnosis-panel`, `wbf-root`, `sim-scenario-<CODIGO>`, `empty-state`.
- Nada sai da máquina. Nada da GTEX inventado: valores vêm da API; perfis de exemplo mostram badge "exemplo".

## Estrutura (frontend/)
```
src/main.ts · App.svelte (shell + roteador)
src/styles/{tokens.css, base.css, print.css}
src/lib/api.ts        cliente fetch tipado para /api/v1 (ver rotas abaixo); erros normalizados {code, message_pt}
src/lib/live.ts       cliente SSE (/api/v1/stream): snapshot → sample/event/status/heartbeat; estado por equipamento; detecção de Edge offline (>12 s sem heartbeat)
src/lib/router.ts     roteador próprio (history API): /app/plant, /app/eq/{id}/{tela}, /app/knowledge/..., /app/tools/..., /app/system/...
src/lib/format.ts     número pt-BR por tag (TAGS.decimals), unidade, idade ("há 12 s"), variação (↓ 54 %, ↑ 48 pontos)
src/lib/state.svelte.ts  equipamento selecionado (da URL), janela de tempo (?w=), tema, sidebar
src/lib/testids.ts
src/components/shell/{AppShell, Header, EquipmentSelect, ReadOnlyBadge, DataSourceBanner, Sidebar, Drawer}.svelte
src/components/ui/{Card, Badge, QualityBadge, StatusDot, Button, EmptyState, Tooltip, Disclosure}.svelte
src/components/data/{KpiTile, AnimatedNumber, Sparkline, WhatChanged, Timeline, EventRow, EvidenceBadge, DiagnosisPanel}.svelte
src/components/wbf/WbfMachine.svelte   (bloco D; props abaixo; stub já existe)
src/routes/{PlantPage, DashboardPage, SimulatorPage, EventsPage, DiagnosisPage, ComingSoonPage}.svelte
public/brand/{favicon.svg, monograma.svg}
```
Build: `npm run build` → `src/forja/ui/dist` (gitignored). O backend serve em `/app/*` com fallback para `index.html`
(`src/forja/api/routers/ui.py`, bloco B) e `/` redireciona para `/app/plant` quando o build existe; sem build, `/` mostra a página
estática atual. Script: `scripts/build_ui.ps1` (npm ci + build) e `scripts/dev_ui.ps1` (vite dev com proxy para o Edge).

## Sidebar (spec §46) e rotas
VISÃO: Planta `/app/plant` · Dashboard `/app/eq/{id}/dashboard`
PROCESSO: Tempo Real `/app/eq/{id}/realtime` · Tendências `/app/eq/{id}/trends` · Histórico `/app/eq/{id}/history`
INTELIGÊNCIA: Alertas `/app/eq/{id}/alerts` · Eventos `/app/eq/{id}/events` · Diagnósticos `/app/eq/{id}/diagnostics` · Early Warning `/app/eq/{id}/early-warning` · Casos anteriores `/app/eq/{id}/cases`
KCM: Alarmes `/app/eq/{id}/kcm/alarms` · Comunicação `/app/eq/{id}/kcm/communication` · Ficha Técnica `/app/eq/{id}/kcm/datasheet` · Componentes `/app/eq/{id}/kcm/components`
CONHECIMENTO: Documentos `/app/knowledge/documents` · Manuais `/app/knowledge/manuals` · Casos `/app/knowledge/cases`
FERRAMENTAS: Simulador `/app/eq/{id}/simulator` · Relatórios `/app/tools/reports` · Exportações `/app/tools/exports`
SISTEMA: Configuração `/app/system/settings` · Backup `/app/system/backup` · Logs `/app/system/logs` · Sobre `/app/system/about`
Fase B/C/D implementam de verdade: Planta, Dashboard, Eventos (lista + detalhe com diagnóstico), Simulador, Sobre.
As demais rotas existem com `EmptyState` honesto ("Disponível na fase E/F/G/L/M") — nunca em branco, nunca botão falso.

## API que a UI consome (já existe; conferir campos no código dos routers)
`GET /health` · `GET /api/v1/system/about` · `GET /api/v1/system/health` · `GET /api/v1/plant` · `GET /api/v1/equipments` ·
`GET /api/v1/equipments/{id}` · `GET /api/v1/equipments/{id}/status` · `GET /api/v1/equipments/{id}/live` ·
`GET /api/v1/equipments/{id}/history?tags&from&to&maxPoints` · `GET /api/v1/equipments/{id}/events?limit` · `GET /api/v1/events/{id}` ·
`GET /api/v1/events/{id}/diagnosis` · `POST /api/v1/events/{id}/ack` · `GET /api/v1/alarms/lookup?equipment_id&code` ·
`GET /api/v1/communication/drivers` · `GET /api/v1/simulator/{id}` · `POST /api/v1/simulator/{id}/scenario` ·
`POST /api/v1/simulator/{id}/controls` · `DELETE /api/v1/simulator/{id}/controls` · `GET /api/v1/stream?eq=`.

## Bloco B+C (Jarvis): shell, planta, dashboard, eventos
- Shell: sidebar recolhível/drawer com os 7 grupos, header (monograma FL, seletor `<select>` com estado por equipamento no texto da opção
  "● Pó Base · Normal", ponto ONLINE pulsando discretamente, selo Somente leitura, relógio local), faixa de fonte de dados.
- Planta: título "GTEX — PHA" (vem do perfil), resumo "3 equipamentos · 1 atenção · 1 sem comunicação", grid de cards (estado, aplicação,
  badge "exemplo" quando `is_example`, frase da anomalia atual, vazão com qualidade, última leitura relativa, último evento). Clique abre o dashboard.
- Dashboard: cabeçalho "Pó Base | WBF | KCM | ● ONLINE | 🔒 Somente leitura"; bloco "O que o sistema está vendo" com chip NORMAL / ATENÇÃO /
  DIAGNÓSTICO DISPONÍVEL e frase em português; 6 tiles (Vazão, Setpoint, Esforço do acionamento, Velocidade indicada, Material na correia,
  Canal de integração) com valor animado (só se qualidade permitir), unidade, mini-tendência SVG (últimos 60 pontos da `/history` + SSE),
  qualidade, botão "Entender esta variável" (explanation_pt da API); dosador animado (`WbfMachine`) ao lado do bloco do sistema;
  timeline dos eventos recentes; resumo do diagnóstico aberto (título, "O que mudou" 3 linhas, link "Abrir diagnóstico").
- Eventos: lista (marcador de estado, título pt, resumo, início, duração, badge "Diagnóstico") e detalhe com `DiagnosisPanel` completo nas
  7 seções (RESUMO, EVIDÊNCIAS, O QUE MUDOU antes/agora/variação, HIPÓTESES com EvidenceBadge traduzido, PRÓXIMAS VERIFICAÇÕES numeradas,
  FONTES, RESSALVAS) e "Detalhes técnicos" colapsado com o JSON.
- Sobre: versão, somente leitura, fonte de dados, licenças (Plex OFL, uPlot MIT, Lucide ISC, Svelte MIT), frase central do produto.
- Backend: `ui.py` servindo `/app/*` do dist com fallback; `/` → redirect `/app/plant` se o dist existir. `scripts/build_ui.ps1`, `scripts/dev_ui.ps1`.
- Entrega: `npm run build` sem erro, `npm run check` sem erro, nenhuma URL `http(s)://` em `dist/` (grep), Edge servindo `/app/plant`.

## Bloco D (segundo front): dosador animado + página do simulador
- `WbfMachine.svelte` (SVG inline + Web Animations API; corte lateral 2D, linhas técnicas, preenchimento plano em tons de grafite, sem 3D).
  Props: `rpm: number|null`, `beltLoad: number|null`, `driveCommand: number|null`, `massFlow: number|null`, `machineState: 0|1|2|null`,
  `quality: 'GOOD'|'SIMULATED'|'UNCERTAIN'|'STALE'|'COMM_ERROR'|'BAD'`, `connection: 'CONNECTED'|'ERROR'|'RECONNECTING'|...`,
  `rpmRef: number|null`, `beltLoadRef: number|null`, `scenario?: string`, `reducedMotion?: boolean`.
  Peças com `data-part`: silo, entrada, partículas, correia, motor, encoder, célula/SFT, saída; rótulos em HTML fora do SVG.
  Comportamento: RUN → correia e partículas se movem com `playbackRate = clamp(rpm/rpmRef, 0, 2)`; densidade de pó ∝ `beltLoad/beltLoadRef`;
  BELTLOAD_LOW visivelmente ralo; ENCODER_FAILURE: correia tracejada "movimento inferido do comando", encoder destacado âmbar "sem sinal", RPM 0;
  COMM_ERROR/STALE: congela, dessatura, faixa "SEM COMUNICAÇÃO · últimos dados antigos · estado da máquina: DESCONHECIDO";
  STOP: parado, partículas somem. Estado exposto em `data-state`, `data-speed`, `data-material-level`, `data-encoder`. Pausa quando a aba está oculta.
  Orçamento: ≤ 60 partículas, ≤ 4 ms por quadro em 1366×768 (medir e reportar).
- `SimulatorPage.svelte`: faixa DADOS SIMULADOS; dosador grande; radio-cards dos 9 cenários (nome pt + código técnico) chamando
  `POST /simulator/{id}/scenario`; sliders (Setpoint, Vazão, Esforço, RPM, Material, Peso líquido, Canal INT) com "Aplicar"/"Limpar"
  (`POST/DELETE /simulator/{id}/controls`); texto explicativo do cenário (spec §39–41); mini-tiles ao vivo. Em equipamento não-simulador a
  página mostra EmptyState "Simulador indisponível: este equipamento lê dados reais" (a API responde 409).
- Entrega: componente funciona isolado com props fixas (página `/app/dev/wbf` só em `import.meta.env.DEV`), `npm run check` limpo.

## Bloco E2E (Edith, depois de B/C/D): Playwright em Python
`pip install pytest-playwright` no `.venv`; navegador `channel="msedge"` (Edge já instalado; sem download) com fallback `playwright install chromium`.
Fixture: sobe `forja run --port <livre>` com `FORJA_DATA_DIR` em tmp e espera `/health`. Testes em `tests/e2e/`: shell (4 viewports, sidebar/drawer,
sem overflow horizontal, selo visível), seletor de equipamento muda a rota e o dashboard, planta mostra Normal/Atenção/Sem comunicação,
dashboard 6 tiles com qualidade SIMULATED, simulador troca para BELTLOAD_LOW e o dosador muda `data-material-level`, evento aparece e o
diagnóstico tem as 7 seções, nenhuma requisição sai de localhost (interceptar), reduced-motion respeitado, nenhum botão com texto de comando.
