# Contratos da Fase G — Central de Comunicação KCM

Complementa `CONTRATOS_A1.md` e `CONTRATOS_J_K.md`. Nenhuma rota desta fase envia comando ao KCM: o teste só lê, com driver descartável; as gravações mudam arquivos de configuração da Forja; "coleta" liga ou pausa a leitura periódica da própria Forja. Regras em `src/forja/service/commcenter.py`; rotas em `src/forja/api/routers/communication.py`.

## Fluxo (prefixo `/api/v1/communication`)

1. **Conferir sem conectar** (`POST /{id}/validate`): valida perfil e mapping candidatos, compila o plano de leitura e devolve erros (bloqueiam), avisos (não bloqueiam) e blocos. Nenhuma conexão é aberta e nada é gravado.
2. **Testar somente leitura** (`POST /test-read`): repete a validação; com erro, responde 422 sem conectar. Sem erro, cria um driver descartável, conecta, lê uma vez, normaliza e desconecta. Usa o par perfil e mapping enviado, mesmo antes de salvar. Sucesso ou falha vai para `read_tests` com o fingerprint do par.
3. **Salvar** (`POST /{id}/mapping`, depois `POST /{id}/config`): grava YAML com histórico e auditoria e recarrega só aquele equipamento.
4. **Ativar a coleta** (`POST /{id}/collection`): driver real exige teste bem-sucedido com o fingerprint da configuração salva.

## Estados mostrados (`comm_state`)

Avaliados nesta ordem; vale o primeiro que se aplica.

| Código | Rótulo | Tom | Quando |
|---|---|---|---|
| `PROTOCOL_UNKNOWN` | Protocolo ainda não identificado | `unknown` | Driver `UNKNOWN`, ou driver real com `protocol` `UNKNOWN`. |
| `UNSUPPORTED` | Driver indisponível | `crit` | O registry declara o driver `UNSUPPORTED`. |
| `NEEDS_CONFIGURATION` | Configuração necessária | `warn` | `needs_configuration` (nesta altura da ordem: driver real sem IP). |
| `SIMULATED` | Simulador (demonstração) | `sim` | Driver `simulator`. |
| `COMM_ERROR` | Erro de comunicação | `crit` | Coleta ligada e conexão `ERROR`. |
| `COLLECTING` | Coletando (somente leitura) | `ok` | Coleta ligada e conexão `CONNECTED`. |
| `READ_TEST_OK` / `READ_TEST_FAILED` | Teste de leitura OK / Teste de leitura falhou | `ok` / `crit` | O último teste do equipamento tem o mesmo fingerprint da configuração salva. |
| `EXPERIMENTAL` | Driver experimental: teste a leitura | `warn` | O registry declara o driver `EXPERIMENTAL`. |
| `DRIVER_AVAILABLE` | Driver disponível | `info` | Demais casos. |

`NOT_CONFIGURED` ("Não configurado") existe na tabela de rótulos e no tipo da tela, mas `comm_state` não o produz. O estado de suporte do driver (`AVAILABLE`, `EXPERIMENTAL`, `NEEDS_CONFIGURATION`, `UNSUPPORTED`) é outro vocabulário: ver `CONTRATOS_J_K.md`.

## Fingerprint de leitura e ativação da coleta

`reading_fingerprint(profile, mapping)` = sha256 do JSON canônico (chaves ordenadas) de `equipment_id`, `driver`, `protocol`, `ip`, `port`, `unit_id`, `timeout_s`, `connect_timeout_s`, `max_block_size`, `options`, `mapping_id`, driver do mapping e, por entrada, tag, endereço, `datatype`, `endianness`, `scale`, `valid_min` e `valid_max`. Fica de fora o que não muda a leitura: `collection_enabled`, `poll_interval_s`, `stale_after_s`, versão e notas do mapping, `source`, `confirmed` e `validation` das entradas. Registrar uma conferência e salvar não invalida o teste.

