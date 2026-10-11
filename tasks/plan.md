# Plano de implementação · Fase Q · Interface enxuta

Fonte: `docs/produto/especificacao_interface_enxuta.md` (aprovada em 2026-10-11). Branch local: `nova-interface`.

## Visão geral

A interface passa a ter quatro entradas (Situação, Planta, Dashboard, Comunicação) e uma engrenagem, com texto curto e sem poluição visual. A ordem segue fatias verticais: cada tarefa entrega algo que funciona e tem prova. A prévia vem antes de qualquer tela de verdade. As escolhas feitas nela fecham as perguntas em aberto do §15 da especificação.

## Decisões de arquitetura

- **Rotas:** nenhuma rota antiga muda. As telas novas ganham rotas novas (`/app/situation`, `/app/tv`), e só o menu e a rota inicial mudam. Isso protege links, favoritos e a maior parte dos testes de tela.
- **Situação:** uma rota agregada só de leitura (`GET /api/v1/situation`). A junção dos dados fica numa função pura, testável sem servidor. A rota reaproveita os montadores de cartão, alertas e diagnóstico que já existem.
- **Títulos:** os títulos das páginas deixam de depender do menu, com um mapa próprio. Assim o menu pode encolher sem mudar título nenhum.
- **Testes:** os testes de tela que hoje varrem o menu passam a varrer o menu principal e a engrenagem, sem perder o que provam: rolagem lateral, controles de comando e telas futuras honestas.
- **Prévia:** página separada (`frontend/previa.html`), servida só pelo servidor de desenvolvimento e fora do pacote. Ela é apagada depois da escolha.
- **Animação:** CSS e Web Animations, como hoje, sem dependência nova.

## Grafo de dependências

```
T0 prévia ──> escolhas (§15)
T1 junção da Situação ──> T2 início do alarme do KCM ──> T3 tela Situação
T4 títulos independentes do menu ──> T5 menu enxuto + engrenagem ──> T6 abas do Dashboard
T3 + T5 ──> T7 Planta 2 × 2 ──> T8 Comunicação direta
T5 ──> T9, T10, T11 texto enxuto (por grupo de telas)
T3 + T7 ──> T12 modo TV
tudo ──> T13 animações (genjutsu cast) ──> T14 documentos
```

## Tarefas

### Fase 0 · Prévia

**T0 · Prévia interativa em localhost** (L, descartável)
- **O que entrega:** página `previa.html` com seções numeradas: menu, Situação, Planta, Dashboard, Comunicação, engrenagem, modo TV e sugestões extras.
  - Cada seção traz 2 ou 3 opções, com "Escolher", "Quero isto / Não quero" por item e o campo "Algo mais?".
  - O pedido se monta sozinho, e "Copiar o pedido" também fica numa barra fixa embaixo.
  - Os dados são de exemplo e marcados assim.
  - Tem animação de verdade: tremida no erro, selo que aparece, aba com mola, check que pula, gráfico que respira.
- **Aceite:** abre em `http://localhost:5173/app/previa.html`, sem rolagem lateral em 375, 768 e 1440 px, com `prefers-reduced-motion` respeitado e o pedido copiável.
- **Verificação:** `npm run check` sem erro; conferência visual (375, 768, 1440) com 0 erro.
- **Arquivos:** `frontend/previa.html`, `frontend/src/previa/**`.

**Checkpoint 0:** as escolhas do usuário entram no §15 da especificação. Depois disso, a prévia é apagada.

### Fase 1 · Situação (tela de ouro)

**T1 · Junção dos dados da Situação** (M)
- **O que entrega:** função pura mais a rota `GET /api/v1/situation`.
  - Por dosador: estado, origem separada (alarme do KCM, evento da Forja, aviso antecipado), desde quando, o que mudou primeiro e a primeira verificação com o nível de evidência em português.
  - Resumo da planta: contagem por estado, com "sem dados" à parte.
- **Aceite:**
  - a ordem segue a gravidade;
  - pausado, não iniciado e sem comunicação nunca contam como normal;
  - o aviso antecipado não dispara a prévia de regra no historiador.
- **Verificação:** `pytest tests/integration/test_api_situation.py`; a prova de somente leitura continua verde (a rota é GET).
- **Arquivos:** `src/forja/api/routers/situation.py`, `src/forja/api/routers/__init__.py`, `tests/integration/test_api_situation.py`.

