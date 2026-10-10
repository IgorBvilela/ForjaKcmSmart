# Contratos da Fase M — Relatórios, Exportações, Backup e Configuração

Complementa `CONTRATOS_E.md` e `CONTRATOS_N.md`. Só a criação de backup grava algo (arquivos na pasta de backups, com auditoria); nada fala com o KCM.

## Backup

- **Conteúdo** (`src/forja/historian/backup.py`, manifesto versão 2): os dois bancos (cópia consistente com o serviço funcionando) e um zip de `config/` e `knowledge/` (`config_<instante>.zip`), cada arquivo com tamanho e sha256 no manifesto. Manifesto versão 1 (só bancos) continua legível.
- **Conferência**: sha256 de todos os arquivos, `integrity_check` nos bancos e, no zip, CRC de cada entrada e caminhos só dentro de `config/` ou `knowledge/` (sem `..`, sem caminho absoluto).
- **Restauração** (linha de comando, serviço parado): `backup restore PASTA --sim` troca os bancos; com `--configuracao`, troca também `config/` e `knowledge/`, guardando antes a configuração atual em `var/backups/antes_da_restauracao_<instante>`.
- **Rotina automática** (`src/forja/service/backups.py`, `BackupJob`): segue `backup` em `config/forja.yaml` — `auto`, `schedule` (HH:MM no fuso da planta; inválido vira 02:00 com aviso) e `keep_last`. Depois de cada backup, apaga os mais antigos além de `keep_last`; só entram pastas `backup_*` com manifesto válido. Falha vai para o log e não para o serviço. Auditoria `BACKUP_CREATE` com usuário `sistema`.

| Rota | O que devolve |
|---|---|
| `GET /api/v1/backups` | Rotina (`auto`, `schedule`, `keep_last`, `next_run_utc`), pasta, nota de restauração e os backups (data, tamanho, versão, arquivos, `has_config`, comando de restauração pronto com e sem `--configuracao`). |
| `POST /api/v1/backups` | Backup agora (responsável e motivo). Auditoria `BACKUP_CREATE`. 501 `BACKUP_UNAVAILABLE` sem historiador SQLite. |
| `GET /api/v1/backups/{nome}/verify` | `ok` e a mensagem. Nome fora de `backup_*` ou fora da pasta de backups: 404/422. |

## Relatório por período (`src/forja/reports/period.py`)

`GET /api/v1/equipments/{id}/report?from&to` (padrão: última hora; até 366 dias):

- **Qualidade do dado no tempo**, por variável legível do mapping (exceto códigos de alarme e parada): cobertura = fração do período com leitura utilizável (a mesma grade sem interpolação do aviso antecipado), média ponderada no tempo, mínimo, máximo, pontos sem comunicação e contagem por qualidade. Até 600 pontos por variável.
- **Eventos e avisos**: agrupados por origem e tipo (ocorrências, tempo dentro do período, pior severidade) e a lista dos 100 mais recentes com duração no período, primeira variável a sair do padrão e antecedência.
- **Alarmes informados pelo KCM**: códigos diferentes de zero lidos em `alarm_code` no período, com vezes, primeira e última, título e qualificador do catálogo da chave do equipamento.
- **Resumo em português** e ressalvas fixas (nada preenchido, ordem não é causa, alarme vem do KCM). Dados simulados são ditos na primeira linha.

## Exportações

| Arquivo | Rota |
|---|---|
| Variáveis, pontos gravados | `GET /api/v1/equipments/{id}/history.csv?resolution=raw` (fase E) |
| Variáveis, resumo por intervalo | `GET /api/v1/equipments/{id}/history.csv?resolution=auto` (fase E) |
| Eventos e avisos | `GET /api/v1/equipments/{id}/events.csv?from&to&dialect` — `inicio_utc`, `inicio_planta`, `fim_utc`, `fim_planta`, `duracao_s`, `equipamento`, `origem`, `tipo`, `titulo`, `severidade`, `estado`, `qualidade`, `primeira_variavel`, `antecedencia_s`, `reconhecido_por`, `resumo` |
| Registros do sistema | `GET /api/v1/system/logs.csv` (fase L) |

Dialeto `br` (`;`, vírgula decimal, BOM) ou `std` (`,` e ponto). Valor ausente sai vazio, nunca zero.

## Configuração

`GET /api/v1/system/settings`: o que está em uso em `config/forja.yaml` (Edge, histórico, eventos, backup, log), as pastas e a versão. Só leitura: para mudar, edita-se o arquivo e reinicia-se o serviço. Não há login nesta versão: a interface só aceita conexões desta máquina e cada alteração pede o nome do responsável, gravado na auditoria.

## Interface

- **Sistema › Backup**: rotina, "Fazer backup agora", lista com "Conferir integridade", "Copiar caminho da pasta" e "Como restaurar" com o comando pronto.
- **Ferramentas › Relatórios**: equipamento e período, relatório para tela e impressão ("Imprimir ou salvar em PDF"; impressão sempre em tema claro, sem os controles).
- **Ferramentas › Exportações**: equipamento, período e formato; quatro arquivos para baixar.
- **Sistema › Configuração**: valores em uso e pastas.
- Ficam como "Em desenvolvimento" só Documentos e Manuais (biblioteca local de documentos).

## Provas

- `tests/integration/test_api_backups.py`: backup com configuração, listagem, conferência, zip adulterado detectado, nome fora da pasta recusado, rotina com limpeza por `keep_last` e auditoria do `sistema`, próximo horário no fuso da planta.
- `tests/integration/test_cli_admin.py`: restaurar a configuração guarda a atual antes.
- `tests/integration/test_api_reports.py`: cobertura no tempo com trecho sem comunicação, eventos por origem, alarme 56 com o qualificador do catálogo, resumo, CSV de eventos, período invertido recusado.
- `tests/e2e/test_tools.py`: backup agora, conferência e comando de restauração; relatório; CSV de eventos e resumido; configuração; telas em 375 px.