- `POST /{id}/collection` com `active: true` e driver real: 409 `NEEDS_CONFIGURATION` sem IP ou protocolo; 409 `READ_TEST_REQUIRED` (com `details.fingerprint`) se nenhum dos 20 testes mais recentes do equipamento tiver `success` e o fingerprint da configuração salva.
- Driver `simulator` liga sem teste. Driver `UNKNOWN`: 409 `NEEDS_CONFIGURATION`. Pedido que não muda o estado não grava nem audita.
- `POST /{id}/config` nunca liga a coleta: o `collection_enabled` do corpo é ignorado. Se o fingerprint mudou num driver real com a coleta ligada, grava com a coleta pausada e responde `collection_paused_by_change: true`.
- `POST /{id}/mapping` que muda o fingerprint do mapping em uso, com driver real e coleta ligada, também grava o perfil com a coleta pausada; a única linha de auditoria é `MAPPING_SAVE`.
- A mesma regra vale na partida do serviço e em toda recarga do equipamento (`collection_gate_for`, em `EquipmentManager.start`), inclusive para perfil editado à mão em `config/equipment/`: sem teste bem-sucedido da configuração em uso, o equipamento fica parado com "Coleta não iniciada: falta um teste somente leitura bem-sucedido desta configuração" e nenhum pacote vai ao KCM. Falha na própria conferência também bloqueia. Prova: `tests/integration/test_collection_gate.py`.

## Gravação (`src/forja/config/writer.py`)

- A configuração editável vive nos arquivos YAML: perfil em `config/equipment/`, mapping em `config/mappings/`. O banco não guarda perfil nem mapping.
- O arquivo é localizado pelo `id` (ou `mapping_id`) do conteúdo, não pelo nome. Arquivo novo: `<id em minúsculas>.yaml` ou `<mapping_id>.yaml`, nome restrito a `[a-z0-9_-]` e dentro da pasta.
- Valida pelo domínio antes de tocar no disco; inválido: 422 `CONFIG_INVALID`.
- Concorrência otimista. Perfil: `base_hash` (sha256 do JSON canônico do perfil, o `config_hash` da visão) comparado com o arquivo atual. Mapping: `base_version` comparada com a versão no disco (`null` só para mapping novo). Divergência: 409 `CONFIG_CONFLICT` e nada é gravado. Mapping salvo recebe a versão do disco + 1.
- A versão anterior, byte a byte (comentários inclusive), vai para `config/_history/equipment/` ou `config/_history/mappings/` como `<nome do arquivo sem extensão>__<AAAAMMDDTHHMMSSZ>.yaml` (sufixo `_2`, `_3`... no mesmo segundo). O carregador não lê `_history` e o `init` não a copia.
- Troca atômica: arquivo temporário na mesma pasta, `fsync` e `os.replace`. O YAML gravado começa com duas linhas de comentário: origem com instante UTC e onde fica a versão anterior.
- Ordem: valida, grava (com histórico), registra a auditoria, atualiza a memória e recarrega só aquele equipamento. Falha na recarga vai para o log do serviço; o arquivo gravado não é desfeito.
- Mapping compartilhado (`equipment_id: "*"`, driver `simulator` ou usado por mais de um perfil) não é editável: 409 `MAPPING_SHARED`. Equipamento que usa mapping compartilhado (o do simulador, por exemplo) recebe em `editable_mapping` o mapping próprio dele, se existir; senão, um modelo novo (`mapping_id` = id em minúsculas, driver `UNKNOWN`, 10 variáveis com tudo `UNKNOWN`).
- Mapping de driver real precisa compilar em plano de leitura (422 `MAPPING_INVALID`); mapping com driver `UNKNOWN` grava sem compilar.

## `read_tests` (`forja_core.db`, migração `0002_core_validacao.sql`)

Colunas `id`, `equipment_id`, `ts_ms`, `driver`, `final_stage`, `success` (0/1), `latency_ms`, `fingerprint`, `user` e `result_json` (resposta do teste sem `values`). Append-only: triggers abortam `UPDATE` e `DELETE`. Teste de perfil cujo `id` não está na configuração carregada roda, mas não é registrado.

## Auditoria (`audit_log`, append-only)

| `action` | `entity_type` / `entity_id` | `before` → `after` |
|---|---|---|
| `COMM_CONFIG_SAVE` | `equipment` / id do equipamento | `{communication, mapping}` → `{communication, mapping}` |
| `MAPPING_SAVE` | `mapping` / `mapping_id` | `{version}` ou nulo → `{version, entries}` |
| `COLLECTION_ON` / `COLLECTION_OFF` | `equipment` / id do equipamento | `{collection_enabled}` → `{collection_enabled}` |

