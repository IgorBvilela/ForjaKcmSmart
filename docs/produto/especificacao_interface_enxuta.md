# Especificação · Fase Q · Interface enxuta

Estado: aprovada em 2026-10-11. A intenção foi confirmada em entrevista com o responsável pelo produto, e está resumida no §1. Tudo o que aparece como "hoje" foi verificado no código; os exemplos entre colchetes são ilustrativos.

## 1. Objetivo

| | |
|---|---|
| Resultado | Interface com poucas telas, cada uma com um trabalho só, texto curto e sem poluição visual |
| Para quem | Gerente e manutenção da planta |
| Por que agora | O menu chegou a 26 itens em 7 grupos, com nomes parecidos em lugares diferentes |
| Sucesso | Abrir o Forja e, numa olhada, saber se está tudo bem e o que verificar primeiro |
| Onde | PC da planta primeiro; depois modo TV; telas prontas para celular |
| Limite | Nenhuma regra do produto muda (somente leitura, três origens separadas, "comportamento compatível com", qualidade do dado visível, DADOS SIMULADOS) |
| Fora desta versão | Apagar funções; abrir o Forja na rede da planta e criar login (etapa separada, exigida pelo celular) |

## 2. Ponto de partida (verificado no código)

- Menu: 26 itens em 7 grupos (`frontend/src/lib/nav.ts`). Nomes parecidos em grupos diferentes: Alertas, Eventos e Alarmes; Casos anteriores e Casos. Documentos e Manuais só mostram "em desenvolvimento" (fase P).
- A primeira tela ao abrir é a Planta (`frontend/src/lib/router.ts`).
- Planta: grade `auto-fill` com cartão mínimo de 320 px. Pelo CSS, 4 dosadores ficam 3 + 1 no PC, e não 2 × 2. O cartão tem 6 blocos: estado, nome, aplicação, linha de anomalia, vazão com minigráfico e rodapé.
- Comunicação: 7 parágrafos de explicação. O aviso de segurança tem 279 caracteres. Com Modbus TCP, há 13 controles antes do botão de teste.
- Outras telas com muito texto: Exportações (5 parágrafos), Comissionamento (4), Histórico (3), Simulador (3).
- Alertas, Eventos, Diagnósticos, Aviso antecipado e Casos são por equipamento. A visão da planta inteira só existe na Planta.
- Nenhuma rota entrega, de uma vez, o que a tela de ouro precisa. Hoje seriam `/plant`, mais `/alerts` por dosador, mais `/diagnosis` por evento aberto.
- O alarme do KCM não tem hora de início guardada. O campo `since_utc` é a hora da leitura mais recente do código (`src/forja/api/routers/intelligence.py`, `kcm_alarm_view`).
- Não existe medida de "tempo fora do normal" por período.
- Defeito: o resumo da Planta não contava "Coleta pausada" nem "Coleta não iniciada". Com todos os dosadores nesses estados, ele dizia "todos em condição normal". Foi corrigido antes desta fase, com o teste `tests/e2e/test_plant_collection.py`.

## 3. Premissas

1. Só a interface muda, mais uma rota nova de leitura para a tela de ouro. Sem banco novo e sem migração.
2. Nenhum endereço antigo quebra: o link direto continua abrindo. Muda o menu, não a rota.
3. A tela de ouro vira a primeira tela ao abrir.
4. O tema escuro continua como base, porque é o único que o usuário vê hoje.
5. O modo TV, nesta versão, usa uma TV ligada no próprio PC do Forja, como segundo monitor. A interface só abre no próprio PC (`bind_host: 127.0.0.1`, ADR 0030).
6. Celular, nesta versão, quer dizer que as telas principais funcionam em 375 px.
7. O código continua com nomes em inglês (`NowPage`, `TvPage`), e o texto de tela em português.
8. O cabeçalho continua como está: seletor de equipamento, estado do Edge, selo "Somente leitura", relógio e a faixa DADOS SIMULADOS.

## 4. Menu novo

