# Contratos da Fase F — Alertas, Aviso antecipado e Casos anteriores

Complementa `CONTRATOS_A1.md` e `CONTRATOS_E.md`. Tudo aqui é leitura, exceto o reconhecimento de evento, que já existia (`POST /api/v1/events/{id}/ack`) e só registra quem viu e quando, com auditoria. Nada fala com o KCM.

## Três vozes, sempre separadas

| Voz | De onde vem | Como aparece |
|---|---|---|
| **Alarme do KCM** | Tags `alarm_active` e `alarm_code` lidas do controlador; texto pelo catálogo de chave composta | "informado pelo KCM"; reconhecer ou resetar é no próprio KCM |
| **Evento detectado pela Forja** | Regras determinísticas `config/rules/R-*.yaml` (`Event.origin = "RULE"`) | "Evento detectado pela Forja" |
| **Aviso antecipado da Forja** | Regras `config/early_warning/EW-*.yaml` (`Event.origin = "EARLY_WARNING"`) | "Aviso antecipado da Forja"; nunca alarme, nunca previsão |

`Event.origin` é campo novo com padrão `"RULE"`: eventos gravados antes continuam válidos.

## Aviso antecipado

Detecção de tendência, desvio do padrão do próprio equipamento, mudança gradual e combinação de variáveis. Não é previsão de falha. Todo limiar é `FORJA_RULE`, configurável, com `threshold_note_pt`.

### Regra (`src/forja/events/ew_rules.py`)

| Campo | Significado |
|---|---|
| `id` | `EW-<ÁREA>-NNN` |
| `severity` | `INFO` ou `ATTENTION` (`CRITICAL` é recusado: sinal fraco não é falha) |
| `window_s` | Janela observada (60 s a 7 dias) |
| `recent_s` | Trecho final usado como "agora" em desvio, estabilidade e proximidade; cabe duas vezes na janela |
| `baseline` | `window_start` (padrão = primeiros `recent_s` da janela) ou `before_window` (padrão = `baseline_s` antes da janela) |
| `evaluate_every_s` | Ritmo da avaliação (mínimo 10 s) |
| `min_coverage` | Fração mínima de cada trecho com leitura utilizável; abaixo disso, dados insuficientes |
| `persist_evaluations` / `clear_evaluations` | Avaliações seguidas para abrir / para encerrar |
| `applications` | Aplicações em que vale (vazio: todas) |
| `signals` | Sinais combinados por AND |

| Sinal (`kind`) | Parâmetros | Atendido quando |
|---|---|---|
| `trend` | `direction` (`up`, `down`, `any`), `min_change`, `min_fit` | Variação da reta ajustada na janela ≥ `min_change` no sentido pedido e R² ≥ `min_fit` |
| `deviation` | `direction`, `min_change` | Média dos últimos `recent_s` afastada do padrão por ≥ `min_change` |
| `stable` | `max_change` | Média dos últimos `recent_s` a no máximo `max_change` do padrão |
| `near_reference` | `ref_tag`, `max_deviation_pct` | Distância entre a variável e a referência (ex.: vazão e setpoint) ≤ `max_deviation_pct` % |
| `state` | `value`, `min_fraction` | Variável discreta em `value` em pelo menos `min_fraction` do tempo com leitura |

Unidade de `min_change` / `max_change`: percentual para kg/h, kg/m e kg; pontos para variável em %; unidade da própria variável nas demais (a mesma convenção do "O que mudou").

### Avaliação (`src/forja/events/early_warning.py`)

- Lê as séries do historiador (`range`, as mesmas dos gráficos) de `agora − lookback` até agora, com até 240 pontos por variável.
- Cada série vira uma grade regular de 120 células: média ponderada no tempo das leituras utilizáveis. Em resolução bruta, cada linha vale até a próxima (store-on-change), no máximo 120 s. Leitura sem valor, qualidade fora de `allowed_qualities` e trecho sem linha ficam vazios. Nada é interpolado.
- Reta por mínimos quadrados sobre as células com valor (mínimo 5); série plana tem R² 0.
- Combinação: um sinal não atendido basta para não atender; sem dado em algum sinal, "dados insuficientes".

### Motor (`src/forja/events/ew_engine.py`)

- Estado por equipamento e regra, em memória. Abre um evento `EARLY_WARNING` depois de `persist_evaluations` avaliações seguidas atendidas; o início é a primeira delas. Atualiza o resumo no máximo a cada 5 min. Encerra (`RESOLVED`) depois de `clear_evaluations` avaliações seguidas fora da combinação.
- Dados insuficientes nunca abrem aviso e não encerram aviso aberto.
- Dedupe `<equipamento>:<regra>`, id determinístico, diagnóstico pela `diagnosis_ref` da regra. O diagnóstico ganha a ressalva "Aviso antecipado ... não é previsão de falha e não é alarme do KCM".
- `EarlyWarningJob` (`src/forja/service/runner.py`) roda a cada 10 s, equipamento por equipamento; falha num equipamento vai para o log e não interrompe os outros nem a aquisição. As transições passam pelo mesmo caminho dos eventos (`EngineBridge.deliver`: salva, publica, diagnostica).

### Regras de fábrica (`config/early_warning/`)

