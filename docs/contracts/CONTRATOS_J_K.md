# Contratos da Fase J/K — Drivers Modbus TCP e EtherNet/IP

Complementa `CONTRATOS_A1.md` (porta `ReadOnlyDriverBase`, `ReadPlan`, `RawFrame`, normalização) e `CONTRATOS_G.md` (configuração e teste pela tela). Os dois drivers só leem e estão `EXPERIMENTAL`: testados contra servidores falsos locais, ainda sem validação no KCM real.

## Estado de suporte (`src/forja/drivers/support.py`, `src/forja/drivers/registry.py`)

| Driver | Estado | Biblioteca | Leitura |
|---|---|---|---|
| `simulator` | `AVAILABLE` | forja | Dados simulados. |
| `modbus_tcp` | `EXPERIMENTAL`; `UNSUPPORTED` se o pymodbus não estiver instalado | pymodbus | Funções 01 a 04. |
| `ethernet_ip` | `EXPERIMENTAL` | cliente CIP mínimo da Forja, sem biblioteca externa | `Get_Attribute_Single` por mensagem explícita, sem conexão de I/O. |

- `DriverSupportState`: `AVAILABLE` (Disponível), `EXPERIMENTAL` (Experimental), `NEEDS_CONFIGURATION` (Requer configuração), `UNSUPPORTED` (Não suportado). Nenhum driver real é `AVAILABLE` sem validação no equipamento real.
- Por equipamento (`equipment_support_state`): `UNSUPPORTED` vence; depois `NEEDS_CONFIGURATION` (driver `UNKNOWN`, IP ou protocolo `UNKNOWN`); senão o estado do driver.
- `DriverRegistry.create` recusa nome desconhecido e driver `UNSUPPORTED` (`UnsupportedDriver`), confere a superfície pública da classe (no registro) e da instância (na criação) e exige `driver.name` igual ao nome registrado.
- O cliente EtherNet/IP usa só a biblioteca padrão do Python e atende à régua do ADR 0008: só mensagem explícita, escrita enumerada (listas fechadas de comandos e serviços) e `Get_Attribute_Single` provado contra respondedor falso próprio.

## Perfil (`communication`)

| Campo | `modbus_tcp` | `ethernet_ip` |
|---|---|---|
| `driver` / `protocol` | `modbus_tcp` / `modbus_tcp` (precisam coincidir) | `ethernet_ip` / `ethernet_ip` |
| `ip` | IPv4 literal, obrigatório | IPv4 literal, obrigatório |
| `port` | 1..65535, obrigatório | 1..65535, obrigatório |
| `unit_id` | 0..255, obrigatório; 0 gera aviso (difusão em alguns equipamentos) | não usado |
| `timeout_s` (padrão 2 s) | tempo de cada requisição (`timeout` do pymodbus) | limite de cada etapa da troca: envio, cabeçalho e corpo |
| `connect_timeout_s` (padrão 3 s) | abertura do TCP | abertura do TCP e `RegisterSession` |
| `max_block_size` | teto do bloco, limitado a 125 registradores ou 2000 bits | não usado |
| `options.block_reads` | `false`: uma requisição por variável (padrão: em bloco) | não usado |
| `poll_interval_s` | 0,25..3600 s; abaixo de 0,5 s gera aviso | igual |

`ip`, `port`, `unit_id` e `max_block_size` nascem `UNKNOWN`; nenhum tem valor de planta no código. A tela oferece a porta padrão do protocolo (502 ou 44818) como botão e nunca a preenche sozinha. Configuração incompleta vira `ConfigError` com o motivo em português (`modbus_settings`, `eip_settings`).

## Endereço no mapping (`protocol_address`)