`user` e `reason_pt` vêm do corpo. Sem trilha de auditoria no container, a rota responde 501 `AUDIT_UNAVAILABLE`.

## API (prefixo `/api/v1/communication`)

| Rota | Corpo | Resposta | Erros |
|---|---|---|---|
| `GET /drivers` | — | `drivers` (por nome: `state`, `state_pt`, `library`, `version`, `reason_pt`); `equipments` (`driver`, `protocol`, `ip_known`, `needs_configuration`, `collection_enabled`, `support_state`, `driver_state`, `message_pt`, `connection`); `read_only` | — |
| `POST /test-read` | `profile`, `mapping`, `user` opcional | `stages` (estágio, instante, texto), `final`, `final_pt`, `success`, `latency_ms`, `error_pt`, `values`, `detail.tags` (por variável: `address_pt`, `block_id`, `datatype`, `endianness_pt`, `raw_hex`, `value`, `value_pt`, `quality`, `quality_pt`, `reason_pt`, `confirmed`), `detail.blocks`, `warnings`, `fingerprint`, `test_id` | 409 `DRIVER_UNSUPPORTED`, 409 `NEEDS_CONFIGURATION`, 422 `MAPPING_MISMATCH`, 422 `CONFIG_INVALID` |
| `GET /{id}` | — | Visão: `profile`, `config_hash`, `mapping`, `mapping_shared`, `editable_mapping`, `editable_mapping_exists`, `fingerprint`, `drivers`, `state` (`code`, `label_pt`, `tone`), `collection`, `runtime`, `last_test`, `last_test_matches`, `read_only` | 404 `EQUIPMENT_NOT_FOUND` |
| `POST /{id}/validate` | `communication`, `mapping` | `ok`, `errors`, `warnings`, `blocks`, `requests_per_cycle`, `fingerprint` (200 mesmo com `ok: false`) | 404 |
| `POST /{id}/config` | `communication` completo, `host_interface?`, `controller?`, `mapping_profile?`, `base_hash`, `user`, `reason_pt` | Visão + `collection_paused_by_change` + `report` (validação da configuração gravada) | 404, 409 `CONFIG_CONFLICT`, 422 `MAPPING_NOT_FOUND`, 422 `CONFIG_INVALID`, 501 |
| `POST /{id}/mapping` | `mapping`, `base_version` (inteiro ou nulo), `user`, `reason_pt` | Visão | 404, 409 `MAPPING_SHARED`, 409 `CONFIG_CONFLICT`, 422 `MAPPING_MISMATCH`, 422 `MAPPING_INVALID`, 422 `CONFIG_INVALID`, 501 |
| `POST /{id}/collection` | `active`, `user`, `reason_pt` | Visão | 404, 409 `NEEDS_CONFIGURATION`, 409 `READ_TEST_REQUIRED`, 409 `CONFIG_CONFLICT`, 501 |
| `GET /{id}/read-tests?limit=1..200` | — | `tests`, mais recente primeiro (padrão 20) | 404 |
| `GET /{id}/log?limit=1..1000` | — | `entries` do log de conexão: `ts_utc`, `level`, `kind`, `message_pt`, `detail` (padrão 200) | 404 |

Em toda rota: campo desconhecido no corpo é 422 `VALIDATION_ERROR`, sem ecoar o valor recebido; corpo acima de 1 MiB é 413 `PAYLOAD_TOO_LARGE`. Em `communication`, campo omitido assume o padrão do modelo. `user` aceita letras, números, `_`, espaço, `.`, `@` e `-` (1 a 64; opcional no teste). Falha de leitura no teste não é erro HTTP: volta 200 com `success: false` e o estágio final (`TIMEOUT`, `CONNECTION_REFUSED`, `INVALID_RESPONSE`, `UNIDENTIFIED`). Com a coleta ativa num driver real, o teste avisa que abriu uma conexão adicional.

## Tela (`frontend/src/routes/CommunicationPage.svelte`, rota `/app/eq/{id}/kcm/communication`)

