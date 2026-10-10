# Contratos da Fase O — Comissionamento

Complementa `CONTRATOS_G.md`. Registro da visita de campo: o que se encontrou no equipamento e cada conferência valor Forja × valor na tela do KCM. Nada aqui fala com o KCM nem afirma que a validação aconteceu: os valores da Forja chegam pela tela, vindos da coleta ou do teste somente leitura.

## Domínio (`src/forja/domain/commissioning.py`)

| Objeto | Conteúdo |
|---|---|
| `CommissioningStatus` | `OPEN` (Em andamento), `CLOSED` (Encerrada). |
| `CheckResult` | `MATCH` (Confere), `MISMATCH` (Diverge), `NOT_EXPOSED` (Não exposta pelo KCM), `NOT_CHECKED` (Não conferida). |
| `CommissioningHeader` | `technician` (obrigatório), `authorized_by` (responsável da planta que autorizou conectar), `visit_date`, `protocol_found`, `kcm_software_version`, `host_interface` (modelo, part number e revisão do módulo Host/Anybus), `ip`, `subnet_mask`, `gateway`, `mapping_id`, `mapping_version`, `host_counters_before`, `host_counters_after`, `notes_pt`. O que não se sabe fica `UNKNOWN`. |
| `CommissioningSession` | `id` (32 hexadecimais gerados; aceita `[A-Za-z0-9_-]{8,64}`), `equipment_id`, `created_at_utc`, `updated_at_utc`, `status`, `header`, `conclusion_pt`. |
| `CommissioningCheck` | `id`, `session_id`, `ts_utc`, `tag` (variável semântica conhecida), `label_pt`, `unit`, `address_text`, `forja_value`, `forja_raw_hex`, `forja_quality`, `kcm_value`, `kcm_text` (quando a tela do KCM não mostra número), `difference`, `result`, `note_pt`, `technician`. |

- `difference` = `kcm_value − forja_value`, calculada pelo domínio quando os dois existem.
- O resultado é escolhido pelo técnico; a Forja não decide se confere.
- Contadores Host antes e depois de conectar: contador de escrita igual nos dois registra que a Forja não escreveu.

## Armazenamento (`forja_core.db`, migração `0002_core_validacao.sql`, `src/forja/historian/core_store.py`)

| Tabela | Regra |
|---|---|
| `commissioning_sessions` | `id`, `equipment_id`, `created_ms`, `updated_ms`, `status` (`OPEN` ou `CLOSED`), `session_json`. Atualizável enquanto `OPEN`; trigger recusa `UPDATE` de sessão `CLOSED` e todo `DELETE`. |
| `commissioning_checks` | `id`, `session_id` (chave estrangeira, `ON DELETE RESTRICT`), `ts_ms`, `tag`, `check_json`. Só `INSERT`: triggers recusam `UPDATE` e `DELETE`. Correção é uma nova conferência. |
| `read_tests` | Mesma migração: cada teste somente leitura, sucesso ou falha (`CONTRATOS_G.md`). Só `INSERT`. |

- O JSON validado pelo domínio é a fonte da verdade; as colunas são cópia para índice. Tempo em epoch ms UTC.
- `add_commissioning_check` confere, na mesma tarefa de escrita, que a sessão existe e está `OPEN`; senão `HistorianError`. `save_commissioning` em sessão encerrada também vira `HistorianError`.
- Sessões do equipamento vêm da mais recente para a mais antiga; conferências, na ordem em que foram gravadas.

## API (prefixo `/api/v1`, `src/forja/api/routers/commissioning.py`)

| Rota | Corpo | Resposta |
|---|---|---|
| `GET /equipments/{id}/commissioning` | — | `sessions` (com `status_pt`), `suggested_tags` e `prefill`: cabeçalho sugerido a partir do perfil (protocolo, versão do software, Host/Anybus, IP, máscara, gateway, mapping em uso e versão); o desconhecido fica `UNKNOWN`. |
| `POST /equipments/{id}/commissioning` | `header` | Detalhe da sessão nova, `OPEN`. |
| `GET /commissioning/{sid}` | — | Detalhe: `session`, `status_pt`, `checks` (com `result_pt`), `summary` (contagem por resultado), `covered_tags`, `suggested_tags`. |
| `POST /commissioning/{sid}/header` | `header`, `user` | Detalhe. Só com a sessão `OPEN`. |
| `POST /commissioning/{sid}/checks` | `tag`, `address_text`, `forja_value`, `forja_raw_hex`, `forja_quality`, `kcm_value`, `kcm_text`, `result`, `note_pt`, `technician` | `check`: o registro gravado, com `id`, `ts_utc` do relógio do Edge, `label_pt` e `unit` do catálogo, `difference` e `result_pt`. |
| `POST /commissioning/{sid}/close` | `conclusion_pt` (obrigatória), `host_counters_after` opcional, `technician` | Detalhe com `status` `CLOSED`. |
| `GET /commissioning/{sid}/report.csv` | — | Relatório CSV (abaixo), com a sessão aberta ou encerrada. |