| Driver | Formato | Regras (`src/forja/normalization/plan.py`) |
|---|---|---|
| `modbus_tcp` | `{area, address, count?, bit?}` | `area`: `holding` (03), `input` (04), `coil` (01), `discrete` (02). `address`: inteiro ≥ 0, base 0, enviado como está (o código não converte numeração de documento). `count` padrão: 1 em coil/discrete; senão o número de palavras do tipo. `int8`/`uint8` recusados (registrador tem 16 bits). `bit` só em holding/input, com `count` 1 ou 2, de 0 a `16 × count − 1`. |
| `ethernet_ip` | `{kind?, class, instance, attribute, offset?, length?, bit?}` | `kind`: `attribute` (padrão) ou `assembly`; os dois leem o atributo do mesmo jeito. `class`, `instance` e `attribute` obrigatórios e sem padrão (`class` e `attribute` ≥ 1). `offset` em bytes (padrão 0). `length` em bytes (padrão: 1 nos tipos de 8 bits, senão 2 × palavras do tipo; obrigatório em `string`). `bit` exige `length` 1, 2 ou 4, de 0 a `8 × length − 1`. |
| `simulator` | `"sim:<tag>"` | Precisa ser exatamente a própria tag. |

Variável com endereço ou tipo `UNKNOWN` fica fora do plano (aviso na validação). Mapping de outro driver ou de outro equipamento (exceto `equipment_id: "*"`) é recusado. `confirmed: true` só é aceito com endereço, tipo, ordem dos bytes e fonte conhecidos e `validation.matched: true` (`src/forja/domain/mapping.py`).

## Leitura em bloco (`ReadPlanCompiler`)

- Modbus: por área, na ordem holding, input, coil, discrete; variáveis ordenadas por endereço; trechos que se tocam ou se sobrepõem viram um bloco enquanto couberem no limite. `block_id` = `<area>:<início>:<quantidade>`; layout por variável `{offset, count, unit: word|bit, bit?}`. Variável maior que o limite é erro de mapping. Um bloco = uma requisição.
- EtherNet/IP: um bloco por (classe, instância, atributo); `block_id` = `eip:<classe>:<instância>:<atributo>`; `count` = maior `offset + length`; layout em bytes. Um bloco = um `Get_Attribute_Single`. Atributo devolvido com menos bytes que `count` vira `DriverReadError`.
- `POST /api/v1/communication/{id}/validate` devolve os blocos e `requests_per_cycle` sem conectar.

## Decodificação (`src/forja/normalization/decoder.py`, `src/forja/normalization/normalizer.py`)

- Tipos: `int8`, `uint8`, `int16`, `uint16`, `int32`, `uint32`, `float32`, `float64`, `bool`, `bitfield16`, `bitfield32`, `string`. Texto vindo do YAML ou JSON vira o tipo, sem diferenciar maiúsculas; erro de digitação é recusado; `UNKNOWN` continua `UNKNOWN`.
- Ordem dos bytes: `big` (ABCD), `little` (DCBA), `big_word_swap` (CDAB), `little_word_swap` (BADC). A reordenação é involução e exige número par de bytes; tipos de 1 byte não reordenam. Ordem `UNKNOWN` numa variável que não é bit resulta em `BAD`.
- `bool`: valor diferente de zero é verdadeiro. `bitfield16`/`bitfield32`: inteiro. `string`: não representável como número.
- Escala: `valor = bruto × factor + offset`. Escala `UNKNOWN`: valor sem conversão, com o motivo "escala não informada".
- Bit: coil e discrete viram 0 ou 1. `bit` em registrador ou atributo monta o inteiro de 16 ou 32 bits com a ordem do mapping (`big` quando `UNKNOWN`) e extrai o bit (0 = menos significativo); com 1 byte, o bit sai direto do byte.

## Qualidade e quadro bruto

