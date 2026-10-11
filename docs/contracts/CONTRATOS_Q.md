# Contratos da Fase Q — Interface enxuta

Complementa `CONTRATOS_B.md` (casca da interface), `CONTRATOS_E.md` (tempo real) e `CONTRATOS_F.md` (alertas e aviso antecipado). Especificação aprovada: `docs/produto/especificacao_interface_enxuta.md`. Decisões: ADR 0033 (interface enxuta) e ADR 0034 (atualização ao vivo).

Nada nesta fase comanda o KCM. Nenhuma tela foi apagada e nenhuma rota antiga quebrou: o menu encolheu e as telas restantes passaram para a engrenagem (Mais) e para as abas do dosador.

## API: situação da planta (`GET /api/v1/situation`, `src/forja/api/routers/situation.py`)

Somente leitura. Uma resposta com tudo o que a tela Agora e o contador do menu mostram.

| Campo | Conteúdo |
|---|---|
| `generated_at_utc` | Instante da montagem da resposta. |
| `data_source`, `data_source_pt` | `SIMULATED` ou `EQUIPMENT`, com o texto em português. |
| `summary` | `total`, `attention`, `critical`, `no_data`, `stopped`, `normal`, `headline_pt` e `tone` (`ok`, `warn`, `crit`, `info`). |
| `equipments[]` | Por dosador: `id`, `name`, `state_pt`, `group`, `severity`, `since_utc`, `since_basis`, `reason_pt`, `is_simulated`, `data_source`, `mass_flow` (leitura com qualidade), `voices` e `focus`. |
| `voices` | `kcm_alarm` (só quando ativo: código, título, se está catalogado, desde quando), `forja_events` e `early_warnings` (eventos abertos, cada um com origem e reconhecimento), `early_warning_confirming` (regras de aviso em confirmação). As três origens nunca se misturam. |
| `focus` | Evento em destaque: `event_id`, `title_pt`, `origin`, `severity`, `start_utc`, `status`, `acked_by`, `changed_first` (variável que mudou primeiro, com o texto do antes e do agora), `hypothesis_pt`, `next_check` (primeira verificação do diagnóstico, com o nível de evidência) e `diagnosis_available`. |

**Regras:**

- **Grupo:**
  - Crítico ou Atenção vira `problem`.
  - Sem dados (Sem comunicação, Coleta pausada, Coleta não iniciada, Desconhecido) vira `no_data`. Sem dados vence o alarme do KCM: sem leitura, não há alarme confirmado.
  - Alarme do KCM ativo, com leitura, vira `problem`.
  - Parado vira `stopped`; o resto, `normal`.
- **Frase do topo:**
  - com problema: "{n} de {total} dosadores em atenção" (tom `crit` se algum for crítico, senão `warn`);
  - sem problema e com dosador sem dados: "{k} de {total} dosadores sem dados" (`info`);
  - todos com dado e bem: "Tudo dentro do normal" (`ok`);
  - sem dosador: "Nenhum dosador configurado".
  - "Sem dados" nunca conta como normal.
- **Ordem:** grupo, gravidade, desde quando e, por fim, a ordem da configuração.
- **Evento em foco:** o aberto mais grave (informativo não entra); no empate, regra antes de aviso antecipado, e o mais antigo.
- **Desde quando** (`since_basis`), nunca inventado:

  | Base | Origem | Texto na tela |
  |---|---|---|
  | `EVENT` | Início do evento em foco | "desde HH:MM" |
  | `LAST_OK` | Última leitura boa (sem comunicação) | "sem leitura desde HH:MM" |
  | `HISTORIAN` | Início do alarme do KCM achado no historiador | "desde HH:MM" |
  | `BEFORE_WINDOW` | O alarme já estava ativo no começo da janela de 24 h | "há mais de 24 h" |
  | `UNDETERMINED` | Sem base conhecida | "início não determinado" |

- **Início do alarme do KCM:** busca no historiador para trás, em blocos de 1 h, até 24 h, com a mesma regra de "ativo" da leitura ao vivo. O início só vale com uma leitura utilizável de alarme inativo antes da sequência. Buraco maior que 3 vezes o intervalo da amostra forçada, ou leitura inutilizável, deixa o início indeterminado. A hora da leitura mais recente nunca vira início.
- **Aviso antecipado:** usa a última avaliação guardada de cada regra. A rota nunca dispara a prévia do historiador.
- **Motivo** (`reason_pt`): o estado da conexão para sem comunicação; "Coleta pausada (em Comunicação)."; "Falta o teste somente leitura desta configuração (em Comunicação)." para coleta não iniciada.

## API: medida de tempo (`GET /api/v1/time-split` e `GET /api/v1/equipments/{id}/time-split`)

Classificação FORJA_RULE (`src/forja/reports/time_split.py`, `src/forja/api/routers/timesplit.py`). Somente leitura: lê o historiador e os eventos guardados. Parâmetros `from` e `to` (padrão: última hora; o fim nunca passa de agora).

