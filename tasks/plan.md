# Plano de implementação · Fase Q · Interface enxuta

Fonte: `docs/produto/especificacao_interface_enxuta.md` (aprovada em 2026-10-11). Branch local: `nova-interface`.

## Visão geral

A interface passa a ter quatro entradas (Agora, Planta, Dashboard, Comunicação) e uma engrenagem, com texto curto e sem poluição visual. A ordem segue fatias verticais: cada tarefa entrega algo que funciona e tem prova. A prévia vem antes de qualquer tela de verdade. As escolhas feitas nela estão no §15 da especificação, e os extras aprovados, no §16.

## Decisões de arquitetura

- **Rotas:** nenhuma rota antiga muda. As telas novas ganham rotas novas (`/app/now`, `/app/tv`), e só o menu e a rota inicial mudam. Isso protege links, favoritos e a maior parte dos testes de tela.
- **Agora:** uma rota agregada só de leitura (`GET /api/v1/situation`). A junção dos dados fica numa função pura, testável sem servidor. A rota reaproveita os montadores de cartão, alertas e diagnóstico que já existem.
- **Títulos:** os títulos das páginas deixam de depender do menu, com um mapa próprio. Assim o menu pode encolher sem mudar título nenhum.
- **Testes:** os testes de tela que hoje varrem o menu passam a varrer o menu principal e a engrenagem, sem perder o que provam: rolagem lateral, controles de comando e telas futuras honestas.
- **Prévia:** página separada (`frontend/previa.html`), servida só pelo servidor de desenvolvimento e fora do pacote. Ela é apagada depois da escolha.
- **Animação:** CSS e Web Animations, como hoje, sem dependência nova.

## Escolhas da prévia aplicadas (2026-10-11)

| Tarefa | Escolha |
|---|---|
| T3 tela Agora | Opção C: gerente à esquerda, com números grandes; manutenção à direita, com cartões. Mais: linha compacta dos normais, Reconhecer no cartão, nível de evidência e frase pronta para copiar |
| T5 menu | Opção C: trilho com ícones grandes e o nome embaixo. A engrenagem abre a página de atalhos `/app/more` (opção B) |
| T6 abas | Opção C: Visão, Variáveis, Gráficos e Ocorrências. O Histórico vira a vista "Tabela" dentro de Gráficos |
| T7 Planta | Opção C: cartão com o desvio do setpoint, "desde quando" e o selo Simulado |
| T8 Comunicação | Opção A: passo a passo numa coluna, com um botão só, "Salvar e ativar", e o aviso numa frase |
| T12 modo TV | Sem escolha na prévia. Recomendação: B (tudo numa tela), com as páginas da Planta alternando a cada 20 s quando não couberem |

## Grafo de dependências

```
T0 prévia ──> escolhas (§15)
T1 junção da tela Agora ──> T2 início do alarme do KCM ──> T3 tela Agora
T4 títulos independentes do menu ──> T5 menu enxuto + engrenagem ──> T6 abas do Dashboard
T3 + T5 ──> T7 Planta 2 × 2 ──> T8 Comunicação direta
T5 ──> T9, T10, T11 texto enxuto (por grupo de telas)
T3 + T7 ──> T12 modo TV
T15 medida de tempo ──> T16 resumo do turno, T17 placar do dia na TV (depois de T12)
T5 ──> T18 atalhos 1 a 4
tudo ──> T13 animações (genjutsu cast) ──> T19 tema claro ──> T14 documentos
```

## Tarefas

### Fase 0 · Prévia

**T0 · Prévia interativa em localhost** (L, descartável)
- **O que entrega:** página `previa.html` com seções numeradas: menu, Agora, Planta, Dashboard, Comunicação, engrenagem, modo TV e sugestões extras.
  - Cada seção traz 2 ou 3 opções, com "Escolher", "Quero isto / Não quero" por item e o campo "Algo mais?".
  - O pedido se monta sozinho, e "Copiar o pedido" também fica numa barra fixa embaixo.
  - Os dados são de exemplo e marcados assim.
  - Tem animação de verdade: tremida no erro, selo que aparece, aba com mola, check que pula, gráfico que respira.
- **Aceite:** abre em `http://localhost:5173/app/previa.html`, sem rolagem lateral em 375, 768 e 1440 px, com `prefers-reduced-motion` respeitado e o pedido copiável.
- **Verificação:** `npm run check` sem erro; conferência visual (375, 768, 1440) com 0 erro.
- **Arquivos:** `frontend/previa.html`, `frontend/src/previa/**`.

**Checkpoint 0:** as escolhas do usuário entram no §15 da especificação. Depois disso, a prévia é apagada.

### Fase 1 · Tela Agora (tela de ouro)

**T1 · Junção dos dados da tela Agora** (M)
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

**T3 · Tela Agora** (M)
- **O que entrega:** `NowPage` na rota `/app/now`, com:
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
- **Verificação:** `pytest tests/e2e/test_now.py` em 375, 768 e 1440 px; conferência visual da tela.
- **Arquivos:** `frontend/src/routes/NowPage.svelte`, `frontend/src/components/now/*`, `frontend/src/lib/api.ts`, `frontend/src/App.svelte`, `tests/e2e/test_now.py`.

**Checkpoint A:**
- núcleo e navegador verdes;
- ruff, mypy e svelte-check sem erro;
- a tela Agora conferida em tela.

### Fase 2 · Navegação enxuta

**T4 · Títulos independentes do menu** (S)
- **O que entrega:** mapa de títulos por rota. Nenhuma mudança visível.
- **Aceite:** todos os títulos de hoje continuam iguais.
- **Verificação:** `pytest tests/e2e/test_equipment_select.py`.
- **Arquivos:** `frontend/src/App.svelte`, `frontend/src/lib/nav.ts`.