| Situação | Qualidade | Valor |
|---|---|---|
| `read()` falhou (timeout, conexão, resposta inválida) | `COMM_ERROR` em todas as variáveis legíveis, com o motivo | nulo |
| Bloco ou variável ausente no quadro | `COMM_ERROR` ("sem leitura") | nulo |
| Decodificação falhou (bloco curto, ordem dos bytes `UNKNOWN`, variável sem layout) | `BAD` ("decodificação falhou: ...") | nulo, sem bruto |
| `string` | `BAD` | nulo, bruto preservado |
| Valor não finito | `BAD` ("valor não numérico") | nulo |
| Fora de `valid_min` / `valid_max` | `BAD` com o limite violado | mantido |
| Leitura válida, entrada `confirmed` | `GOOD` | valor |
| Leitura válida, entrada não confirmada | `UNCERTAIN` ("Não validado") | valor |

`STALE` nunca nasce aqui: é estado derivado do relógio monotônico. `RawFrame` = `{equipment_id, ts_utc, blocks, latency_ms}`; cada `RawBlock` = `{block_id, payload, ts_utc, ts_mono_ns, latency_ms}`. Payload Modbus: tupla de registradores (0..65535) ou de bits (0/1). Payload EtherNet/IP: bytes do atributo. `Sample.raw` guarda os bytes do recorte de cada variável antes de ordem e escala (em coil/discrete, o bit em 2 bytes); a API os expõe em hexadecimal.

## Saúde e capacidades

| | `modbus_tcp` | `ethernet_ip` |
|---|---|---|
| `health()` | `connected`, `last_ok_utc`, `latency_ms` do último quadro, `consecutive_errors`, `detail_pt` (conexão, blocos lidos ou último erro) | mesmos campos; `detail_pt` traz a sessão aberta com a identidade do dispositivo lida por `ListIdentity` (nome, fabricante, produto, revisão, série), quando ele responde, ou o último erro |
| `capabilities()` | `EXPERIMENTAL`, biblioteca pymodbus e versão, `read_areas` coil, discrete, holding, input, `max_block_size` 125, sem identificação do dispositivo | `EXPERIMENTAL`, "forja (cliente CIP mínimo)", `read_areas` attribute, sem `max_block_size`, com identificação do dispositivo |

## Tempo de espera e reconexão

- Modbus: pymodbus com `retries=0` e `reconnect_delay=0` (ADR 0007); não repete nem reconecta sozinho.
- EtherNet/IP: um pedido por vez; resposta conferida por comando, status e contexto; resposta anunciada acima de 65.535 bytes é recusada. `disconnect()` envia `UnRegisterSession` (melhor esforço) e fecha o socket.
- Erros com texto em português: `DriverTimeout` (sem resposta), `DriverConnectError` (conexão recusada ou perdida), `DriverReadError` (exceção Modbus, status CIP, resposta curta ou de outro pedido).
- Uma conexão por driver: `connect()` fecha a anterior antes de abrir outra. Quem tenta de novo é o loop de aquisição (`src/forja/acquisition/loop.py`): grava o lote `COMM_ERROR`, marca `ERROR`, desconecta e reconecta com backoff exponencial (1 s, fator 2, teto 60 s, variação de ±20 %; volta ao início depois de uma leitura boa), somando `reconnect_count`. O watchdog reinicia o loop sem sinal de vida por mais de 3 × `poll_interval_s` (`restart_count`).

## Somente leitura, por camada