| Parte | Definição |
|---|---|
| Sem dados | Trecho sem leitura válida da variável de referência (buraco, falha de comunicação, coleta pausada ou não iniciada). Nunca conta como normal nem como fora do normal. |
| Fora do normal | Trecho com dado e com evento de regra da Forja aberto (atenção para cima) ou com o alarme do KCM ativo. O aviso antecipado não conta. |
| Dentro do normal | O resto do tempo com dado. |

- **Variável de referência:** a vazão (`mass_flow`); sem ela no mapping, a primeira variável contínua legível.
- **Leitura válida:** qualidade utilizável (validado, simulado ou incerto). Cada leitura vale até a seguinte, no máximo 3 vezes o intervalo da amostra forçada (o mesmo limite de buraco da tela Agora). A leitura de logo antes do início vale no começo do período.
- **Alarme do KCM ativo:** a mesma regra da leitura ao vivo (`forja.events.kcm_alarm`): `alarm_active` = 1 ou `alarm_code` ≠ 0. Leitura sem valor ou sem qualidade encerra o trecho.
- **Resposta:** `from_utc`, `to_utc`, `definition_pt`, `evidence_level` e, por dosador, `id`, `name`, `reference_tag`, `span_s`, `normal_s`, `out_s`, `no_data_s` e as três porcentagens. As três partes somam o período.

## Interface (`frontend/`)

### Rotas

| Rota | Tela |
|---|---|
| `/app/now` | Agora. É a primeira tela: `/` e `/app` levam a ela. |
| `/app/plant` | Planta. |
| `/app/eq/{id}/dashboard` e as telas do dosador | Dashboard com abas: Visão (`dashboard`), Variáveis (`realtime`), Gráficos (`trends`, com a vista Tabela em `history`) e Ocorrências (`alerts`, `events`, `diagnostics`, `early-warning`, `cases`). |
| `/app/eq/{id}/kcm/communication` | Comunicação. |
| `/app/more` | Mais: atalhos em grupos (do dosador, dados, sistema, demonstração, conhecimento). |
| `/app/tv` | Modo TV. `?troca=N` muda a troca de páginas da Planta (5 a 120 s; padrão 20). |

Documentos e Manuais (fase P) ficam fora da navegação até existirem; as rotas continuam com o estado vazio honesto.

### Menu (`src/components/shell/Sidebar.svelte`, `src/lib/nav.ts`)

- Trilho fixo a partir de 1024 px; gaveta abaixo disso, com o foco preso e Escape para fechar.
- Quatro entradas (Agora, Planta, Dashboard, Comunicação) e a engrenagem Mais no pé.
- Entrada acesa: as abas do dosador acendem Dashboard; as telas da página Mais acendem a engrenagem.
- Contador de dosadores em atenção no ícone Agora (no fim da linha, na gaveta).

### Atalhos de teclado (`src/lib/shortcuts.svelte.ts`)

- As teclas 1 a 4 abrem Agora, Planta, Dashboard e Comunicação (no equipamento dos links do menu).
- Não agem com Alt, Ctrl, Shift ou Meta, nem enquanto se digita (campo de texto, área de texto, lista ou texto editável).
- Podem ser desligados na página Mais, seção Teclado (WCAG 2.2, critério 2.1.4). A escolha fica no navegador (`forja.atalhos`).
- Ligados, as entradas do menu anunciam a tecla em `aria-keyshortcuts`.

### Situação compartilhada (`src/lib/situationStore.svelte.ts`)

A tela Agora, o contador do menu, a Planta (motivo e desde quando) e o Modo TV leem a mesma resposta de `/situation`. A consulta acontece a cada 15 s e logo depois de evento, diagnóstico ou mudança da planta, no máximo uma vez a cada 5 s.

### Atualização ao vivo (`src/lib/live.svelte.ts`)

- Atualização de evento aberto que não muda estado, gravidade, qualidade nem reconhecimento não reconsulta listas, planta nem situação.
- A primeira atualização de cada evento só registra o evento: a atualização nunca muda estado nem gravidade, e a tela acabou de consultar.
- `lastEventUpdate` avisa o detalhe do próprio evento, que continua acompanhando as amostras guardadas.

### Regra de texto (`src/components/ui/PageHeader.svelte`)

Cada tela: rótulo, título de até 3 palavras, no máximo uma frase de apoio (até cerca de 100 caracteres) e a explicação longa em "Saiba mais", fechado. Ações da tela (exportar, imprimir, filtros) ficam no próprio cabeçalho. O aviso de segurança da casca é o selo "Somente leitura".

### Planta (`src/routes/PlantPage.svelte`, `src/components/plant/PlantCard.svelte`)