| Ordem | Entrada | Trabalho único | De onde vem |
|---|---|---|---|
| 1 | Agora | Está tudo bem? O que verifico primeiro? | Nova. Reúne o essencial de Alertas, Eventos, Diagnósticos, Aviso antecipado e Casos anteriores |
| 2 | Planta | Ver todos os dosadores | Planta |
| 3 | Dashboard | Um dosador por dentro | Dashboard. Tempo Real, Tendências, Histórico e Eventos viram abas |
| 4 | Comunicação | Ligar um KCM: protocolo, endereço, teste | Comunicação, com o mapping numa seção fechada |
| Pé do menu | Engrenagem | O resto, para quem precisa | Ver a lista abaixo |

A engrenagem reúne:

- **Do dosador:** Ficha técnica, Componentes, Alarmes do KCM, Comissionamento.
- **Dados:** Relatórios, Exportações.
- **Sistema:** Equipamentos (cadastro), Backup, Saúde e logs, Configuração, Sobre.
- **Demonstração:** Simulador.
- **Conhecimento:** Casos de campo.

Documentos e Manuais saem do menu até existirem (fase P).

## 5. Regras de texto e de visual (todas as telas)

**Texto:**
- Título curto, de até 3 palavras.
- No máximo 1 frase de apoio visível ao abrir, com até cerca de 100 caracteres.
- Explicação longa vai em "Saiba mais" (fechado) ou em `docs/`. Código interno só aparece em "Detalhes técnicos", regra que já existe.
- Um aviso de segurança só: o selo "Somente leitura" do cabeçalho. Nenhuma tela repete o parágrafo de segurança.

**Visual:**
- Cada tela tem uma ação principal em destaque.
- Cor forte só com significado: o estado (normal, atenção, crítico, sem comunicação) e a ação principal. O resto fica neutro.
- O número importante aparece grande, com a unidade e a qualidade ao lado.
- "DADOS SIMULADOS" continua visível sempre que o dado for simulado.

**Tamanhos de tela e movimento:**
- Funciona em 375, 768 e 1440 px, e na TV em 1920 × 1080.
- Toque de 44 px. Sem rolagem lateral.
- Animação curta e com função: entrada de cartão, mudança de estado e troca de aba. Respeita `prefers-reduced-motion`.

## 6. Telas

### 6.1 Agora (tela de ouro, primeira tela)

**Topo, para o gerente:** uma frase grande.
- Se tudo está bem: "Tudo dentro do normal" e, embaixo, "[4] dosadores · atualizado há [3 s]".
- Se algo está fora: "[1] de [4] dosadores em atenção".

**Cartões, para a manutenção:** um cartão por dosador com problema, do mais grave para o menos grave. Cada cartão mostra:
- nome, estado e desde quando;
- o que mudou primeiro, do bloco "antes do evento" (`pre_event.first_label_pt` e `lead_s`);
- o que verificar primeiro: a primeira verificação do diagnóstico (`next_checks[0].text_pt`), com o nível de evidência em português;
- a origem, separada: alarme do KCM, evento da Forja ou aviso antecipado;
- as ações "Ver diagnóstico" (as 7 seções) e "Reconhecer" (auditado, como hoje).

**Os outros dosadores:**
- Dosadores sem problema aparecem numa linha compacta cada.
- Dosadores sem dados (sem comunicação, coleta pausada ou coleta não iniciada) ficam num grupo próprio, "Sem dados". Eles nunca contam como normais.

O texto de hipótese é sempre "comportamento compatível com", nunca "causa".

**"Desde quando", sem inventar:**
- **Evento da Forja ou aviso antecipado:** o início do evento aberto mais antigo do dosador.
- **Sem comunicação:** a última leitura boa (`last_ok_utc`).
- **Alarme do KCM:** o início do episódio é buscado no historiador, numa janela limitada. Se não for possível, a tela diz "início não determinado".
- **Aviso antecipado:** a tela usa o estado já avaliado da regra e não recalcula o historiador, porque a prévia de regra é cara.

**Dados:**
- A rota nova `GET /api/v1/situation` é só de leitura e junta, por dosador:
  - o cartão da planta;
  - os eventos abertos, separados por origem;
  - o alarme do KCM;
  - a primeira verificação do diagnóstico;
  - o estado do aviso antecipado.
- A atualização usa o SSE que já existe: o recarregamento acontece quando chega uma mensagem de evento ou de estado, e também a cada 15 s.

### 6.2 Planta

- **Grade quase quadrada:** o número de colunas é a raiz de N, arredondada para cima e limitada pela largura.
  - 4 dosadores ficam em 2 × 2, 6 em 3 × 2 e 9 em 3 × 3.
  - No tablet são 2 colunas; no celular, 1.