- Cabeçalho com o estado (`data-code`, `data-tone`) e aviso fixo: a tela grava a configuração da Forja e lê o KCM; nenhum botão envia comando; não há varredura de rede. A visão é atualizada a cada 5 s sem tocar no que está em edição.
- Passos: 1 Protocolo (Ainda não identificado, Modbus TCP, EtherNet/IP, Simulador; cada um com o estado de suporte e o motivo); 2 Endereço (IP, porta com o botão "Usar a porta padrão do protocolo", que nunca preenche sozinho; unit id só no Modbus; tempo de espera, intervalo entre leituras, valor antigo depois de; leitura em bloco só no Modbus); 3 Variáveis (editor de mapping e "Conferir configuração (sem conectar)"); 4 Teste somente leitura (responsável e botão, bloqueado com protocolo não identificado); 5 Salvar (motivo; grava o mapping e depois a configuração); 6 Coleta (ativar ou pausar; conexão, latência, falhas seguidas e último teste, marcado "(outra configuração)" quando o fingerprint não bate).
- IP, porta e unit id em branco viram `UNKNOWN`; no mapping, "Não definido" e fonte em branco também. Com o simulador, o passo 2 só informa e não há mapping editável. Salvar e mudar a coleta exigem o responsável.
- "Ativar coleta" fica habilitado sem alteração pendente e, para driver real, com o último teste bem-sucedido no fingerprint salvo (a rota aceita qualquer um dos 20 mais recentes).
- `frontend/src/components/comm/ReadTestPanel.svelte`: estágios, veredito com latência, avisos e, por variável, onde foi lido, bruto em hexadecimal, tipo e ordem, decodificado e qualidade. O campo "Valor na tela do KCM" mostra a diferença (KCM − Forja). Para driver real, "Confere" e "Diverge" gravam `validation` e `confirmed` na entrada do mapping em edição; "Confere" exige endereço, tipo, ordem dos bytes e fonte conhecidos. Só vale depois de salvar.
- `frontend/src/components/comm/MappingEditor.svelte`: um cartão por variável com o estado (Validada na tela do KCM, Sem endereço, Divergiu na conferência, Não validada); campos de endereço por protocolo (`CONTRATOS_J_K.md`), tipo, ordem dos bytes, escala, faixa válida e fonte do endereço. Mudar endereço, tipo, ordem ou escala desfaz `confirmed`. Variáveis entram e saem pelo catálogo.
- "Detalhes técnicos e log de conexão": driver, protocolo salvo, mapping em uso e versão, início do fingerprint e do hash do perfil, 50 entradas do log de conexão.
- O responsável fica no `localStorage` (`forja.responsavel`), compartilhado com a tela de comissionamento.

## Provas

- `tests/integration/test_api_comm_center.py`: validação sem rede, mapping compartilhado recusado, versão nova com histórico e auditoria, conflito de versão e de hash, endereço incoerente recusado, troca de protocolo grava, audita e pausa a coleta, rota de configuração nunca liga a coleta, ativação exige teste da configuração salva, teste que falhou não libera, histórico de testes e log, modelo de mapping todo `UNKNOWN`.
- `tests/integration/test_api_communication.py`: suporte honesto por driver; 409 para driver indisponível e sem configuração; 422 para mapping de outro equipamento ou protocolo antes de conectar; timeout relatado como resultado; campo desconhecido recusado sem eco.
- `tests/integration/test_read_test.py`: estágios do teste, `NotConfigured` e `UnsupportedDriver` propagados, teste sem tocar nos loops em execução.
- `tests/unit/test_config_writer.py`: gravação atômica, histórico da versão anterior, conflito de hash e de versão, id impróprio para nome de arquivo.
- `tests/integration/test_core_store_validation.py`: `read_tests` em ordem e `DELETE` recusado.
- `tests/e2e/test_communication.py`: fluxo completo no navegador contra servidor Modbus de bancada (conferir sem conexão, testar, comparar, salvar com histórico, ativação liberada só com o fingerprint salvo, Tempo Real com qualidade `GOOD`, só funções de leitura no fio) e tela em 375 px.
- `tests/contract/test_openapi_no_device_write.py`: as cinco rotas `POST` desta fase estão na lista fechada de rotas que mudam estado.