**T2 · Início do alarme do KCM pelo historiador** (S)
- **O que entrega:** o início do episódio de alarme ativo, buscado numa janela limitada do historiador, reaproveitando os episódios do relatório.
- **Aceite:**
  - com o episódio dentro da janela, a tela mostra o início real;
  - com o episódio fora da janela, ou sem dado, a tela diz "início não determinado";
  - nunca usa a hora da última leitura.
- **Verificação:** testes de integração com séries sintéticas.
- **Arquivos:** `src/forja/api/routers/situation.py`, `src/forja/reports/period.py`, `tests/integration/test_api_situation.py`.

**T3 · Tela Situação** (M)
- **O que entrega:** `SituationPage` na rota `/app/situation`, com:
  - a frase do topo (para o gerente);
  - os cartões por dosador com problema (para a manutenção);
  - as linhas compactas dos normais;
  - o grupo "Sem dados".
  - Atualiza com o SSE, quando chega mensagem de evento ou de estado, e a cada 15 s.
- **Aceite:**
  - tudo normal mostra "Tudo dentro do normal";
  - "pouco material na correia" mostra o cartão completo;
  - falha de comunicação aparece em "Sem dados";
  - "Reconhecer" é auditado, como hoje.
- **Verificação:** `pytest tests/e2e/test_situation.py` em 375, 768 e 1440 px; conferência visual da tela.
- **Arquivos:** `frontend/src/routes/SituationPage.svelte`, `frontend/src/components/situation/*`, `frontend/src/lib/api.ts`, `frontend/src/App.svelte`, `tests/e2e/test_situation.py`.

**Checkpoint A:**
- núcleo e navegador verdes;
- ruff, mypy e svelte-check sem erro;
- a Situação conferida em tela.

### Fase 2 · Navegação enxuta

**T4 · Títulos independentes do menu** (S)
- **O que entrega:** mapa de títulos por rota. Nenhuma mudança visível.
- **Aceite:** todos os títulos de hoje continuam iguais.
- **Verificação:** `pytest tests/e2e/test_equipment_select.py`.
- **Arquivos:** `frontend/src/App.svelte`, `frontend/src/lib/nav.ts`.

**T5 · Menu com 4 entradas e engrenagem** (M)
- **O que entrega:**
  - menu principal com Situação, Planta, Dashboard e Comunicação;
  - engrenagem no pé do menu, com os grupos da especificação (§4);
  - no celular, a engrenagem fica dentro da gaveta;
  - a rota inicial passa a ser `/app/situation`;
  - Documentos e Manuais saem do menu, mas as rotas continuam honestas.
- **Aceite:**
  - toda tela de hoje fica a até 2 cliques;
  - a gaveta mantém o foco preso, fecha com Escape e devolve o foco.
- **Verificação:**
  - `pytest tests/e2e/test_navigation.py` (novo: percorre todas as telas);
  - migração dos testes de hoje: `conftest.py` (`nav_routes`), `test_shell.py`, `test_readonly.py`, `test_events.py`.
- **Arquivos:** `frontend/src/lib/nav.ts`, `frontend/src/components/shell/Sidebar.svelte`, `frontend/src/components/shell/GearMenu.svelte`, `frontend/src/lib/router.ts`, mais os testes citados.

**T6 · Abas do Dashboard** (M)
- **O que entrega:** abas no topo das telas do dosador, apontando para as rotas de hoje. Nomes e agrupamento conforme a prévia.
- **Aceite:**
  - a aba ativa é marcada (`aria-current`);
  - funciona no teclado;
  - no celular, rola para o lado sem rolar a página.
- **Verificação:** `pytest tests/e2e/test_navigation.py tests/e2e/test_dashboard.py`.
- **Arquivos:** `frontend/src/components/shell/EquipmentTabs.svelte`, as páginas do dosador e `tests/e2e/test_navigation.py`.

**Checkpoint B:**
- todas as telas alcançáveis;
- bateria completa verde;
- conferência visual do menu e da gaveta.

### Fase 3 · Planta e Comunicação

**T7 · Planta em grade quase quadrada e cartão enxuto** (M)
- **O que entrega:** colunas igual à raiz de N, arredondada para cima e limitada pela largura; o cartão escolhido na prévia; o resumo continua contando "sem dados" à parte.
- **Aceite:** 4 dosadores em 2 × 2 a partir de 1024 px; 1 coluna em 375 px; sem rolagem lateral.
- **Verificação:** `pytest tests/e2e/test_plant.py tests/e2e/test_plant_collection.py`, mais um teste novo com 4 perfis num Edge próprio.
- **Arquivos:** `frontend/src/routes/PlantPage.svelte`, `frontend/src/components/plant/*`, `tests/e2e/test_plant_grid.py`.