- **Cartão só com o essencial:** estado, nome, vazão em destaque e, se não estiver normal, desde quando. A prévia mostra 2 ou 3 versões.
- **Clique no cartão:** abre o Dashboard do dosador.
- **Resumo do topo:** "Sem dados" conta separado, preservando a correção do §2.
- **Áreas:** só aparecem quando houver mais de uma, como hoje.

### 6.3 Dashboard

- **Topo:** nome, estado e vazão.
- **Abas propostas:** Agora, Gráficos, Histórico e Eventos. A aba Eventos dá acesso a alertas, diagnósticos, aviso antecipado e casos anteriores do dosador. Nomes e agrupamento ficam para a prévia.
- **Rotas:** as de hoje continuam, e as abas apontam para elas.

### 6.4 Comunicação

Uma tela direta, em passos curtos:

1. **Protocolo:** Modbus TCP, EtherNet/IP ou Simulador, cada um com o seu estado de suporte (experimental quando for o caso). "Ainda não identificado" continua possível: o que é desconhecido fica `UNKNOWN`.
2. **Endereço:** só os campos daquele protocolo.
   - Modbus TCP pede IP, porta e unit id.
   - EtherNet/IP pede IP e porta.
   - Os tempos e a leitura em bloco ficam em "Avançado", fechado.
3. **Testar (somente leitura):** o botão é grande, e o resultado vem numa frase ("Leu [12] de [12] variáveis em [35 ms]"). O detalhe fica fechado: valor bruto, valor decodificado, qualidade e comparação com a tela do KCM.
4. **Salvar e ativar a coleta:**
   - pede o responsável e o motivo, que vão para a auditoria;
   - a ativação só acontece depois de um teste bem-sucedido da configuração salva, regra que já existe.

O resto da tela:
- **Variáveis (mapping):** seção própria e fechada, com a contagem ("[12] variáveis · [3] sem endereço").
- **Comissionamento:** aparece como próximo passo, com um link, depois de um teste bem-sucedido.
- **Campos de cada protocolo:** continuam definidos na interface, como hoje. Não precisa de rota nova.

### 6.5 Engrenagem

- É um botão no pé do menu, que abre a lista em grupos do §4.
- No celular, fica dentro da gaveta.
- Toda tela de hoje fica a no máximo 2 cliques.

### 6.6 Modo TV

- **Tela:** endereço próprio (`/app/tv`), tela cheia, sem menu e sem precisar de clique.
- **Troca de tela:** mostra a tela Agora. Quando está tudo bem, alterna com a Planta a cada [20 s]. Com problema, fica parada na tela Agora.
- **Leitura:** letra grande, relógio e "atualizado há N s".
- **Dado parado:** Edge sem resposta e dado parado aparecem em destaque. Valor velho nunca aparece como atual.
- **Proteção da TV:** o conteúdo se desloca de leve, de tempos em tempos, para a imagem não marcar a tela.
- **Ligação nesta versão:** a TV é o segundo monitor do PC do Forja, com o Edge em tela cheia ou em modo quiosque.

### 6.7 Celular

- **Nesta versão:** Agora, Planta, Dashboard e Comunicação funcionam em 375 px.
- **Etapa separada, depois do campo:** abrir o Forja na rede da planta. Isso exige três coisas:
  - login com usuários, senhas e permissões (ADR 0014);
  - HTTPS;
  - autorização da TI.
- Essa etapa revisa a ADR 0030.

## 7. O que um produto profissional deste domínio exige

| Exigência | Como entra aqui | Classificação |
|---|---|---|
| Hierarquia de telas (ISA-101): visão geral, unidade, detalhe, diagnóstico | Agora e Planta → Dashboard → Gráficos e Histórico → Diagnóstico | TECHNICAL_OPINION |
| Cor reservada para o anormal (IHM de alto desempenho) | §5 | TECHNICAL_OPINION |
| Alarme ≠ evento, reconhecimento registrado, tela sem enxurrada de alarmes (ISA-18.2) | Três origens separadas, "Reconhecer" auditado, um cartão por dosador | TECHNICAL_OPINION |
| Qualidade sempre visível; valor velho nunca como atual; buraco nunca preenchido | Regras atuais mantidas em todas as telas | FORJA_RULE |
| Tela de sala de controle legível de longe, sem interação, sem marcar a TV | Modo TV | TECHNICAL_OPINION |
| Hipótese com evidência, nunca como causa | A tela Agora mostra o nível de evidência da verificação | FORJA_RULE |

