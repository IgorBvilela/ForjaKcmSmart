# Contratos da Fase L — Saúde e Logs

Complementa `CONTRATOS_A1.md` (`/health`, `/api/v1/system/about` e `/api/v1/system/health` seguem iguais) e `CONTRATOS_N.md` (pasta de logs). Tudo aqui é leitura: nenhuma rota muda estado e nenhuma fala com o KCM.

## API (prefixo `/api/v1/system`, `src/forja/api/routers/system.py`)

| Rota | O que devolve |
|---|---|
| `GET /health-report` | Relatório de saúde (abaixo), mais `now_utc` e `rules_loaded`. |
| `GET /logs?source=app\|comm\|audit&limit=1..2000&level&equipment_id` | `source`, `source_pt` e `entries` (`ts`, `level`, `origin`, `message_pt`, `detail`), mais recente primeiro. Padrão: `source=app`, `limit=200`. |
| `GET /logs.csv?source&limit=1..20000` | As mesmas entradas em CSV (padrão `limit=5000`), sem filtro de nível nem de equipamento. |

Erros: 404 `EQUIPMENT_NOT_FOUND` para `equipment_id` desconhecido; 422 `VALIDATION_ERROR` para fonte, nível (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`) ou limite inválidos.

### Fontes dos registros

| `source` | `source_pt` | Origem dos dados | `origin` | `detail` | Filtro `level` |
|---|---|---|---|---|---|
| `app` | Serviço | Final do `forja.log` atual (até os últimos 4 MiB; arquivos rotacionados não entram) | nome do logger | traceback, quando há | nível mínimo |
| `comm` | Comunicação | Tabela `comm_log` do historiador: mudanças de estado de conexão por equipamento; `equipment_id` filtra | id do equipamento | `previous`, `current` e, em falha, `exception` e `message` | nível exato; `INFO` traz todos |
| `audit` | Auditoria | `audit_log` do banco core | `user` | `action`, `entity_type`, `entity_id`, `before`, `after` | não se aplica (nível sempre `INFO`) |

`comm_log` é apagado com o bruto do historiador (`historian.raw_retention_days`). `audit_log` é append-only: triggers abortam `UPDATE` e `DELETE`.

### Auditoria em português (`audit_message_pt`)

Mensagem: `<rótulo> (<entity_id>)`, seguida de `: <reason_pt>` quando há motivo. O código da ação fica no `detail`.

| `action` | Rótulo | Gravada por |
|---|---|---|
| `EVENT_ACK` | Evento reconhecido | `POST /api/v1/events/{event_id}/ack` |
| `COMM_CONFIG_SAVE` | Configuração de comunicação salva | `POST /api/v1/communication/{id}/config` |
| `MAPPING_SAVE` | Mapping salvo | `POST /api/v1/communication/{id}/mapping` |
| `COLLECTION_ON` / `COLLECTION_OFF` | Coleta ativada / Coleta pausada | `POST /api/v1/communication/{id}/collection` |
| `COMMISSIONING_OPEN` / `COMMISSIONING_CLOSE` | Sessão de comissionamento aberta / encerrada | rotas de comissionamento (`CONTRATOS_O.md`) |
| `BACKUP_CREATE`, `EQUIPMENT_CREATE` | Backup criado, Equipamento cadastrado | nada no código atual grava essas ações |
| qualquer outra | Alteração registrada | — |

### CSV

BOM UTF-8, separador `;`, fim de linha CRLF, colunas `instante;nivel;origem;mensagem;detalhe` (`detalhe` em texto). Arquivo `forja_logs_<fonte>.csv`, `cache-control: no-store`.

## Relatório de saúde (`src/forja/service/health.py`)

| Campo | Conteúdo |
|---|---|
| `status`, `status_pt` | Pior severidade dos achados: `ok` (Tudo funcionando), `info` (Funcionando, com observações), `warn` (Atenção), `crit` (Problema que precisa de ação). Sem achados: `ok`. |
| `findings` | `[{severity, area, text_pt}]`, do mais grave ao mais leve. |
| `edge` | `version`, `uptime_s`. |
| `equipment` | Um item por equipamento: `equipment_id`, `name`, `driver`, `collecting` (coleta ligada e configuração completa), `connection`, `connection_pt`, `latency_ms`, `consecutive_errors`, `reconnect_count`, `restart_count`, `samples_per_min` (leituras boas nos últimos 60 s), `last_ok_utc`, `since_ok_s`, `is_stale`, `detail_pt`. |
| `storage` | `disk` (`total_bytes`, `free_bytes`, `free_fraction`, medido na pasta de dados) e `historian_fraction` (tamanho do historiador ÷ `historian.max_historian_gb`). |
| `historian`, `core` | `stats()` dos dois bancos: tamanho, linhas por tabela, versão do schema; o historiador traz também última amostra e marcas d'água da consolidação. |
| `jobs` | `runs` e `errors` de `run_rollups` e `run_retention`. |
| `events_engine` | `batches`, `transitions`, `diagnoses` e `errors` do motor de eventos. |
| `realtime` | `clients` e `dropped` do tempo real (SSE). |

### Achados

Regras da Forja sobre a saúde do próprio Edge (FORJA_RULE); nenhuma é limite do KCM. As de aquisição valem só para equipamento com coleta ativa: coleta pausada ou configuração incompleta não é falha.

| Área | Condição | Severidade |
|---|---|---|
| aquisição | Conexão `ERROR` há mais de 300 s, ou sem nenhuma leitura válida desde o início | `crit` |
| aquisição | Conexão `ERROR` há até 300 s | `warn` |
| aquisição | Último valor antigo (`is_stale`) | `warn` |
| aquisição | Coleta reiniciada pelo watchdog (`restart_count` > 0) | `info` |
| aquisição | Nenhum equipamento com coleta ativa | `info` |
| disco | Menos de 10 % livre / menos de 20 % livre | `crit` / `warn` |
| historiador | Acima de 90 % de `historian.max_historian_gb` (padrão 20 GB) | `warn` |
| historiador | Execução com erro na consolidação (`run_rollups`) ou na retenção (`run_retention`) | `warn` |
| eventos | Erro do motor de eventos ao processar lotes | `warn` |
| tempo real | Atualização descartada por tela lenta | `info` |

## Log do serviço (`src/forja/service/logsetup.py`)

- `configure_logging` é chamado pelo `EdgeRunner` (terminal e serviço) depois de montar o container. Arquivo `<pasta de dados>/logs/forja.log` (`var/logs` em desenvolvimento), `RotatingFileHandler` em UTF-8: troca ao atingir `logging.rotate_mb` MiB (padrão 20) e guarda `logging.keep` arquivos anteriores (padrão 10). Nível raiz: `logging.level` (padrão `INFO`); o uvicorn usa o mesmo nível.
- Linha: `<instante ISO com fuso> <NÍVEL> <logger>: <mensagem>`. Linhas seguintes sem esse prefixo (traceback) pertencem à entrada anterior e voltam em `detail`.
- Chamar de novo troca o handler, identificado pelo nome, sem duplicar. `forja run` também escreve no console; o serviço Windows, não.

## Tela (`frontend/src/routes/SystemLogsPage.svelte`, rota `/app/system/logs`)

- Item "Saúde e logs" do grupo Sistema. O relatório é atualizado a cada 10 s.
- Faixa de estado com ícone, `status_pt`, tempo ligado e versão; lista de achados com a área.
- "Aquisição por equipamento": tabela com equipamento e driver, coleta, conexão, latência, leituras por minuto, falhas seguidas, reconexões, reinícios e última leitura válida.
- "Armazenamento": disco livre com barra (âmbar acima de 80 % ocupado, vermelho acima de 90 %), tamanho e amostras do historiador, última amostra, "consolidado até", tamanho do banco de eventos com eventos e auditorias.
- "Motor de eventos e tempo real": regras carregadas, lotes, mudanças de evento, diagnósticos, erros, telas conectadas, atualizações descartadas, execuções e erros da consolidação e da retenção.
- "Registros": abas Serviço, Comunicação e Auditoria; filtro de nível (Todos, Avisos e erros, Só erros) só na aba Serviço; 300 entradas mais recentes; "Detalhes técnicos" por entrada; "Exportar CSV" da aba atual.

## Provas

- `tests/unit/test_health_report.py`: sem achados quando tudo está bem; sem comunicação há 12 min é crítico e vem primeiro; disco com 15 % livre; reinício automático informado; coleta pausada não é falha; erros de tarefas, do motor de eventos e historiador perto do limite viram atenção.
- `tests/unit/test_logsetup.py`: grava em arquivo e lê o final por nível, com o traceback no detalhe; arquivo inexistente devolve vazio; reconfigurar não duplica o handler.
- `tests/integration/test_api_health_about.py`: relatório em português com todos os equipamentos; registros de auditoria, comunicação e serviço; frase da auditoria; CSV com o cabeçalho; fonte inválida recusada com 422.
- `tests/integration/test_core_store.py` e `tests/integration/test_api_real_container.py`: `audit_log` append-only; o reconhecimento de evento grava na trilha do banco real.
- `tests/e2e/test_health.py`: a tela aponta o equipamento sem comunicação, troca de fonte dos registros, exporta CSV e cabe em 375 px.