| Regra | Sinais | Janela |
|---|---|---|
| `EW-BELTLOAD-001` Esforço subindo, vazão mantida e menos material na correia (WBF) | esforço sobe ≥ 8 pontos (R² ≥ 0,6); vazão a até 3% do setpoint; material cai ≥ 10% (R² ≥ 0,5); em operação | 15 min |
| `EW-DRIVE-001` Esforço do acionamento subindo aos poucos | esforço sobe ≥ 8 pontos (R² ≥ 0,6); vazão a até 3% do setpoint; material estável (até 5%); em operação | 30 min |
| `EW-FLOW-001` Vazão se afastando do padrão sem mudança no alvo | vazão ≥ 5% abaixo do padrão; setpoint estável (até 1%); em operação | 30 min |

Pontos de partida da Forja, a ajustar depois de observar a operação real. O simulador tem os 9 cenários do Documento Mestre e nenhum é deriva lenta: na demonstração, o aviso se confirma alguns minutos depois de "Pouco material na correia".

## Antes do evento (`src/forja/events/pre_event.py`)

`pre_event` em toda visão de evento: `first_tag`, `first_label_pt`, `lead_s` (abertura − saída do padrão), `changes` (cada variável com `before_event_s` e `first`), `together` (grupos que saíram com até 30 s de diferença) e `narrative_pt`. Saídas com menos de 1 s de diferença contam como o mesmo instante ("saíram do padrão primeiro, juntas"). Termina sempre com "Ordem dos acontecimentos, não causa." Aviso antecipado não tem instante único de saída e diz isso.

## Ocorrências anteriores (`src/forja/events/recurrence.py`)

Eventos do equipamento agrupados por (origem, tipo): contagem, primeira e última, em aberto, reconhecidos, duração típica (mediana dos encerrados), variável que mais vezes saiu primeiro, classes de resolução e as 5 mais recentes.

## Casos de campo

`FieldCase.equipment_ids` (novo, opcional) liga o caso aos perfis. Sem a lista, vale a combinação planta + área + nome, com os três conhecidos. Casos de outros equipamentos com a mesma aplicação aparecem à parte, marcados "Outro equipamento". Causa só aparece como confirmada com `confirmed_cause` fora de `UNKNOWN` (o modelo já exige descrição).

## API (prefixo `/api/v1`)

| Rota | O que devolve |
|---|---|
| `GET /equipments/{id}/alerts` | `kcm_alarm` (`state`: `ACTIVE`, `NONE`, `UNKNOWN` sem leitura atual, `NOT_MAPPED`; código, título e qualificador do catálogo, qualidade), `forja_events` e `early_warnings` (abertos, inclusive reconhecidos), `counts`, `notes_pt` |
| `GET /equipments/{id}/early-warning` | `disclaimer_pt`, `rules` (estado `ACTIVE`, `CONFIRMING`, `NORMAL`, `INSUFFICIENT`, `PENDING`; por sinal: veredito, texto medido, limite configurado, cobertura, ajuste e até 60 pontos para o mini gráfico), `recent` (avisos registrados). Sem avaliação ainda, faz uma leitura avulsa (`preview: true`) que não conta para a confirmação |
| `GET /equipments/{id}/cases` | `field_cases`, `same_application_cases`, `recurrence`, `note_pt` |
| `GET /knowledge/cases` | Todos os casos de campo |
| `GET /events/{id}` e listas | Ganham `origin`, `origin_pt` e `pre_event` |

Nenhuma rota nova muda estado: a lista fechada de rotas mutantes do contrato OpenAPI não mudou.

## Interface

- `/app/eq/{id}/alerts`: três blocos rotulados e um resumo no topo; "Reconhecer" pede o nome (lembrado neste navegador) e uma observação opcional, com tremida no erro e selo animado no sucesso.
- `/app/eq/{id}/early-warning`: aviso fixo "não é previsão de falha e não é alarme do KCM"; um cartão por regra com estado, janela, ritmo, sinais (mini gráfico da janela, "Agora", "Limite configurado"), nota de evidência e o aviso aberto; histórico de avisos.
- `/app/eq/{id}/cases` e `/app/knowledge/cases` (com busca): ocorrências registradas e casos de campo com o que foi observado, feito, aprendido, medições com natureza e evidência, e "Causa não confirmada".
- Detalhe do evento: bloco "Antes do evento" com a linha de antecedência e o texto.
- No menu, "Aviso antecipado" substitui "Early Warning". Alarmes, Ficha Técnica e Componentes passam a apontar a etapa H (cadastro e ficha dos equipamentos).

## Provas

- `tests/unit/test_early_warning_signals.py`: grade sem interpolação, qualidade não permitida vira buraco, degrau limitado, tendência gradual × oscilação, sentido, percentual × pontos, cobertura insuficiente, desvio do início e de antes da janela, proximidade, estado, combinação AND, o exemplo "esforço sobe + vazão mantida + material cai", regras do repositório válidas e configuração inválida recusada.
- `tests/unit/test_early_warning_engine.py`: abre só após as avaliações seguidas e encerra, operação estável não abre, sem dados não abre nem encerra, aplicação respeitada, ritmo de avaliação, sinal de estabilidade separa os dois avisos de esforço.
- `tests/unit/test_pre_event_recurrence.py`: primeira saída, antecedência, saídas juntas, empate, recorrência por tipo e origem.
- `tests/integration/test_api_intelligence.py`: três vozes separadas, alarme sem leitura desconhecido, reconhecimento mantém aberto e registra quem, prévia sem efeito, aviso ativo e histórico, aplicação, casos e recorrência, "antes do evento" na API.
- `tests/e2e/test_intelligence.py`: alertas e reconhecimento no navegador, aviso antecipado com limites e evidência, casos e busca, "Antes do evento", telas em 375 px; `tests/e2e/test_readonly.py` varre os controles das telas novas.