## 8. Stack

A stack não muda.

- **Interface:** Svelte 5 + TypeScript + Vite, com os tokens CSS atuais.
  - Animação em CSS e Web Animations, como hoje. uPlot continua nos gráficos.
  - Nenhuma dependência nova.
- **Backend:** FastAPI, com uma rota nova só de leitura (`GET /api/v1/situation`).
  - O contrato fica em `docs/contracts/CONTRATOS_Q.md`.
  - Sem migração de banco.
- **Por quê:** tudo já está testado (796 testes do núcleo e 77 de navegador). A mudança é de organização, não de tecnologia.
- **Alternativa:** Motion (licença MIT), se a prévia mostrar que falta mola de verdade na animação.

## 9. Comandos

```powershell
.\.venv\Scripts\python.exe -m pytest -q -m "not e2e"     # núcleo
.\.venv\Scripts\python.exe -m pytest -q tests/e2e         # navegador (Edge local)
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m mypy                        # estrito, arquivos em pyproject.toml
cd frontend; npm run check; npm run build; cd ..          # tipos e build da interface
.\scripts\build_ui.ps1                                    # build servido pelo Edge
.\.venv\Scripts\forja.exe run                             # http://127.0.0.1:8765/app
```

## 10. Estrutura

**Interface:**
- Telas novas:
  - `frontend/src/routes/NowPage.svelte`
  - `frontend/src/routes/TvPage.svelte`
- Componentes:
  - em `frontend/src/components/now/`;
  - o menu da engrenagem e as abas do dosador, em `frontend/src/components/shell/`.
- Menu em `frontend/src/lib/nav.ts`. Os títulos das páginas ganham um mapa próprio, porque hoje dependem do menu (`App.svelte`).

**Backend:** rota em `src/forja/api/routers/situation.py`. A junção dos dados fica numa função pura, testável sem servidor.

**Testes:**
- `tests/integration/test_api_situation.py`
- `tests/e2e/test_now.py`
- `tests/e2e/test_tv.py`
- `tests/e2e/test_navigation.py`

**Prévia:** página descartável só no modo de desenvolvimento, como a bancada `dev/wbf`, aberta em localhost. Ela é apagada depois da escolha.

**Documentos:**
- esta especificação;
- a ADR 0033 (menu enxuto e tela de ouro);
- `docs/contracts/CONTRATOS_Q.md`.

## 11. Estilo de código

```svelte
<script lang="ts">
  const cards = $derived(live.plant)
  let equipmentId = $state(app.equipmentId ?? '')

  $effect(() => {
    if (!equipmentId && cards.length) equipmentId = cards[0].id
  })
</script>

<section class="exp" data-testid="exports">
```

- Nomes de código em inglês; texto de tela em português do Brasil.
- `data-testid` em todo elemento de ação.
- Cor, tamanho e tempo só por token (`frontend/src/styles/tokens.css`).
- Comentário técnico e impessoal.

## 12. Estratégia de testes

Cada passo começa pelo teste.

**Núcleo (pytest), na rota da tela Agora:**
- a ordem por gravidade;
- o "desde quando" de cada tipo;
- "sem dados" nunca vira normal;
- o aviso antecipado não recalcula o historiador;
- o início do alarme do KCM vem do historiador, ou a tela diz "início não determinado";
- a rota é GET e entra na prova de somente leitura.

**Navegador (Playwright + Edge):**
- Agora com tudo normal, com "pouco material na correia" e com falha de comunicação.
- Planta em 2 × 2 com 4 dosadores.
- Comunicação direta, contra o servidor Modbus falso de teste.
- Engrenagem: toda tela de hoje alcançável em até 2 cliques.
- Modo TV:
  - sem controles;
  - troca de tela sozinha;
  - fica na tela Agora quando há problema;
  - mostra dado parado.
- Larguras de 375, 768, 1440 e 1920 px.

**Testes que dependem do menu e serão migrados sem perder o que provam:**
- `nav_routes` do `conftest.py`, que passa a ler um registro de rotas, e não o menu;
- `test_shell.py`;
- `test_readonly.py` (`PHASE_NAMES` e a varredura de controles);
- `test_equipment_select.py` (títulos);
- `test_events.py` (menu na impressão).