Erros: 404 `EQUIPMENT_NOT_FOUND`; 404 `SESSION_NOT_FOUND`; 409 `SESSION_CLOSED` (cabeçalho, conferência ou encerramento em sessão encerrada); 422 `UNKNOWN_TAG`; 422 `VALIDATION_ERROR` (campo desconhecido, `sid` fora do padrão, texto acima do limite); 503 `CORE_UNAVAILABLE` (sem banco core).

- Roteiro (`SUGGESTED_TAGS`): `setpoint`, `mass_flow`, `drive_command`, `rpm`, `belt_load`, `alarm_code`, `alarm_active`. Não presume que o KCM expõe essas variáveis: "Não exposta pelo KCM" é resultado válido.
- Nada impede duas sessões abertas no mesmo equipamento; a tela abre a mais recente em andamento.
- Auditoria (`entity_type` `commissioning`): `COMMISSIONING_OPEN` (`after`: `equipment_id`, `visit_date`) e `COMMISSIONING_CLOSE` (`before` e `after`: `status`; `reason_pt`: os primeiros 500 caracteres da conclusão). Cabeçalho e conferências não geram linha de auditoria; a conferência já é registro imutável.

## Relatório CSV (`src/forja/reports/commissioning.py`)

- Dialeto brasileiro: BOM UTF-8, separador `;`, vírgula decimal, fim de linha CRLF. Arquivo `comissionamento_<equipamento>_<data da visita>.csv`, `cache-control: no-store`.
- Primeiro bloco, uma linha `campo;valor` por informação: Relatório, Equipamento, Sessão, Situação, Data da visita, Técnico, Autorizado por, Protocolo encontrado, Versão do software do KCM, Interface Host/Anybus, IP, Máscara, Gateway, Mapping (`<id> v<versão>`), Contadores Host antes, Contadores Host depois, Observações, Conclusão, Aberta em (UTC), Atualizada em (UTC).
- Linha vazia e a tabela das conferências: `data_hora_utc`, `data_hora_planta` (fuso `edge.timezone`), `tag`, `variavel`, `unidade`, `endereco`, `valor_forja`, `bruto_forja_hex`, `qualidade_forja`, `valor_kcm`, `texto_kcm`, `diferenca`, `resultado`, `observacao`, `tecnico`. Nenhum valor é arredondado além do registrado.

## Tela (`frontend/src/routes/CommissioningPage.svelte`, `frontend/src/lib/commissioning.ts`; rota `/app/eq/{id}/kcm/commissioning`)

- Sem sessão: cabeçalho pré-preenchido com `prefill`, a data do dia e o técnico guardado no `localStorage` (`forja.responsavel`); "Abrir sessão" exige o técnico. Protocolo, versão, Host/Anybus, IP, máscara ou gateway em branco viram `UNKNOWN`.
- "Ler valores agora (somente leitura)": com a coleta ativa, usa o último valor da coleta (`GET /api/v1/equipments/{id}/live`), sem conexão extra; com a coleta pausada, faz `POST /api/v1/communication/test-read` com a configuração salva, e esse teste também entra em `read_tests`.
- Um cartão por variável do roteiro e por variável com endereço no mapping em uso: valor da Forja com qualidade, origem e endereço; "Valor na tela do KCM" (aceita `1.281,5` ou `1281.5`; o que não é número vai para `kcm_text`); resultado (padrão Confere); observação; "Registrar conferência". Variável já conferida mostra "já registrada" e aceita nova conferência.
- Tabela das conferências (variável, instante, Forja, KCM, diferença, resultado, observação) e contagem por resultado.
- Encerrar: contadores Host depois de conectar e conclusão do técnico (obrigatória). Sessão encerrada mostra a conclusão e os contadores; o cabeçalho fica bloqueado e os cartões de registro somem.
- "Exportar CSV" e "Imprimir relatório" (`window.print()`). Na impressão (`frontend/src/styles/print.css`, `frontend/src/styles/tokens.css`): tema claro, sem animação, controles ocultos (`.no-print`) e bloco de assinaturas do técnico e do responsável da planta (`.print-only`).
- Lista "Sessões deste equipamento" e "Nova visita" depois de uma sessão encerrada.

## Provas

- `tests/integration/test_api_commissioning.py`: lista vazia com roteiro e cabeçalho pré-preenchido em `UNKNOWN`; sessão aberta e auditada; conferências com diferença calculada e "Não exposta pelo KCM"; resumo; encerramento auditado; conferência recusada depois de encerrar; CSV com cabeçalho e vírgula decimal; cabeçalho só muda com sessão aberta; tag desconhecida 422; sessão inexistente 404.
- `tests/integration/test_core_store_validation.py`: sessão e conferência gravadas; encerrada não aceita edição nem conferência; conferência sem sessão recusada; `read_tests` sem `DELETE`.
- `tests/e2e/test_commissioning.py`: visita completa no navegador (abrir, ler valores da coleta, registrar "Confere" e "Não exposta pelo KCM", exportar CSV, encerrar) e tela em 375 px.
- `tests/contract/test_openapi_no_device_write.py`: as quatro rotas `POST` de comissionamento estão na lista fechada de rotas que mudam estado.
- Não verificado: uso numa visita real ao equipamento.
