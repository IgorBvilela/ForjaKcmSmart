# Registros de decisão (ADR) — Forja KCM Intelligence

Decisões tomadas em 2026-09-30 na auditoria inicial (detalhe e motivos: `docs/auditoria/2026-09-30_auditoria_inicial.md`, seção 9). Status: aceitas, pendentes de aprovação formal do chefe. Mudar uma decisão = novo ADR numerado nesta pasta, nunca edição silenciosa.

| ADR | Decisão | Classificação |
|---|---|---|
| 0001 | Python 3.14 como alvo (`>=3.13,<3.15`); gate A0 provou instalação; cai para 3.13 via uv se faltar wheel | TECHNICAL_OPINION |
| 0002 | SQLite WAL em dois arquivos (`forja_core.db`, `forja_historian.db`); não MySQL no Edge | DECISÃO (motivo forte documentado) |
| 0003 | Read-only por construção em 8 camadas provadas por teste; driver só connect/disconnect/read/health/capabilities | FORJA_RULE |
| 0004 | SQL à mão atrás de repositórios + migrações numeradas com checksum; sem ORM | TECHNICAL_OPINION |
| 0005 | Banco é a fonte da verdade da configuração em runtime; YAML/JSON = semente, import/export, backup | TECHNICAL_OPINION |
| 0006 | STALE é estado derivado por relógio monotônico, nunca linha gravada; COMM_ERROR grava value NULL | FORJA_RULE |
| 0007 | pymodbus 3.15 embrulhado, `retries=0`, `reconnect_delay=0`; backoff só no supervisor | TECHNICAL_OPINION |
| 0008 | EtherNet/IP decidido na fase I com régua fixa (MIT/BSD/Apache sem dual, wheel puro, Get_Attribute_Single contra fake, escrita enumerada); só explícita na v1 | TECHNICAL_OPINION |
| 0009 | Serviço Windows com pywin32 + `sc.exe`; WinSW só se falhar duas vezes; PyInstaller onedir | TECHNICAL_OPINION |
| 0010 | Front Vite + Svelte 5 + TypeScript em `/app`, build estático servido pelo FastAPI, zero CDN (pendente: Node aprovado pelo chefe) | TECHNICAL_OPINION |
| 0011 | uPlot para gráficos com eixo; SVG próprio para sparkline, timeline e dosador; GAP nunca interpolado | TECHNICAL_OPINION |
| 0012 | SSE: um stream por aba, heartbeat 5 s, Last-Event-ID, snapshot antes; rótulos pt-BR vêm do backend | TECHNICAL_OPINION |
| 0013 | Tokens de design da Shuri como única fonte; IBM Plex Sans/Mono (OFL) vendorizadas; cobre nunca é status; lilás só SIMULADO | TECHNICAL_OPINION |
| 0014 | scrypt da stdlib para senha; sessão no servidor; audit log append-only com cadeia de hash | TECHNICAL_OPINION |
| 0015 | Playwright em Python, um runner; mypy; `tools/check.py` + hook git nativo, zero rede | TECHNICAL_OPINION |
| 0016 | Diagnóstico JSON v1.0 com 7 seções; hipótese "compatível com", nunca causa; sem promoção de evidência; ressalva obrigatória | FORJA_RULE |
| 0017 | Alarmes por chave composta; 56 = BELTLOAD LOW só como FIELD_OBSERVED da aplicação WBF da GTEX; 06–47 HYPOTHESIS | FORJA_RULE |
| 0018 | STOP BY: enum da spec §36; Calib/Tare UNKNOWN "candidato a PROCEDURE" (decisão do chefe) | FORJA_RULE |
| 0019 | Código anterior não localizado: nascer limpo (A1) com porta de reconciliação; o 1.0 dele vence se aparecer | DECISÃO |
| 0020 | Gráfico de tendência em degrau (cada ponto vale até a próxima linha gravada, coerente com store-on-change); nunca reta entre leituras | FORJA_RULE |
| 0021 | Partida da coleta grava marca `COMM_ERROR` sem valor 1 ms após a última leitura observada quando houve pausa: trecho sem coleta vira buraco | FORJA_RULE |
| 0022 | Análise de janela ("o que mudou") usa o padrão do início da janela como ANTES; eventos seguem com a mediana pré-saída | TECHNICAL_OPINION |
| 0023 | Instalação Windows: programa em `Program Files` trocado inteiro (em etapas, com volta), dados em `ProgramData` nunca apagados, `FORJA_HOME` no ambiente do serviço, conta LocalService, pasta de dados só gravável por Administradores e pelo serviço, backup antes de toda atualização, pacote sempre fora do modo desenvolvimento (contrato: `docs/contracts/CONTRATOS_N.md`) | TECHNICAL_OPINION |
| 0024 | Perfil e mapping editáveis ficam em YAML em `config/equipment` e `config/mappings`, gravados pela Central de Comunicação: validação pelo domínio antes do disco, troca atômica, versão anterior intacta em `config/_history/`, conflito por hash do perfil e versão do mapping (409), auditoria em `audit_log` e recarga só do equipamento afetado; o banco não guarda configuração. Revisa a 0005 (contrato: `docs/contracts/CONTRATOS_G.md`) | TECHNICAL_OPINION |
| 0025 | EtherNet/IP lido por cliente CIP mínimo próprio, só com a biblioteca padrão (`src/forja/drivers/ethernet_ip/_client.py`): mensagem explícita não conectada, sem Forward_Open (não disputa a posse das saídas), listas fechadas de comandos (0x63, 0x65, 0x66, 0x6F) e serviços (0x01, 0x0E) conferidas antes de montar bytes; fecha a 0008 sem dependência externa (pycomm3 sem desenvolvimento ativo e declarado até Python 3.10; cpppo com licença dual GPL); EXPERIMENTAL até validação no KCM real (contrato: `docs/contracts/CONTRATOS_J_K.md`) | TECHNICAL_OPINION |
| 0026 | Coleta de driver real (`modbus_tcp`, `ethernet_ip`) só liga depois de teste somente leitura bem-sucedido, registrado em `read_tests` (append-only), com o mesmo fingerprint da configuração salva (sha256 de driver, endereço, tempos, opções e entradas do mapping); gravar configuração nunca liga a coleta e mudança que altera o fingerprint pausa a coleta; a regra vale na API e na partida/recarga do serviço, também para YAML editado à mão, e falha na conferência bloqueia (contrato: `docs/contracts/CONTRATOS_G.md`) | FORJA_RULE |
| 0027 | Aviso antecipado é regra determinística configurável (`config/early_warning`): tendência por reta com R² mínimo, desvio e estabilidade em relação ao padrão do próprio equipamento, proximidade da referência e estado, combinados por AND, com persistência para abrir e para encerrar; vira evento de origem `EARLY_WARNING`, nunca alarme do KCM e nunca previsão; dados insuficientes não abrem nem encerram (contrato: `docs/contracts/CONTRATOS_F.md`) | FORJA_RULE |
| 0028 | Equipamento não é apagado: arquivar move o perfil para `config/_archive` e o tira da memória, o histórico fica no banco, restaurar devolve; a semente não recria perfil arquivado numa atualização; equipamento novo nasce com protocolo não identificado e coleta desligada (contrato: `docs/contracts/CONTRATOS_H.md`) | TECHNICAL_OPINION |
| 0029 | Backup leva os bancos e a configuração (zip verificado contra caminho fora de `config/`/`knowledge/`), roda todo dia no horário de `backup.schedule` no fuso da planta e guarda só `keep_last`; restaurar segue na linha de comando com o serviço parado e guarda a configuração atual antes (contrato: `docs/contracts/CONTRATOS_M.md`) | TECHNICAL_OPINION |
| 0030 | Sem login nesta versão: a interface escuta só em 127.0.0.1 e toda alteração pede o nome do responsável, que vai para a auditoria; usuários, senhas e permissões (ADR 0014) ficam para quando a interface for acessada de outra máquina | DECISÃO |
| 0031 | Cadeia de hash da trilha de auditoria (parte da 0014): tabela `audit_chain` append-only, um elo por registro gravado na mesma transação, hash = sha256(hash anterior + conteúdo canônico); conferência por `forja audit verify`, `GET /api/v1/system/audit/verify` e na aba Auditoria de Saúde e logs; registros anteriores ao encadeamento contados à parte (contrato: `docs/contracts/CONTRATOS_L.md`) | TECHNICAL_OPINION |
| 0032 | Tamanhos mínimos de texto pela regra de interface do produto: rótulo e selo em 13 px (podem ter número), legenda e número pequeno em 13 px, nada abaixo de 12 px; campo de marcar com 24 px; menu lateral com folga de rolagem para o contorno de foco aparecer inteiro. Conferido com a conferência visual em 375, 768 e 1440 px | FORJA_RULE |