**Conferência visual:** em 375, 768, 1440 e 1920 × 1080, no tema escuro, com os blocos abertos.

**Portão:** núcleo e navegador verdes; ruff, mypy e svelte-check sem erro.

## 13. Limites

- **Sempre:**
  - teste antes do commit;
  - prévia antes de construir tela;
  - conferência visual antes de entregar;
  - texto em português, tokens e telas responsivas.
- **Perguntar antes:**
  - mudança no backend além da rota da tela Agora e da medida de tempo do §16;
  - dependência nova;
  - abrir o Forja na rede ou criar login;
  - apagar qualquer função;
  - renomear Planta, Dashboard ou Comunicação.
- **Nunca:**
  - escrita no KCM;
  - misturar as três origens;
  - "causa" no lugar de "comportamento compatível com";
  - preencher buraco de leitura;
  - CDN ou fonte remota;
  - publicar qualquer coisa.

## 14. Critérios de sucesso

1. O menu principal tem 4 entradas e a engrenagem.
2. Todas as telas de hoje abrem em até 2 cliques, a partir do menu, da engrenagem ou das abas. A exceção são Documentos e Manuais, da fase P.
3. A tela Agora funciona nos dois casos:
   - com tudo normal, mostra "Tudo dentro do normal";
   - no cenário "pouco material na correia", assim que o evento abre, mostra o cartão do dosador com: desde quando, o que mudou primeiro, o que verificar primeiro e as três origens separadas.
4. Planta: 4 dosadores em 2 × 2 a partir de 1024 px e em 1 coluna em 375 px, sem rolagem lateral.
5. Comunicação: depois de escolher o protocolo, o botão "Testar" aparece sem rolar em 1440 × 900, e só os campos daquele protocolo ficam visíveis.
6. Nenhuma tela principal abre com mais de uma frase de apoio.
7. Modo TV:
   - não tem menu nem controles;
   - troca de tela sozinha;
   - fica na tela Agora quando há problema;
   - mostra "atualizado há N s" e dado parado em destaque.
8. Provas:
   - núcleo e navegador verdes;
   - prova de somente leitura verde;
   - conferência visual com 0 erro em 375, 768, 1440 e 1920 px.
9. O resumo da Planta continua contando "sem dados" à parte, sem nunca chamá-lo de normal (`tests/e2e/test_plant_collection.py` verde).

## 15. Decisões da prévia (2026-10-11)

| Tema | Escolha |
|---|---|
| Nome da tela de ouro | **Agora** |
| Menu | C · trilho com ícones grandes e o nome embaixo; no celular vira gaveta |
| Tela Agora | C · gerente à esquerda (números grandes), manutenção à direita (cartões) |
| Planta | C · cartão com o desvio do setpoint |
| Dashboard | C · abas Visão, Variáveis, Gráficos e Ocorrências |
| Comunicação | A · passo a passo numa coluna |
| Engrenagem | B · página de atalhos em grupos |
| Modo TV | sem escolha na prévia (ver abaixo) |

Itens marcados como "quero":
- **Tela Agora:**
  - linha compacta para os dosadores normais;
  - botão Reconhecer no cartão;
  - nível de evidência ao lado da verificação;
  - frase pronta para o gerente copiar.
- **Planta:** desde quando, se não estiver normal; selo Simulado no cartão.
- **Comunicação:** um botão só, "Salvar e ativar"; aviso de segurança numa frase só.
- **Modo TV:** relógio grande; aviso forte quando um dosador entra em atenção; deslocamento leve para não marcar a TV.

Itens sem resposta, mantidos como a prévia mostrou (o responsável confirma ou recusa):
- contador de problemas ao lado da entrada Agora;
- desenho animado do dosador na aba Visão.

Decisões derivadas das escolhas (o responsável confirma ou recusa):
- **Histórico:** as abas da opção C não têm Histórico.
  - A tabela do historiador vira a vista "Tabela" dentro de Gráficos, porque gráfico e tabela mostram o mesmo período.
  - A rota de hoje continua.