| Camada | Onde | Como |
|---|---|---|
| Superfície do driver | `src/forja/domain/ports.py`, `src/forja/drivers/registry.py` | `ReadOnlyDriverBase` recusa, na definição da classe, atributo público fora de `name`, `connect`, `disconnect`, `read`, `health`, `capabilities` ou com prefixo de escrita; o registry confere classe e instância. |
| Cliente Modbus | `src/forja/drivers/modbus_tcp/_client.py` | Expõe só `connected`, `open`, `close`, `read`. `guard_pdu` (gancho `trace_pdu` do pymodbus) levanta `ReadOnlyContractViolation` para função fora de 01–04 antes de virar quadro. |
| Cliente EtherNet/IP | `src/forja/drivers/ethernet_ip/_client.py` | Expõe só `connected`, `open`, `close`, `identity`, `read_attribute`, `read_all`. Encapsulamento só `ListIdentity` (0x63), `RegisterSession` (0x65), `UnRegisterSession` (0x66) e `SendRRData` (0x6F); CIP só `Get_Attribute_All` (0x01) e `Get_Attribute_Single` (0x0E), conferidos antes de montar bytes. Sem `Forward_Open` nem `SendUnitData`. O driver usa só `Get_Attribute_Single`. |
| Fronteira de import | `tests/contract/test_import_boundaries.py` | Bibliotecas de protocolo só em `src/forja/drivers/*/_client.py`. |
| Nomes no código | `tests/contract/test_readonly_driver_contract.py` | Varredura AST: nenhum `write*`, `set_*`, `reset*`, `tare*`, `span*`, `calib*` em `src/forja/drivers/` (única exceção: `set_scenario` e `set_overrides` no controle do simulador). |
| Fio | `tests/fixtures/fake_modbus_server.py`, `tests/fixtures/fake_eip_server.py` | Servidores próprios, independentes dos clientes, registram toda função, comando e serviço recebido; o que não lê recebe exceção ou "serviço não suportado" e nada muda. Os testes conferem que só leitura chegou. |

## O que fica `UNKNOWN` (depende de campo)

- Qual protocolo a interface Host/Anybus expõe: `driver: UNKNOWN` até a confirmação no equipamento; o driver nunca é escolhido por suposição.
- IP, porta, unit id, área, endereço, contagem, classe, instância, atributo, deslocamento, tamanho, tipo, ordem dos bytes e escala: só no perfil e no mapping. O mapping do equipamento de campo em `config/mappings/` nasce com todas as entradas `UNKNOWN`.
- Qualidade `UNCERTAIN` até cada variável ser conferida contra a tela do KCM.
- Validação dos dois drivers no KCM real: pendente; o estado `EXPERIMENTAL` é afirmado por teste.
- Quantas conexões simultâneas o módulo aceita: desconhecido pelo código; o teste somente leitura avisa quando abre conexão adicional com a coleta ativa.
- EtherNet/IP implícito (conexão de I/O): não implementado.

## Provas

- `tests/integration/test_modbus_driver.py`: `float32` nas quatro ordens; variáveis contíguas numa requisição; coil, discrete e bit em registrador; unit id no quadro; sessão inteira só com funções de leitura; bloqueio no fio; superfície do cliente; equipamento desligado, silêncio, exceção Modbus, resposta curta, queda e reconexão; configuração incompleta; registro `EXPERIMENTAL`; teste somente leitura ponta a ponta; mapping vindo de texto.
- `tests/integration/test_eip_driver.py`: `float`, inteiro e bit do atributo; uma requisição por atributo; só comandos e serviços permitidos; identidade na saúde; bloqueio de serviço e comando que não leem; caminho lógico de 8 e 16 bits; atributo inexistente e atributo curto; silêncio, resposta inválida, queda e reconexão; configuração incompleta; registro `EXPERIMENTAL`; teste somente leitura ponta a ponta.
- `tests/integration/test_modbus_acquisition.py`: equipamento Modbus cai e vira `COMM_ERROR` sem valor, o simulador segue gravando, a aquisição reconecta sozinha, só leitura no fio.
- `tests/unit/test_decoder.py`, `tests/unit/test_normalizer.py`, `tests/unit/test_plan_options.py`, `tests/unit/test_mapping_types.py`: ida e volta por tipo e ordem (hypothesis), qualidade por entrada, blocos Modbus e EtherNet/IP, bit no layout, leitura uma a uma, tipos vindos de texto.
- `tests/unit/test_registry.py`, `tests/contract/test_readonly_driver_contract.py`, `tests/contract/test_import_boundaries.py`: estados honestos, recusa de escrita na classe e na instância, varredura AST com violação plantada, fronteira de import.
- `tests/unit/test_backoff.py`, `tests/integration/test_watchdog.py`: backoff com teto e variação; loop travado reiniciado.
- Não verificado: leitura contra um KCM real.