- **Grade quase quadrada:** colunas = raiz de N arredondada para cima, reduzida quando a largura não comporta 280 px por cartão; cartão de até cerca de 640 px. 4 dosadores ficam 2 × 2; 1 coluna no celular.
- **Cartão:** estado, selo Simulado, nome, vazão em destaque, motivo e desde quando fora do normal (da situação compartilhada) e desvio da vazão em relação ao setpoint.
- **Desvio:** só com a máquina em operação e as duas leituras utilizáveis. A barra usa a escala de desenho de ±10 %, e a cor vem do estado do cartão, não de um limite.
- **Link:** camada sobre o cartão inteiro, com o nome "{nome}: {estado}. Abrir dashboard". Os dados do cartão não entram no texto do link.

### Comunicação (`src/routes/CommunicationPage.svelte`)

- **Uma coluna:** Protocolo, Endereço ("Avançado" fechado), Variáveis (fechado, com a contagem), Testar (resultado numa frase) e Salvar e ativar.
- **Botão único:**

  | Situação | Rótulo |
  |---|---|
  | Configuração da tela testada com sucesso, ou simulador | "Salvar e ativar a coleta" |
  | Sem teste válido da configuração da tela, ou protocolo desconhecido | "Salvar sem ativar" |
  | Nada a salvar e coleta pausada, com teste válido da configuração salva | "Ativar a coleta" |
  | Nada a fazer | "Coleta ativa" ou "Nada a salvar" (desabilitado) |

- **Chave de leitura:** a comunicação sem o liga e desliga da coleta, mais o mapping sem as conferências registradas. É conservadora; quem decide a ativação é o servidor (`READ_TEST_REQUIRED`, `NEEDS_CONFIGURATION`).
- **Falha parcial:** se salvar der certo e a ativação for recusada, a tela diz "Configuração salva. A coleta não foi ativada: {motivo do servidor}".

### Modo TV (`src/routes/TvPage.svelte`)

- Sem menu, cabeçalho ou controle.
- Tela Agora à esquerda e Planta à direita. Quando a Planta não cabe, as páginas dela trocam sozinhas, com barra de progresso.
- Brilho por 1 min para o dosador que entra em atenção, só depois da primeira leitura (anel fixo com movimento reduzido).
- Edge sem pulso por mais de 12 s: faixa "Edge sem resposta" e a tela esmaecida. Dado parado é marcado no cartão.
- Deslocamento de até 6 px a cada 2 min, dentro da margem, para a imagem não marcar a TV.
- Abaixo de 900 px: uma coluna, com rolagem.

### Escolha (`src/styles/base.css`)

Radio e caixa de marcar usam a classe `.choice`: o alvo é a linha inteira (44 px), o `input` fica para o teclado e o leitor de tela, e a marca visível é desenho.

### Movimento (`src/lib/motion.ts`)

- `popOnChange` e `flashOnChange`: o selo do estado dá um "pop" e o anel do cartão acende uma vez quando o estado muda. Nada na primeira vez nem com movimento reduzido.
- Ponto vivo do minigráfico: só em dado ao vivo e utilizável.

## Testes

| Arquivo | O que prova |
|---|---|
| `tests/unit/test_time_split.py`, `tests/integration/test_api_time_split.py` | Medida de tempo: as três partes somam o período; sem dados nunca é normal nem fora do normal; aviso antecipado não conta; alarme do KCM ativo conta. |
| `tests/integration/test_api_situation.py` | Regras da situação: grupos, frase do topo, ordem, evento em foco, início do alarme do KCM pelo historiador e aviso antecipado sem prévia. |
| `tests/e2e/test_now.py` | Tela Agora: frase, cartão com o que verificar, reconhecimento, frase pronta e 375 px. |
| `tests/e2e/test_navigation.py` | Primeira tela, ordem do menu, toda tela a até 2 cliques, contador igual ao da tela Agora, no máximo uma consulta da situação a cada 5 s, gaveta com o foco preso e a regra de texto em 21 telas. |
| `tests/e2e/test_equipment_tabs.py` | Abas do dosador. |
| `tests/e2e/test_plant.py`, `test_plant_grid.py`, `test_plant_collection.py` | Planta: cartão, desvio, motivo, 2 × 2 com 4 dosadores, coleta pausada nunca como normal e animação da mudança de estado. |
| `tests/e2e/test_communication.py` | Fluxo de campo contra o Modbus de bancada com o botão único, recusa honesta da ativação e "Testar" à vista em 1440 × 900. |
| `tests/e2e/test_shortcuts.py` | Atalhos 1 a 4, nada enquanto se digita, desligar na página Mais e a escolha guardada. |
| `tests/e2e/test_tv.py` | Modo TV: sem controles, relógio e selo, tela Agora à vista com problema, troca de páginas e Edge derrubado em destaque. |
| `tests/e2e/test_dashboard.py` | Sem recarga por segundo com evento aberto; ponto vivo só com movimento permitido. |