**T5 · Menu com 4 entradas e engrenagem** (M)
- **O que entrega:**
  - menu principal em trilho com ícones grandes: Agora, Planta, Dashboard e Comunicação;
  - engrenagem no pé do trilho, que abre a página de atalhos `/app/more`, com os grupos da especificação (§4);
  - no celular, o trilho vira gaveta, com a engrenagem dentro;
  - a rota inicial passa a ser `/app/now`;
  - Documentos e Manuais saem do menu, mas as rotas continuam honestas.
- **Aceite:**
  - toda tela de hoje fica a até 2 cliques;
  - a gaveta mantém o foco preso, fecha com Escape e devolve o foco.
- **Verificação:**
  - `pytest tests/e2e/test_navigation.py` (novo: percorre todas as telas);
  - migração dos testes de hoje: `conftest.py` (`nav_routes`), `test_shell.py`, `test_readonly.py`, `test_events.py`.
- **Arquivos:** `frontend/src/lib/nav.ts`, `frontend/src/components/shell/Sidebar.svelte`, `frontend/src/components/shell/GearMenu.svelte`, `frontend/src/lib/router.ts`, mais os testes citados.

**T6 · Abas do Dashboard** (M)
- **O que entrega:** abas no topo das telas do dosador (Visão, Variáveis, Gráficos e Ocorrências), apontando para as rotas de hoje.
  - Gráficos tem duas vistas: Gráfico (Tendências) e Tabela (Histórico).
  - Ocorrências reúne eventos, alertas, diagnósticos, aviso antecipado e casos anteriores.
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
- **O que entrega:** colunas igual à raiz de N, arredondada para cima e limitada pela largura; cartão com o desvio do setpoint, "desde quando" e o selo Simulado; o resumo continua contando "sem dados" à parte.
- **Aceite:** 4 dosadores em 2 × 2 a partir de 1024 px; 1 coluna em 375 px; sem rolagem lateral.
- **Verificação:** `pytest tests/e2e/test_plant.py tests/e2e/test_plant_collection.py`, mais um teste novo com 4 perfis num Edge próprio.
- **Arquivos:** `frontend/src/routes/PlantPage.svelte`, `frontend/src/components/plant/*`, `tests/e2e/test_plant_grid.py`.

**T8 · Comunicação direta** (M)
- **O que entrega:** os passos protocolo → endereço → testar → salvar e ativar, numa coluna.
  - Fecham por padrão: os tempos (em "Avançado"), o detalhe do teste e as variáveis (mapping, com contagem).
  - O aviso de segurança vira uma frase.
  - "Salvar e ativar" é um botão só, que faz as duas operações auditadas em sequência. Se salvar der certo e ativar for recusado, a tela diz exatamente isso.
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
  - Tela Agora e Planta juntas (opção B). Quando a Planta não cabe, as páginas dela alternam a cada 20 s; a tela Agora nunca sai de vista.
  - Mostra relógio grande e "atualizado há N s"; Edge sem resposta e dado parado aparecem em destaque.
  - Aviso forte, com brilho suave, quando um dosador entra em atenção.
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
- `docs/contracts/CONTRATOS_Q.md` (rota da tela Agora);
- README atualizado (fase Q, contagem de testes);
- especificação com o §15 respondido.

### Fase 6 · Extras aprovados na prévia

**T15 · Medida de tempo: dentro do normal, fora do normal e sem dados** (M)
- **O que entrega:** função pura e rota GET, por dosador e por período, com a definição do §16 da especificação.
- **Aceite:**
  - sem dados nunca conta como normal nem como fora do normal;
  - aviso antecipado não conta como fora do normal;
  - a soma das três partes dá o período inteiro.
- **Verificação:** testes de integração com séries e eventos sintéticos; prova de somente leitura verde.

**T16 · Resumo do turno para imprimir** (M)
- **O que entrega:** página para imprimir, com o que aconteceu e o tempo de cada dosador nas três partes.
- **Turnos:** vêm da configuração da planta; sem turno configurado, a tela pede o período.
- **Verificação:** teste de tela e impressão (tema claro de impressão).

**T17 · Placar do dia na TV** (S)
- **O que entrega:** tempo dentro do normal hoje, por dosador, no modo TV.
- **Depende de:** T12 e T15.

**T18 · Atalhos de teclado de 1 a 4** (S)
- **O que entrega:** as teclas 1 a 4 abrem Agora, Planta, Dashboard e Comunicação.
- **Aceite:**
  - não agem enquanto se digita num campo;
  - podem ser desligados na página da engrenagem (WCAG 2.2, critério 2.1.4).

**T19 · Tema claro opcional** (M)
- **O que entrega:** botão para trocar o tema, com a escolha guardada no navegador; a paleta clara que já existe é revisada tela a tela.
- **Verificação:** conferência visual nos dois temas.

**Fica para a etapa de rede e login:** QR code na TV para abrir no celular.

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
| A medida "fora do normal" ser lida como acusação ou como causa | Médio | Definição escrita no contrato, sem dados à parte, sem contar aviso antecipado |
| O tema claro nunca foi conferido em todas as telas | Médio | T19 revisa tela a tela; a conferência visual roda nos dois temas |

## Perguntas em aberto

Respondidas pela prévia (§15 da especificação). Ficam para o responsável confirmar ou recusar:
- modo TV na opção B (recomendação);
- Histórico como vista "Tabela" dentro de Gráficos;
- contador de problemas e desenho animado, que ficaram sem resposta na prévia e foram mantidos.
