[IMAGEM #1]
# FORJA KCM INTELLIGENCE
Documento Mestre de Contexto Técnico, Arquitetura, Pesquisa e Desenvolvimento para Claude Code
Versão 1.0  •  30/09/2026  •  Forja Lógica

| “O KCM controla a dosagem. A Forja observa o KCM, entende o comportamento e ajuda o técnico a diagnosticar.” |
|---|

USO INTERNO DE DESENVOLVIMENTO • READ-ONLY • OFFLINE-FIRST
# Resumo executivo
Este documento consolida as decisões técnicas, evidências de campo, regras de segurança, estado atual do software e requisitos de evolução do Forja KCM Intelligence. Ele deve acompanhar os documentos originais do projeto e servir como mapa para o Claude Code, sem substituir manuais oficiais nem preencher lacunas específicas da GTEX por inferência.

| Princípio | Regra |
|---|---|
| Arquitetura | KCM → Host/Anybus → Forja Edge → Historian → Eventos → Diagnóstico → UI |
| Controle | Nenhuma escrita no KCM. Sem RUN/STOP/setpoint/reset/calibração. |
| PLC/SCADA | Não são intermediários obrigatórios nem fallback de aquisição. |
| Campo | Protocolo, IP, KGR e mapping permanecem UNKNOWN até validação. |
| Diagnóstico | Correlação não é causa. Mostrar evidência, hipótese e próxima verificação. |
| Operação | Offline-first, local, resiliente e preparado para múltiplos KCMs. |

# 0. COMO USAR ESTE DOCUMENTO
Este documento deve ser tratado como fonte de contexto do projeto, não como substituto dos manuais originais. O Claude deve:
1. ler este arquivo inteiro antes de modificar código;
2. ler o repositório atual e seus testes;
3. ler os documentos originais disponíveis em `/docs/reference/`;
4. diferenciar fato confirmado, observação de campo, decisão de arquitetura, hipótese e pendência;
5. pesquisar somente o que não estiver coberto pelos documentos locais, priorizando fontes oficiais;
6. nunca transformar informação genérica de internet em configuração específica da GTEX;
7. nunca inventar protocolo, KGR, IP, assembly, register, offset, bit, scale, byte order, alarme ou status.
Se houver conflito entre este documento e uma fonte original específica da máquina, registrar o conflito e priorizar a evidência mais específica e rastreável.
# 1. DEFINIÇÃO DO PRODUTO — REGRA ABSOLUTA
O Forja KCM Intelligence é uma camada independente de monitoramento, histórico, detecção de comportamento anormal e diagnóstico técnico para sistemas de dosagem Coperion K-Tron/KCM.
Frase central do produto:
O KCM controla a dosagem. A Forja observa o KCM, entende o comportamento e ajuda o técnico a diagnosticar.
O produto não é outro supervisório e não deve tentar substituir o sistema existente da planta.
## 1.1 O supervisório existente normalmente faz
- visualização do processo;
- comando de partida/parada;
- alteração de setpoint;
- exibição de alarmes;
- operação da máquina.
## 1.2 O Forja deve fazer
- ler diretamente o KCM quando a interface real permitir;
- historizar os sinais;
- identificar o que mudou e quando mudou;
- capturar contexto anterior ao evento;
- correlacionar variáveis;
- contextualizar alarmes;
- separar parada normal de falha;
- gerar hipóteses e verificações técnicas;
- informar o nível de evidência de cada conclusão;
- encontrar casos semelhantes;
- construir memória técnica do equipamento;
- permitir análise local e offline.
## 1.3 O Forja nunca deve
- dar RUN ou STOP;
- alterar setpoint;
- resetar alarme;
- alterar parâmetros;
- fazer Tare, Span ou calibração;
- modificar Feed Factor;
- comandar motor ou saída;
- escrever register/assembly;
- usar PLC como intermediário obrigatório;
- usar SCADA como fonte obrigatória;
- depender de internet para operação básica.
Read-only não é opção de configuração: é requisito estrutural.
# 2. ARQUITETURA OBRIGATÓRIA
A arquitetura conceitual é:
DOSADOR
   ↓
KCM
   ↓
HOST / ANYBUS
   ↓  READ ONLY
FORJA EDGE / PC DA PLANTA
   ↓
Aquisição
   ↓
Normalização semântica
   ↓
Historian
   ↓
Eventos determinísticos
   ↓
Diagnóstico
   ↓
UI / Relatórios / IA opcional
PLC e SCADA não são origem nem intermediário do produto.
Arquiteturas proibidas:
KCM → PLC → Forja
KCM → SCADA → Forja
A única camada dependente de protocolo deve ser o driver. Todo o restante trabalha com tags semânticas normalizadas.
# 3. TAXONOMIA DE CONHECIMENTO E EVIDÊNCIA
Toda informação técnica deve carregar origem e nível de confiança.
## 3.1 Estados de conhecimento durante desenvolvimento
- FACT / CONFIRMADO: comprovado por documento do projeto ou evidência de campo rastreável.
- OFFICIAL_DOC: confirmado por documentação oficial adequada do fabricante/protocolo.
- FIELD_CONFIRMED: causa ou condição confirmada em campo por evidência suficiente.
- FIELD_OBSERVED: ocorrência real observada, mas sem causa necessariamente confirmada.
- DECISÃO: decisão arquitetural deliberada do produto.
- INFERENCE / HIPÓTESE: interpretação técnica plausível, ainda não comprovada.
- UNKNOWN / PENDÊNCIA: informação ainda não conhecida.
## 3.2 Níveis de evidência do produto
Manter no diagnóstico:
- `MANUFACTURER_DOC`
- `MACHINE_DOC`
- `FIELD_CONFIRMED`
- `FIELD_OBSERVED`
- `FORJA_RULE`
- `TECHNICAL_OPINION`
- `HYPOTHESIS`
Cada hipótese, verificação e fonte deve possuir seu próprio nível. Nunca dar um único nível de evidência ao diagnóstico inteiro.
## 3.3 Regra de promoção documental
Uma entrada só pode virar `DOC_REFERENCED`/documentada quando houver referência rastreável suficiente, idealmente:
- fabricante/documento;
- revisão;
- seção/página;
- escopo aplicável.
Uma foto de campo completa continua sendo `FIELD_OBSERVED`; não vira documento de fabricante apenas por estar bem identificada.
# 4. POLÍTICA DE PESQUISA PARA O CLAUDE
O Claude não possui toda a documentação técnica. Ele deve pesquisar quando necessário, mas com hierarquia rígida.
## 4.1 Prioridade de fontes externas
1. Coperion / K-Tron oficial;
2. HMS Networks / Anybus oficial;
3. ODVA / Rockwell quando EtherNet/IP for relevante;
4. Modbus Organization quando Modbus for relevante;
5. documentação oficial da biblioteca de software escolhida;
6. fontes técnicas secundárias apenas como apoio.
## 4.2 O que deve ser pesquisado quando necessário
- arquitetura KCM/K-Tron;
- interfaces Host compatíveis;
- Anybus-S/Anybus aplicável ao hardware real;
- KGR e Host File;
- EtherNet/IP e Modbus TCP read-only;
- limites de sessão/conexões simultâneas;
- bibliotecas Python adequadas;
- reconexão e watchdog;
- serviço Windows;
- packaging offline;
- segurança OT.
## 4.3 O que a internet NÃO pode confirmar sobre a GTEX
A pesquisa genérica não confirma:
- protocolo realmente configurado;
- IP/máscara;
- KGR carregado;
- Host File efetivo;
- mapa real das variáveis;
- assemblies/registers/offsets;
- datatype/scale/endianness;
- quantidade de conexões aceitas;
- versão efetiva do software do KCM;
- destino do cabo verde;
- semântica de status brutos não documentados.
Esses itens permanecem `UNKNOWN` até evidência de campo ou documento específico.
# 5. ESTADO ATUAL DO SOFTWARE
O projeto já existe e não deve ser reescrito do zero.
## 5.1 Etapa 1 — núcleo
Validada em execução real do software local:
- arquitetura read-only;
- `KcmDriver` sem operação de escrita;
- simulador WBF;
- tags semânticas;
- qualidades `SIMULATED`, `GOOD`, `UNCERTAIN`, `STALE`, `COMM_ERROR`, `BAD`;
- historian SQLite;
- API FastAPI;
- CLI;
- cenários simulados;
- eventos básicos.
Em validação manual foram observados cenários `ENCODER_FAILURE` e `BELTLOAD_LOW`, com historian e eventos funcionando.
## 5.2 Etapa 2 — inteligência determinística
Fechada. Ajustes implementados incluem:
- persistência de `summary` do evento;
- seção consolidada `sources`;
- `forja diagnose --json` como contrato oficial;
- `diagnosis_schema_version: "1.0"`;
- nível de evidência por hipótese/verificação/fonte;
- `evidence_summary` com indicação do elo mais fraco;
- regra estrutural que impede promoção indevida de evidência;
- diagnóstico determinístico, sem IA decidindo causa.
Referências de commits informadas no projeto:
- `b77603f` — correções de Etapa 2;
- `e6aec44` — contrato JSON/evidence;
- `ddd7a25` — UI da Etapa 3.
## 5.3 Etapa 3 — UI
UI já levantada com:
- quatro telas principais;
- FastAPI servindo a interface;
- sem CDN;
- sem fontes remotas;
- gráficos locais em SVG;
- responsividade validada em 375 px, tablet e desktop;
- claro/escuro;
- testes Playwright identificando bugs reais de navegação/layout;
- 135 testes e lint limpo no momento reportado.
Pendências principais da Etapa 3:
- drivers reais Modbus TCP e EtherNet/IP;
- kit/assistente de descoberta de campo passivo;
- evolução para múltiplos KCMs;
- aprofundamento visual/UX e visualização animada do dosador.
# 6. ALVO INICIAL — GTEX / PHA / PÓ BASE
Contexto inicial do produto:
Planta: GTEX Itupeva/SP
Linha/Área: PHA
Equipamento: Dosador Pó Base
Aplicação: WBF
Controlador: KCM/K-Tron
## 6.1 Evidências fotográficas já recuperadas
- aplicação WBF confirmada em tela/fotos;
- módulo Anybus-S observado instalado em `J3 HOST`;
- porta RJ45 visível e já ocupada por cabo verde;
- K-PROM visível;
- etiqueta/indicação `Ver 2.5` foi observada na CPU/EPROM, mas não deve ser tratada como versão global confirmada;
- confirmar versão em menu de software do KCM (`SYSTEM → SW VERSIONS` ou equivalente real).
## 6.2 Alarme observado
Na aplicação WBF fotografada da GTEX:
56 = BELTLOAD LOW
Isso não é universal. O código 56 pode ter outro significado em outra aplicação/configuração.
## 6.3 Valores de simulação usados como referência de UX
Para o simulador WBF do Pó Base:
Setpoint de referência: 1300 kg/h
VOL BELTLOAD de referência: 2,0 kg/m
São referências do cenário simulado/contexto estudado, não limites universais do KCM.
# 7. CASO DE CAMPO GTEX — CONHECIMENTO QUE DEVE ENTRAR NA BIBLIOTECA
Atendimento realizado aproximadamente entre 11 e 13/09/2026 na linha PHA, dosador Pó Base.
## 7.1 Situação observada
- linha parada por período relevante;
- relato de falha de encoder;
- alarme 56 `BELTLOAD LOW` observado;
- conjunto/esteira chegou a girar fisicamente com RPM indicada em 0;
- operação local pelo KCM chegou a funcionar em contexto em que o automático/supervisório parava;
- cadeia elétrica/mecânica exigiu investigação.
## 7.2 Intervenções observadas/referidas
- conector/cabo da célula de carga reparado;
- encoder substituído;
- intervenções de cabos/conectores;
- emenda direta associada à rota MDU/Scale em contexto de campo;
- continuidade elétrica verificada em trechos;
- calibração/validação realizada posteriormente.
## 7.3 Medições/referências de campo
- alimentação de encoder medida aproximadamente em 4,9 V em contexto do atendimento;
- MDU STATUS observado como `0046`, `2006` e `2046` em momentos distintos;
- SFT/statuses devem permanecer crus até decoder baseado em fonte correta;
- referência de gap da ordem de `0,125 mm` apareceu no contexto estudado, mas não é valor universal para qualquer sensor/montagem;
- `PICK UP TEETH` deve refletir dentes/PPR reais da instalação; referências históricas como 120/400 não podem ser aplicadas genericamente.
## 7.4 Calibração/validação reportada
Foram registrados valores como:
- tara/zero estático aproximado: `0,7447 kg / 0,0001 kg`;
- correlação de calibração aproximada: `98,9–99,4%`;
- validações comparando indicação KCM com referência externa, dentro da tolerância de processo informada no atendimento.
Isso deve ser tratado como validação de processo/serviço de campo, não como certificação metrológica.
## 7.5 Regra de diagnóstico aprendida
Uma ocorrência particularmente importante foi:
Máquina/conjunto com movimento físico
+
Drive Command presente
+
RPM indicada = 0
Isso é compatível com problema na cadeia de feedback de velocidade, mas não confirma automaticamente encoder queimado.
Sequência de verificação recomendada:
movimento físico?
→ alimentação do sensor
→ sinal/frequência na origem
→ cabo/conector
→ gap/alinhamento
→ interface/SIB se aplicável
→ entrada do KCM
→ configuração/PICK UP TEETH
A causa confirmada do caso estruturado deve permanecer `UNKNOWN` enquanto não houver evidência fechando a cadeia causal.
# 8. CONCEITOS DE DOMÍNIO KCM IMPORTANTES
O produto deve conhecer semanticamente, sem pressupor que todos estejam expostos pelo Host:
- K-Port 1 / K-Port 2;
- Host/Anybus;
- K-PROM;
- KGR;
- K-Link;
- KSU/KSC/K-Vision quando relevantes ao documento correto;
- MDU;
- SFT;
- Scale/SIB;
- encoder/speed pickup;
- Drive Command;
- Mass Flow;
- Setpoint;
- Net/Gross Weight;
- Belt Load;
- Feed Factor;
- control mode gravimétrico/volumétrico;
- Tare/Span;
- Calibration Correlation;
- STOP BY;
- INT CHANNEL;
- PICK UP TEETH;
- alarm/history.
## 8.1 WBF
No WBF, o conceito de vazão envolve a relação entre carga de correia e velocidade. O simulador pode trabalhar com uma aproximação física simples:
Mass Flow ≈ Belt Load × Belt Speed
Não tentar reproduzir internamente o algoritmo proprietário do KCM.
REFILL não pertence ao simulador WBF alvo. Não misturar lógica de LWF no Pó Base WBF.
# 9. ALARMES E STATUS — NÃO UNIVERSALIZAR
Exemplos estudados em documentação/contexto, sempre dependentes de aplicação/firmware:
06  WT PROC FAILURE
07  INCORRECT NUM SFT
08  BAD SFT STATUS
09  NO MDU FOUND
13  MDU SPEED DEV
16  MDU NO ENCODER
17  MDU I/O FAULT
39  EXT_IO_FAIL
43  MassFlow High
44  MassFlow Low
45  Drive Command Ceiling
46  Drive Command High
47  Drive Command Low
56  BELTLOAD LOW  (observado na aplicação WBF da GTEX)
O catálogo de alarmes deve usar chave composta, por exemplo:
controller + application + software/firmware + code
Nunca criar `56 = BELTLOAD LOW` como verdade universal.
## 9.1 STOP BY
STOP não significa automaticamente falha.
Classificar quando houver base para isso em:
- parada normal/solicitada;
- interlock;
- proteção;
- falha;
- calibração/procedimento.
Referências estudadas incluem termos como:
`Board Reset`, `Loc Display`, `Ext Display`, `ALS Input`, `DginRunEna`, `Stop Input`, `MDU DrvEna`, `Zero SP`, `Emptying`, `Interlock`, `Calib`, `Tare`, `FeedFactBad`, `MDUInterlock`, `MDU Alarm`.
Não inventar significado de bit/status sem fonte adequada.
# 10. COMUNICAÇÃO — O MAIOR RISCO TÉCNICO ATUAL
## 10.1 O que sabemos
- existe módulo Anybus-S no `J3 HOST`;
- existe RJ45 já utilizado;
- o cabo verde deve ter seu destino identificado;
- o produto deseja ler diretamente a interface Host/Anybus;
- a leitura real precisa coexistir com a arquitetura atual sem interferência.
## 10.2 O que NÃO sabemos ainda
- protocolo efetivamente configurado;
- IP/máscara/node;
- KGR carregado e nome;
- Host File;
- mapa de dados exposto;
- mecanismo exato de leitura;
- limite de conexões simultâneas;
- se existe sessão `Exclusive Owner` ou equivalente no protocolo atual;
- assemblies/registers reais;
- escala e endianness.
## 10.3 Possíveis protocolos
Dependendo da configuração/hardware, o universo KCM/Host pode envolver protocolos como:
- EtherNet/IP;
- Modbus TCP;
- Modbus RTU;
- PROFIBUS DP;
- PROFINET;
- DeviceNet;
- AB-DF1;
- outros conforme hardware/firmware.
A presença de RJ45 não confirma EtherNet/IP.
## 10.4 Não confundir K-Port 2 com Host
Referências de Modbus associadas a K-Port 2/WAGO não provam que o Host do KCM esteja em Modbus. O produto deve separar claramente:
- comunicação I/O auxiliar;
- interface Host;
- protocolo efetivamente carregado no Anybus.
# 11. TOPOLOGIA DE REDE E CABO RJ45
O fato de o RJ45 do Anybus já estar ocupado não impede o Forja de funcionar.
Cenário desejado, se a rede/protocolo permitirem:
KCM / Anybus
    │
    └── cabo existente
          ↓
        SWITCH
        ├── sistema atual
        └── Forja Edge
O Forja entra na mesma rede, não precisa obrigatoriamente de uma segunda porta física no KCM.
Se hoje houver conexão ponto a ponto direta, a topologia precisa ser levantada antes de qualquer alteração.
Não usar divisor passivo de RJ45.
Não inserir switch em comunicação industrial funcionando sem planejamento e autorização.
# 12. DESCOBERTA DE CAMPO
O sistema deve chegar à fábrica funcional em modo simulado e permitir configurar a comunicação real sem edição de código.
## 12.1 Ordem preferida
1. fotografar e identificar hardware sem desconectar nada;
2. confirmar aplicação e versão;
3. identificar Anybus/part number;
4. identificar IP/máscara e Host File/KGR;
5. seguir o cabo verde e levantar topologia;
6. preferir observação passiva;
7. se necessário e autorizado, executar teste ativo mínimo e direcionado;
8. comparar valores lidos com a tela real do KCM;
9. somente após validação marcar mapping como confirmado.
## 12.2 Captura passiva
Estar conectado a uma porta qualquer do mesmo switch não garante enxergar tráfego unicast existente.
Para observar tráfego entre KCM e peer existente, pode ser necessário:
- SPAN/mirror port;
- TAP de rede apropriado.
Não concluir “não existe comunicação” apenas porque uma captura em porta comum não mostrou pacotes.
## 12.3 Critério de validação
Uma conexão só deve ser considerada útil quando valores reais forem comparados com a tela/estado do KCM.
Exemplo:
Tag             KCM real       Forja       Validado
Setpoint         1300           1300        sim
Mass Flow        1287           1287        sim
Drive Command    41,8%          41,8%       sim
RPM              62             62          sim
Belt Load        2,01 kg/m      2,01 kg/m   sim
Antes da confirmação: `UNCERTAIN`.
Depois de validação rastreável: `GOOD`.
# 13. DRIVER REGISTRY E MAPEAMENTO EXTERNO
A comunicação deve ser plugável.
DriverRegistry
 ├── SimulatorDriver
 ├── ModbusTCPDriver
 ├── EtherNetIPDriver
 └── futuros drivers
Contrato conceitual:
connect()
disconnect()
read()
health()
capabilities()
Sem `write()`.
## 13.1 Mapping fora do código
Nada específico da máquina deve ficar hardcoded no driver.
Exemplo conceitual:
equipment:
  id: GTEX_PHA_PO_BASE
  application: WBF

communication:
  driver: ethernet_ip
  ip: UNKNOWN

mapping:
  setpoint:
    address: UNKNOWN
    datatype: UNKNOWN
    scale: UNKNOWN
    endianness: UNKNOWN
    confirmed: false
Assembly 100/150, registers, offsets ou qualquer endereço só podem existir como configuração/documentação, nunca como verdade fixa do driver.
# 14. MULTI-EQUIPMENT — UM SISTEMA, VÁRIOS KCMs
O produto deve evoluir de:
1 Edge → 1 Driver → 1 Equipment
para:
Forja Edge
   ├── Equipment Manager
   │     ├── Pó Base  → Driver 1
   │     ├── Barrilha → Driver 2
   │     └── KCM 03   → Driver 3
   ├── Historian
   ├── Events
   ├── Diagnostics
   └── UI
Cada equipamento possui seu próprio:
- `equipment_id`;
- nome/planta/área/linha;
- aplicação;
- controlador;
- protocolo;
- configuração de conexão;
- mapping;
- baseline;
- histórico;
- eventos;
- diagnósticos.
Falha de um KCM não pode interromper aquisição dos demais.
# 15. MODELO DE DADOS E QUALIDADE
## 15.1 Hierarquia
Plant → Area → Line → Equipment → Controller / Components
Exemplo:
GTEX → PHA → Dosador_Po_Base_01
## 15.2 Semantic Tags
Exemplos:
- `machine_state`
- `setpoint`
- `mass_flow`
- `drive_command`
- `rpm`
- `belt_load`
- `net_weight`
- `gross_weight`
- `alarm_code`
- `alarm_active`
- `stop_by`
- `sft_status`
- `mdu_status`
- `int_channel_pct`
- `control_mode`
- `tare`
- `span`
- `cal_correlation`
O vocabulário semântico é independente de protocolo.
## 15.3 Qualidade
- `GOOD`: leitura validada e confiável no mapping atual;
- `SIMULATED`: dado do simulador;
- `UNCERTAIN`: leitura não validada/mapping não confirmado;
- `COMM_ERROR`: tentativa atual de leitura falhou;
- `STALE`: último valor conhecido está velho;
- `BAD`: valor inválido por regra de qualidade definida.
Nunca confundir `COMM_ERROR` com `STALE`.
# 16. HISTORIAN
SQLite local continua adequado ao Edge inicial.
Cada amostra deve preservar no mínimo:
timestamp
plant
area
line
equipment
tag
value
quality
source
O projeto deve prever:
- índices;
- retention policy;
- cleanup/compactação;
- backup;
- downsampling para gráficos;
- migração futura para PostgreSQL/TimescaleDB sem quebrar domínio.
Nunca renderizar dezenas de milhares de pontos brutos diretamente na UI.
# 17. EVENTOS E DIAGNÓSTICO DETERMINÍSTICO
A inteligência principal deve nascer de regras determinísticas e contexto temporal, antes de IA.
Fluxo:
Sample
  ↓
Rule Engine
  ↓
Event
  ↓
Contexto anterior/durante
  ↓
Biblioteca de diagnóstico
  ↓
Hipóteses + verificações + fontes
Todo evento relevante deve capturar janela anterior para responder:
- o que mudou primeiro?
- o que aconteceu antes do alarme?
- quais variáveis reagiram?
- o comportamento já ocorreu antes?
## 17.1 Formato oficial do diagnóstico
RESUMO
EVIDÊNCIAS
O QUE MUDOU
HIPÓTESES
PRÓXIMAS VERIFICAÇÕES
FONTES
RESSALVAS
Internamente pode existir `RATE_DEVIATION`, mas a UI deve mostrar “Vazão abaixo do esperado”.
Internamente pode existir `SPEED_FEEDBACK_ANOMALY`, mas a UI deve mostrar “Leitura de velocidade inconsistente”.
## 17.2 Correlação não é causa
Nunca escrever:
“Causa: encoder queimado.”
sem prova.
Preferir:
“Comportamento compatível com possível problema na cadeia de feedback de velocidade.”
# 18. REGRAS/EXEMPLOS DE DIAGNÓSTICO
## 18.1 Belt Load baixo
Comportamento possível:
Belt Load ↓
Drive Command ↑
Mass Flow inicialmente preservada
Interpretação adequada:
O controlador está exigindo mais comando para compensar menor carga sobre a correia.
Hipóteses devem ser separadas de evidência. Alimentação a montante, cadeia de medição de carga e problemas mecânicos podem ser hipóteses, não causas confirmadas.
## 18.2 Feedback de velocidade
RUN
Drive Command > 0
RPM = 0
Pergunta principal:
O conjunto está fisicamente girando?
Se gira, investigar cadeia de feedback.
Se não gira, investigar acionamento/habilitação/mecânica conforme evidência disponível.
## 18.3 Drive Command alto
Drive Command alto com Mass Flow baixo é compatível com problema de entrega/processo, mas não fecha causa. Gerar verificações, nunca conclusão única.
# 19. UI/UX — POSICIONAMENTO VISUAL
A interface não deve parecer um SCADA tradicional nem um painel administrativo genérico.
Referências de qualidade visual podem ser produtos industriais modernos, sem copiar design proprietário.
## 19.1 Estética
- industrial premium;
- dark mode como principal;
- grafite/preto/cinza metálico;
- acento laranja/cobre Forja;
- verde normal;
- âmbar atenção;
- vermelho crítico;
- ciano/azul comunicação/informação;
- tipografia legível;
- cards limpos;
- espaço visual;
- animações funcionais.
## 19.2 Sidebar
Estrutura desejada:
VISÃO DA PLANTA
Dashboard
Equipamentos

PROCESSO
Tempo Real
Tendências
Histórico

INTELIGÊNCIA
Alertas
Eventos
Diagnósticos
Early Warning
Casos anteriores

KCM
Alarmes
Comunicação
Ficha técnica
Componentes

CONHECIMENTO
Manuais
Documentos
Casos de campo

FERRAMENTAS
Simulador
Relatórios
Exportações

SISTEMA
Configurações
Backup
Logs
Sobre
Sidebar recolhível e animada.
No header, seletor rápido de equipamento:
[ Pó Base ▼ ]
## 19.3 Linguagem
O usuário industrial não deve precisar entender inglês interno.
Evitar como título principal:
- `RATE_DEVIATION`
- `BELT_LOAD_LOW`
- `SPEED_FEEDBACK_ANOMALY`
Usar:
- Vazão abaixo do esperado;
- Pouco material sobre a correia;
- Leitura de velocidade inconsistente.
Código técnico pode aparecer em “Detalhes técnicos”.
# 20. VISÃO DA PLANTA
Tela inicial orientada a manutenção/engenharia:
GTEX — PHA

Pó Base
● Normal
WBF
Sem anomalias

Barrilha
⚠ Atenção
Comportamento fora do baseline

KCM 03
○ Sem comunicação
Cada card deve mostrar de forma resumida:
- estado;
- qualidade da comunicação;
- último evento;
- anomalia atual;
- última leitura;
- aplicação.
Clique abre o equipamento.
# 21. DASHBOARD DO EQUIPAMENTO
Não transformar em parede de gauges.
Cabeçalho:
Pó Base | WBF | KCM | ONLINE | 🔒 SOMENTE LEITURA
Indicadores essenciais:
- vazão atual e tendência;
- setpoint;
- Drive Command;
- RPM;
- Belt Load;
- INT Channel quando disponível;
- alarme/estado.
Bloco principal:
O QUE O SISTEMA ESTÁ VENDO
Exemplo normal:
Nenhuma alteração relevante detectada.
Exemplo anormal:
A carga sobre a correia está diminuindo enquanto o KCM aumenta o Drive Command para tentar manter a vazão.
# 22. COMPONENTE “O QUE MUDOU?”
Mais importante que um gráfico técnico complicado.
Exemplo:
BELT LOAD
Antes: 2,00 kg/m
Agora: 0,92 kg/m
↓ 54%

DRIVE COMMAND
Antes: 41%
Agora: 89%
↑ 48 pontos

MASS FLOW
Antes: 1302 kg/h
Agora: 1275 kg/h
↓ 2,1%
O usuário deve compreender o evento sem interpretar escalas complexas.
# 23. ANIMAÇÕES E INTERAÇÕES
O produto pode ter bastante movimento, mas sempre funcional.
Desejado:
- sidebar suave;
- cards entrando discretamente;
- números animados ao mudar;
- indicador online pulsando discretamente;
- transições de estado;
- timeline animada;
- alertas entrando suavemente;
- tooltips técnicos;
- gráficos com animação controlada;
- troca de equipamento suave;
- respeito a `prefers-reduced-motion`.
Evitar animações infantis, pesadas ou puramente decorativas.
# 24. VISUALIZAÇÃO ANIMADA DO WBF / DOSADOR
Criar visual local com SVG/Canvas/CSS.
Componentes:
SILO
 ↓ pó
ENTRADA
 ↓
CORREIA / SISTEMA DE PESAGEM
 ↓
SAÍDA
Elementos visuais:
- silo;
- alimentação;
- partículas de pó;
- correia;
- motor;
- encoder/sensor de velocidade;
- célula/Scale/SFT como abstração visual adequada;
- saída.
Comportamento:
- em RUN, correia move;
- partículas caem e acompanham a correia;
- velocidade visual reage a RPM/belt speed;
- quantidade de pó reage ao Belt Load;
- em BELTLOAD LOW, menos material na correia;
- em ENCODER_FAILURE, correia pode continuar visualmente em movimento enquanto RPM indicada cai a zero;
- em COMMUNICATION_FAILURE, congelar/atenuar e mostrar claramente que os dados são antigos.
A animação é representação explicativa, não gêmeo digital de alta fidelidade.
# 25. SIMULADOR
Manter os cenários:
- `NORMAL_OPERATION`
- `BELTLOAD_LOW`
- `RATE_LOW`
- `ENCODER_FAILURE`
- `SFT_FAILURE`
- `DRIVE_COMMAND_HIGH`
- `INT_CHANNEL_DEGRADED`
- `COMMUNICATION_FAILURE`
- `STOP_NORMAL`
Sem `REFILL` para WBF.
Adicionar modo avançado com controles manuais para:
- Setpoint;
- Mass Flow;
- Drive Command;
- RPM;
- Belt Load;
- Net Weight;
- INT Channel.
Sempre exibir banner discreto DADOS SIMULADOS.
# 26. MÓDULO COMUNICAÇÃO
O objetivo é permitir que a descoberta em campo vire configuração do sistema, sem VS Code.
Sidebar: COMUNICAÇÃO.
Subtelas:
- Visão geral;
- Configurar equipamento;
- Assistente de descoberta;
- Testar conexão;
- Mapeamento de tags;
- Qualidade da comunicação;
- Log técnico.
## 26.1 Estados de suporte de driver
- `AVAILABLE`
- `EXPERIMENTAL`
- `NEEDS_CONFIGURATION`
- `UNSUPPORTED`
Nunca mostrar protocolo como suportado se não existir driver funcional.
## 26.2 Wizard de descoberta
### Etapa 1 — identificação
- fabricante;
- controlador;
- aplicação;
- modelo/código Anybus;
- versão KCM;
- Host File;
- KGR.
Todos aceitam `UNKNOWN`.
### Etapa 2 — rede
- IP;
- máscara;
- gateway;
- porta quando aplicável;
- MAC se conhecido.
### Etapa 3 — protocolo
- EtherNet/IP;
- Modbus TCP;
- Outro/desconhecido.
### Etapa 4 — teste
Botão:
TESTAR SOMENTE LEITURA
Estados:
- conectando;
- handshake/sessão;
- conectado;
- timeout;
- falha;
- não identificado.
Nunca testar escrita.
### Etapa 5 — validação
Tabela de comparação com valor lido e valor observado no KCM. Usuário confirma manualmente.
# 27. EDITOR DE MAPPING
Permitir edição segura via UI:
Tag semântica
Address
Datatype
Scale
Endian
Quality
Validado?
Fonte
Importar/exportar YAML/JSON.
Validar schema antes de salvar.
Mudanças de mapping devem entrar no audit log.
# 28. EARLY WARNING E BASELINE
Criar módulo `Early Warning`, mas não vender como previsão milagrosa.
Objetivo:
identificar comportamento diferente do padrão antes de um evento grave, quando existir histórico suficiente.
Exemplos de sinais:
- Drive Command subindo progressivamente com vazão semelhante;
- Belt Load caindo e Drive Command subindo;
- RPM intermitente;
- COMM_ERROR recorrente;
- mudança persistente em relação ao baseline.
Não escrever:
“Falha acontecerá em 3 horas.”
Preferir:
“Comportamento diferente do histórico; recomenda-se investigação.”
Baseline deve considerar:
- equipamento;
- produto;
- modo de operação;
- faixa de setpoint.
Não comparar produtos/condições incompatíveis.
# 29. DOCUMENTOS, CASOS E RAG
Criar biblioteca local de conhecimento.
Categorias:
- manual do fabricante;
- manual da máquina;
- procedimento;
- relatório técnico;
- caso de campo;
- foto;
- diagrama;
- configuração.
Entidades desejadas:
- `Document`
- `DocumentChunk`
- `SourceReference`
- `Case`
- `Intervention`
- `CalibrationRecord`
Hierarquia de fonte para RAG/diagnóstico:
1. manual oficial correto;
2. documentação específica da máquina/AS-BUILT;
3. procedimento aprovado;
4. medição/caso confirmado;
5. relatório histórico;
6. inferência técnica.
IA deve devolver:
Resumo
Evidências
Hipóteses
Próximas verificações
Fontes
# 30. IA / COPILOT
IA é opcional e posterior ao núcleo determinístico.
Provider abstrato:
- `none`
- `local`
- `cloud`
Com `none`, o produto deve continuar operacional.
A IA pode:
- explicar diagnóstico;
- resumir ocorrência;
- buscar documentação;
- comparar casos;
- responder perguntas técnicas com fontes.
A IA nunca pode:
- comandar KCM;
- contornar proteção;
- transformar hipótese em certeza;
- inventar parâmetro/registro/limite.
# 31. OFFLINE-FIRST E WINDOWS
O produto deve funcionar sem internet.
Proibido depender de:
- CDN;
- Google Fonts;
- scripts remotos;
- API externa para telas essenciais.
Objetivo de entrega:
ForjaKCM.exe
ou instalador Windows.
Em produção, preferir serviço Windows/Edge que:
- inicia com o sistema;
- coleta 24/7 mesmo com navegador fechado;
- reconecta automaticamente;
- preserva logs;
- mantém historian local.
UI pode abrir via localhost.
# 32. RESILIÊNCIA
Implementar:
- watchdog;
- reconnect policy;
- backoff;
- isolamento de falha por equipamento;
- health endpoint;
- recuperação após reinício.
Se comunicação cair:
COMM_ERROR na tentativa atual
+
STALE nos últimos valores mantidos
Nunca mostrar último valor como se fosse atual.
# 33. SAÚDE, LOGS, BACKUP E AUDITORIA
## Saúde
Mostrar:
- uptime;
- driver;
- conexão;
- última leitura;
- latência;
- erros/reconexões;
- historian;
- tamanho DB;
- samples/min;
- event engine;
- espaço em disco.
## Logs
Separar:
- Application Log;
- Communication Log;
- Event Log;
- Audit Log.
## Backup
Incluir:
- banco;
- configs;
- mappings;
- perfis de equipamentos;
- biblioteca de diagnóstico;
- casos.
Funções:
- backup agora;
- backup automático;
- restaurar.
## Usuários locais
- `ADMIN`
- `MAINTENANCE`
- `VIEWER`
Nenhum perfil recebe capacidade de comandar KCM.
# 34. RELATÓRIOS E EXPORTAÇÃO
Permitir:
- relatório de diagnóstico;
- relatório de evento;
- relatório de equipamento;
- relatório de comunicação;
- relatório diário;
- impressão;
- PDF;
- CSV de tendências;
- JSON técnico.
Relatório de diagnóstico deve incluir:
- equipamento;
- data;
- evento;
- gráficos/contexto;
- evidências;
- hipóteses;
- verificações;
- fontes;
- ressalvas;
- observações/responsável.
# 35. SEGURANÇA INDUSTRIAL
Regras inegociáveis:
- read-only por construção;
- sem bypass/jumper de proteção;
- sem instrução para trabalho energizado fora de procedimento;
- sem exposição direta do KCM à internet;
- menor privilégio;
- acesso/configuração auditável;
- qualquer teste ativo de campo exige autorização da planta.
# 36. IMPLEMENTAÇÃO DE DRIVERS REAIS
## 36.1 Modbus TCP
Driver genérico e read-only.
Mapping externo define:
- área/função de leitura;
- address;
- count;
- datatype;
- endianness;
- scale.
Sem addresses fixos.
## 36.2 EtherNet/IP
Driver genérico e read-only.
Pesquisar e decidir biblioteca com base na versão Python/projeto e compatibilidade real. Candidatas históricas: `pycomm3`, `cpppo` ou outra tecnicamente melhor.
Não hardcode Assembly 100/150. Se documentos referenciarem esses números, mantê-los como mapping/documentação, não como regra universal.
Considerar coexistência com possíveis conexões existentes e limitações de ownership/sessão.
# 37. INTERFACE DE CONFIGURAÇÃO SEM CÓDIGO
Objetivo fundamental:
adicionar ou ajustar um KCM após instalação sem abrir VS Code.
Fluxo desejado:
+ ADICIONAR EQUIPAMENTO
  ↓
Nome
Planta
Área
Linha
Aplicação
Driver
Rede
Mapping
Tags
Validação
Salvar
Depois, equipamento aparece no seletor da UI.
# 38. CRITÉRIO DE ACEITE VISUAL
A UI não pode parecer:
- template Bootstrap;
- painel admin genérico;
- dashboard financeiro;
- SCADA antigo;
- protótipo acadêmico.
Deve parecer um produto industrial premium de 2026, claramente desenvolvido para manutenção/diagnóstico de equipamentos.
# 39. CRITÉRIO DE ACEITE FUNCIONAL
Em modo simulado, deve ser possível:
1. iniciar o aplicativo;
2. abrir visão da planta;
3. selecionar Pó Base;
4. observar WBF animado;
5. selecionar `BELTLOAD_LOW`;
6. visualizar menos pó na correia;
7. visualizar Drive Command subindo;
8. detectar anomalia;
9. abrir diagnóstico;
10. compreender sem inglês técnico;
11. ver evidências;
12. ver verificações;
13. ver fontes;
14. imprimir diagnóstico;
15. abrir Comunicação;
16. criar equipamento;
17. escolher Simulator / Modbus TCP / EtherNet/IP conforme disponibilidade real;
18. configurar conexão;
19. testar somente leitura;
20. configurar mapping;
21. validar tags;
22. salvar equipamento;
23. consultar historian;
24. alternar entre vários equipamentos.
Toda ação visível deve funcionar ou aparecer claramente como indisponível/pendente de configuração. Não criar botão falso.
# 40. PLANO DE IMPLEMENTAÇÃO RECOMENDADO
Fases sugeridas:
A  Auditoria completa do repositório atual
B  Design system + shell + sidebar + equipment selector
C  Visão da planta + dashboard
D  Visualização animada WBF
E  Tendências + timeline
F  Diagnóstico UX
G  Communication Center + wizard
H  Multi-equipment
I  Abstrações finais de driver real
J  Modbus TCP
K  EtherNet/IP
L  Health / reconnect / logging
M  Reports / backup
N  Packaging Windows / serviço
O  Campo GTEX
P  Pós-campo: mapping real, ajustes, baseline e RAG
Não avançar de fase com testes falhando.
# 41. PENDÊNCIAS DE CAMPO QUE DEVEM CONTINUAR UNKNOWN
Até visita/evidência específica, manter `UNKNOWN`:
1. protocolo real do Anybus na GTEX;
2. part number exato/configuração do módulo;
3. IP/máscara/node;
4. KGR carregado;
5. Host File real;
6. addresses/registers/assemblies;
7. datatypes/scales/byte order;
8. mecanismo de leitura não interferente;
9. limite de conexões simultâneas;
10. versão global real do software KCM;
11. destino do cabo verde;
12. lista/semântica completa de alarmes da aplicação;
13. `PICK UP TEETH` real;
14. detalhes definitivos de SFT/MDU/SIB instalados;
15. decodificação de MDU/SFT statuses observados.
É melhor mostrar UNKNOWN do que preencher algo plausível sem prova.
# 42. FONTES LOCAIS QUE DEVEM ACOMPANHAR O REPOSITÓRIO
Criar estrutura recomendada:
docs/reference/
  originals/
  gtex/
  manuals/
  photos/
  derived/
Arquivos importantes já identificados na biblioteca do projeto:
- `Forja KCM Intelligence — Análise A–T (Arquitetura do MVP).pdf`
- `KCM-SMART-MANUAL.html`
- `Manual_Diagnostico_Encoder_Dosador_PHA_GTEX.pdf`
- `Manual_Ligacoes_KCM_GTEX_Forja_Logica.pdf` / `.md`
- relatórios técnicos GTEX WBF/KCM;
- guias técnicos GTEX de campo LWF/WBF;
- fotos do KCM, Anybus, Scale/SFT/MDU e ligações;
- diagramas disponíveis.
O Smart Manual e guias derivados são úteis, mas não substituem a fonte oficial/original quando houver conflito.
# 43. FONTES OFICIAIS JÁ CITADAS EM MATERIAL INTERNO
Materiais internos registram referência a documentos como:
- Coperion K-Tron KCM Hardware Instruction Manual 1090020601-EN, Rev. 1.2.1;
- Coperion K-Tron LWF Programming Manual 0590020601-EN, Rev. 1.8.0 para conceitos específicos de documentação estudada;
- páginas do KCM Hardware Manual relacionadas a SFT, J2, receptora diferencial, SIB/Scale e velocidade;
- documentação oficial Coperion de SFT Weighing Technology.
Ao utilizar essas referências, confirmar a aplicabilidade ao hardware/aplicação real antes de transformar em regra.
# 44. CONTEXTO HISTÓRICO DE PLC/SCADA — SOMENTE PARA ENTENDER A PLANTA
Documentos históricos da GTEX registram endereços e arquiteturas envolvendo Micro820/HMI/inversores em contextos LWF/WBF.
Essas informações podem ajudar a entender a topologia da planta, mas não devem puxar a arquitetura do Forja para o PLC.
Também existe contexto de upgrade D5/DF3102/GCM-K associado a outra arquitetura. Não usar isso como prova do protocolo do Pó Base KCM/Anybus.
# 45. PRINCÍPIO DE PRODUTO: NÃO DUPLICAR O SUPERVISÓRIO
Toda funcionalidade nova deve responder algo que o supervisório atual não responde claramente.
Perguntas do Forja:
- O que mudou?
- Quando começou?
- O que mudou primeiro?
- Houve sinal antes do alarme?
- Isso já aconteceu?
- Quais hipóteses são compatíveis?
- O que verificar primeiro?
- Qual evidência sustenta essa hipótese?
Se a funcionalidade só replica uma variável já exibida no supervisório sem adicionar contexto/diagnóstico, ela não é prioridade.
# 46. OBJETIVO ECONÔMICO E LIMITES DE PROMESSA
O produto busca ajudar a reduzir:
- MTTR;
- tempo de investigação;
- condições degradadas não percebidas;
- dependência de conhecimento informal;
- perda de histórico;
- repetição de diagnóstico do zero.
Existe contexto de impacto financeiro elevado associado à operação da linha/equipamento. Isso justifica a importância do problema, mas o software não pode prometer que teria evitado uma perda específica sem evidência histórica suficiente.
Mensagem correta:
reduzir o tempo entre o início de uma condição anormal, sua identificação e a intervenção técnica.
# 47. INSTRUÇÃO FINAL PARA O CLAUDE CODE
Ao receber este documento:
1. não codifique imediatamente;
2. faça auditoria do repositório;
3. compare estado atual com este documento;
4. identifique o que já está implementado;
5. identifique conflitos e lacunas;
6. proponha plano incremental;
7. preserve o que já foi testado;
8. implemente por fases;
9. rode testes/lint/Playwright após cada fase relevante;
10. mantenha read-only por construção;
11. mantenha tudo específico da GTEX como configuração até prova em campo;
12. nunca invente informação técnica para “fazer a tela parecer completa”.
Ao final de cada fase, reportar:
- o que foi alterado;
- arquivos afetados;
- testes executados;
- resultados;
- pendências `UNKNOWN`;
- próximo passo.
# 48. PROMPT DE INÍCIO RECOMENDADO
Use este texto junto deste documento ao abrir o Claude Code:
Leia integralmente `Forja_KCM_Intelligence_Documento_Mestre_Claude.md`, o README, o código atual, os testes e todos os arquivos em `docs/reference`. Não altere nada ainda. Faça primeiro uma auditoria do estado real do repositório e compare com o Documento Mestre. Classifique cada requisito como IMPLEMENTADO, PARCIAL, AUSENTE ou BLOQUEADO_POR_CAMPO. Liste riscos de regressão, decisões que precisam ser preservadas e pendências específicas da GTEX. Em seguida proponha um plano de implementação por fases. Não invente protocolo, mapping, register, assembly, status ou versão. Read-only é requisito estrutural. Só depois da minha aprovação comece a alterar código.
# 49. RESUMO EM UMA FRASE
Forja KCM Intelligence é um observador industrial read-only que lê o KCM diretamente quando tecnicamente possível, registra o comportamento da máquina e transforma dados, eventos, documentação e casos de campo em diagnóstico rastreável para a manutenção.