**T8 · Comunicação direta** (M)
- **O que entrega:** os passos protocolo → endereço → testar → salvar e ativar.
  - Fecham por padrão: os tempos (em "Avançado"), o detalhe do teste e as variáveis (mapping, com contagem).
  - O aviso de segurança vira uma frase.
- **Aceite:**
  - depois de escolher o protocolo, "Testar" aparece sem rolar em 1440 × 900;
  - só os campos daquele protocolo aparecem;
  - o fluxo de campo contra o Modbus de bancada continua passando.
- **Verificação:** `pytest tests/e2e/test_communication.py tests/e2e/test_commissioning.py`.
- **Arquivos:** `frontend/src/routes/CommunicationPage.svelte`, `frontend/src/components/comm/*`, `tests/e2e/test_communication.py`.

**T9 · Texto enxuto: telas de dados** (S, M)
- **Telas:** Tempo Real, Tendências, Histórico, Exportações, Relatórios.
- **O que entrega:** um componente "Saiba mais" para a explicação longa; título curto e 1 frase de apoio.
- **Verificação:** os testes de tela dessas telas.

**T10 · Texto enxuto: telas de sistema** (S, M)
- **Telas:** Backup, Configuração, Saúde e logs, Sobre, Equipamentos.

**T11 · Texto enxuto: telas do dosador na engrenagem e de inteligência** (M)
- **Telas:** Ficha técnica, Componentes, Alarmes do KCM, Comissionamento, Simulador, Alertas, Eventos, Diagnóstico, Aviso antecipado, Casos.
- Dividir em duas partes se passar de 5 arquivos.

**Checkpoint C:**
- bateria completa verde;
- nenhuma tela principal abre com mais de 1 frase de apoio (teste em `test_navigation.py`);
- conferência visual.

### Fase 4 · Modo TV

**T12 · Modo TV** (M)
- **O que entrega:** `TvPage` na rota `/app/tv`.
  - Tela cheia, sem menu e sem controles.
  - Alterna Situação e Planta quando tudo está bem; para na Situação quando há problema.
  - Mostra relógio e "atualizado há N s"; Edge sem resposta e dado parado aparecem em destaque.
  - O conteúdo se desloca de leve para não marcar a TV.
- **Aceite:** os critérios 7 e 8 da especificação, em 1920 × 1080.
- **Verificação:** `pytest tests/e2e/test_tv.py`.
- **Arquivos:** `frontend/src/routes/TvPage.svelte`, `frontend/src/App.svelte`, `tests/e2e/test_tv.py`.

### Fase 5 · Acabamento

**T13 · Animações** (S, M)
- **Com o quê:** genjutsu cast, depois do shell estável.
- **O que entrega:** entrada dos cartões, mudança de estado, troca de aba e gráfico que respira, com `prefers-reduced-motion`.

**T14 · Documentos**
- ADR 0033 (menu enxuto e tela de ouro);
- `docs/contracts/CONTRATOS_Q.md` (rota da Situação);
- README atualizado (fase Q, contagem de testes);
- especificação com o §15 respondido.

**Checkpoint final, nas etapas seguintes do fluxo:**
- Testes: navegador de verdade e conferência visual em 375, 768, 1440 e 1920 px.
- Revisão: code-review-and-quality, security-and-hardening e design-audit.
- Entrega: organizacao-profissional, com a varredura em 0 violações.

## Riscos e mitigação

| Risco | Impacto | Mitigação |
|---|---|---|
| Cerca de 10 testes de tela dependem do menu | Médio | T4 antes de T5; a migração mantém o que cada teste prova |
| As escolhas da prévia mudam o escopo | Médio | O checkpoint 0 atualiza a especificação antes de T3, T6, T7 e T8 |
| Buscar o início do alarme no historiador fica lento | Baixo | Janela limitada; teste de tempo com séries sintéticas |
| O teste da Planta 2 × 2 precisa de 4 dosadores | Baixo | Edge próprio com cópia da configuração e um perfil a mais (padrão de `test_plant_collection.py`) |
| O modo TV exige uma TV no PC do Forja | Baixo | Documentado; a rede com login fica na etapa separada |

## Perguntas em aberto

As do §15 da especificação, todas respondidas pela prévia (T0).