- **Ocorrências:** reúne eventos, alertas (três origens), diagnósticos, aviso antecipado e casos anteriores do dosador.
- **Modo TV:** opção B (tudo numa tela), com convicção.
  - Quem olha a TV vê a tela Agora e a Planta juntas, sem esperar a troca.
  - Quando a Planta não couber, as páginas da Planta alternam a cada 20 s.
  - Com problema, a tela Agora nunca sai de vista.
- **Rota:** a tela Agora fica em `/app/now`; os dados continuam em `GET /api/v1/situation`.

## 16. Extras aprovados na prévia

Todos entram nesta fase, menos o QR code:

1. **Resumo do turno para imprimir:** o que aconteceu no turno e quanto tempo cada dosador ficou dentro do normal, fora do normal e sem dados.
   - Depende da medida nova, descrita abaixo.
   - Os horários dos turnos são da planta: vêm da configuração (`config/`), nunca do código.
   - Sem turno configurado, a tela pede o período (início e fim).
2. **Atalhos de teclado de 1 a 4** para Agora, Planta, Dashboard e Comunicação.
   - Atalho de uma tecla só precisa poder ser desligado (WCAG 2.2, critério 2.1.4). Por isso fica um "ligar/desligar" na página da engrenagem, guardado no navegador.
   - O atalho não age enquanto se digita num campo.
3. **Tema claro opcional:** botão para trocar o tema, com a escolha guardada no navegador. A conferência visual passa a rodar nos dois temas.
4. **Placar do dia na TV:** tempo dentro do normal hoje, por dosador, com a mesma medida nova.
5. **Frase pronta** para o gerente copiar (já marcada na tela Agora).
   - O botão monta a frase sem IA e só copia; nada sai da máquina.
   - Exemplo: "[Dosador A] em atenção desde [14:32]: [material na correia caiu]; verificar primeiro [alimentação do silo]".
6. **QR code na TV para abrir no celular:** anotado para a etapa de rede e login. Antes dela, o celular não alcança o Forja, e o código não teria para onde levar.

**Medida nova: tempo dentro do normal, fora do normal e sem dados**, por dosador e por período.
- **Sem dados:** trecho sem leitura válida (buraco, falha de comunicação, coleta pausada ou não iniciada). Nunca conta como normal nem como fora do normal.
- **Fora do normal:** trecho com evento da Forja aberto (regra, gravidade de atenção para cima) ou com alarme do KCM ativo.
- **Dentro do normal:** o resto do tempo com dado.
- O aviso antecipado não conta como fora do normal: é sinal fraco e aparece à parte.
- Classificação: FORJA_RULE. Contrato em `docs/contracts/CONTRATOS_Q.md`.

## 17. Kit de skills por etapa

| Etapa | Skills | Apoio |
|---|---|---|
| Entrevista | interview-me (feita) | |
| Documento | spec-driven-development | |
| Plano | planning-and-task-breakdown, deprecation-and-migration (troca do menu e dos testes) | arquitetura |
| Prévia | frontend-design, genjutsu (ui-ux-pro-max, desktop-principles, mobile-principles, motion-principles) | identidade visual, celular |
| Construção | incremental-implementation, test-driven-development, frontend-ui-engineering, api-and-interface-design, genjutsu cast (depois do shell estável) | front-end, back-end |
| Testes | browser-testing-with-devtools, conferencia-visual | celular |
| Revisão | code-review-and-quality, security-and-hardening, genjutsu design-audit | segurança, usuário exigente |
| Entrega | documentation-and-adrs, organizacao-profissional, entrega-profissional | supervisão |

O kit do projeto cita `design-taste-frontend` e `dataviz`, que não estão instaladas nesta máquina. `frontend-design` e genjutsu cobrem esse papel. Instalar as duas exige conferir a licença na fonte oficial antes.

## 18. Riscos

- Cerca de 10 testes de navegador dependem do menu. A migração está prevista no §12, sem apagar o que eles provam.
- Os títulos das páginas vêm do menu e precisam de um mapa próprio.
- O início do alarme do KCM não é guardado. A tela Agora calcula pelo historiador, numa janela limitada.
- O modo TV, nesta versão, depende de uma TV ligada no PC do Forja.
- O uso no celular, de verdade, depende da etapa de rede e login (revisão da ADR 0030).
- A tela de Eventos, no modo diagnósticos, faz uma consulta por evento, até 100. A tela Agora não repete esse padrão.
