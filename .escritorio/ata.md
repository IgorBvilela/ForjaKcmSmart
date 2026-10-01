# Ata do escritório — Forja KCM Intelligence

Pasta: `C:\Users\ivilela\Documents\SIGNA-Q\FKI` · Aberta em: 2026-09-30

## Quem trabalha neste projeto
| Área | Pessoa |
|---|---|
| Entrega | Pepper |
| Arquitetura | Stark |
| Back-end e drivers | Sexta-feira |
| Banco (SQLite) | Karen |
| Design | Shuri |
| Front-end | Jarvis |
| Mobile | Mística (a partir da fase B) |
| Segurança | Verônica |
| Testes | Edith |
| Documentos | Uatu |
| Deploy/instalador | Dum-E (fase N) |
| QA chato | Ultron |

## Combinados permanentes
- Stack: Python 3.14 + FastAPI + Pydantic v2 + SQLite (2 arquivos, SQL à mão) + SSE; front Vite + Svelte 5 (pendente confirmação do chefe sobre Node); serviço Windows com pywin32 + sc.exe; PyInstaller onedir.
- Banco: SQLite embutido em `var/forja_core.db` e `var/forja_historian.db` (dev). Não é MySQL: o Edge é serviço offline único no PC da planta; motivo registrado na auditoria.
- Padrões: read-only por construção; UNKNOWN literal; textos `*_pt`; relógio injetável; tempo em UTC epoch ms no banco; sem rede em teste; git só local.
- Hospedagem: não se aplica (software local, instalador Windows na fase N). Deploy é do chefe.
- Contrato entre módulos: `docs/contracts/CONTRATOS_A1.md`. Decisões: `docs/auditoria/2026-09-30_auditoria_inicial.md` (seção 9).

## Não fazer
- PLC ou SCADA como fonte ou fallback (regra absoluta do produto).
- Qualquer função de escrita no KCM, mesmo "desligada por configuração".
- Hardcode de IP, register, assembly (100/150), KGR, bits de MDU/SFT, alarmes universais, thresholds da GTEX.
- Decodificar MDU/SFT/STOP BY sem documento do modelo e revisão.
- Marcar driver AVAILABLE sem driver funcional validado.
- CDN, Google Fonts, script remoto, telemetria.
- Microserviços, Docker, broker, ORM, PostgreSQL agora, IA/RAG real agora, predição.
- cpppo (licença dual GPL), NSSM (sem manutenção), pyapp (baixa Python em runtime).
- Publicar, enviar ou sincronizar qualquer coisa para fora da máquina.

## Pendências abertas
- [ ] Chefe: existe outra cópia do código das Etapas 1-3 (zip, outro PC, e-mail, claude.ai)? Pasta `Downloads\forja-kcm-etapa1` sumiu; transcrição permite recuperação parcial. (dono: chefe)
- [ ] Chefe: onde estão o `.md` original do Documento Mestre e os documentos do DM §42/§43? (dono: chefe)
- [ ] Chefe: Node/npm pode entrar no front (Vite + Svelte)? Programa em Vue/React? (dono: chefe, antes da fase B)
- [ ] Chefe: origem de 4,9 V, 0,125 mm e dos status SFT 00000183/00000181; documento dos alarmes 06–47 e termos STOP BY. (dono: chefe)
- [ ] Chefe: Calib/Tare como categoria PROCEDURE de STOP BY? (dono: chefe)
- [ ] Extrair os 23 arquivos recuperáveis da transcrição antiga para `docs/reference/derived/` (dono: Pepper, fase A1).
- [ ] ADRs 0001–0012 com as 23 decisões (dono: Stark, fase A1).

## Sessões

### 2026-09-30 — auditoria inicial e fundação
- **Convocados:** Uatu, Stark, Sexta-feira, Karen, Shuri, Jarvis, Verônica, Edith, verificador, Happy, Ultron.
- **Decidido:** auditar antes de codar (spec §0/§95); código anterior não localizado → nascer limpo com porta de reconciliação; 23 decisões técnicas fechadas (ver auditoria §9); fases A0..P.
- **Feito:** auditoria completa (`docs/auditoria/2026-09-30_auditoria_inicial.md`); matriz de 200 requisitos; 51 fontes verificadas; gate de ambiente A0 passou (Python 3.14.5, 14/14 imports, SQLite 3.50.4 com FTS5); git local iniciado; estrutura de pastas; domínio, config e infra escritos e testados por smoke (`src/forja/{domain,config,infra}`); sementes `config/forja.yaml`, 3 perfis, 2 mappings; contrato de integração `docs/contracts/CONTRATOS_A1.md`.
- **Ficou de fora:** código dos blocos 1–5 (em implementação pelo time), telas (fase B), drivers reais (J/K).
- **Ultron:** voltou porque o rastro do código estava na máquina, havia 8 bifurcações abertas e zero estimativa; corrigido antes da entrega (rastro verificado, decisões fechadas, estimativas dadas). Chefe reagiu: "a ideia era construir do zero" → aprovação implícita para nascer limpo; implementação iniciada.

### 2026-10-01 — fase A1: núcleo implementado
- **Convocados:** Sexta-feira (×3: drivers, eventos/diagnóstico, API/CLI), Karen (historian), Stark (aquisição/serviço); Pepper integrou.
- **Decidido:** retomar os 5 blocos interrompidos pela queda da sessão anterior, cada um terminando o que faltava e escrevendo testes; integração pela Pepper (não por agente).
- **Feito:** 5 blocos entregues e integrados; suíte inteira 528 testes verdes; ruff e mypy limpos em 85 arquivos; servidor real de pé com 3 simuladores (planta Normal/Sem comunicação, live SIMULATED com idade, COMM_ERROR honesto, drivers reais UNSUPPORTED, SSE snapshot+sample, CSP); `forja diagnose --json --demo BELTLOAD_LOW` gera diagnóstico v1.0 válido em português; `forja doctor` ok. Ajustes de integração: AlarmKey normaliza "06"="6"; Sample serializa bytes em base64; log de falha de leitura com rate-limit; `forja run` cai para a próxima porta livre se 8765 estiver ocupada (estava, por php.exe do chefe). 23 arquivos das Etapas 1-3 recuperados da transcrição para docs/reference/derived; ADRs 0001–0019 em docs/adr.
- **Ficou de fora:** telas (fase B); drivers Modbus/EtherNet/IP (J/K); `/docs` em modo dev usa assets do Swagger via CDN (só dev; decisão do chefe: manter ou vendorizar); Ctrl+C gracioso verificado por leitura, não por teste automatizado; `StopByClass.PROCEDURE` e `DiagnosisRepository.list` → `list_diagnoses` ficam para a próxima mudança de domínio.
- **Ultron:** não convocado nesta rodada (entrega técnica interna); entra antes da fase B ser mostrada ao chefe.

### 2026-10-01 — fases B, C e D: telas, dosador animado, simulador
- **Convocados:** Jarvis (×2: casca/planta/dashboard/eventos e dosador/simulador), Shuri (revisão de acabamento), Mística (auditoria 375/768/1024), Edith (38 testes de tela), Sexta-feira (textos do diagnóstico em português), Ultron (aceite §89 e reconferência); Pepper integrou.
- **Decidido:** stack do front Vite + Svelte 5 + TypeScript (chefe delegou: "não sei programar, quero algo bonito igual à foto"); referência visual do chefe guardada em docs/reference/design com o que NÃO entra (CLP como fonte, foto real, linguagem de causa, protocolo como botão); dashboard em 3 linhas (condição · 6 indicadores · dosador + linha do tempo); tokens da Shuri como única fonte; rótulos e chips do diagnóstico por título em português, ids só em "Detalhes técnicos"; horas em texto no fuso da planta (tzdata); discretas em palavras.
- **Feito:** shell com sidebar/drawer, header com seletor e selo Somente leitura, planta, dashboard, eventos e diagnóstico (7 seções), simulador com 9 cenários e sliders, dosador SVG animado com 3 níveis de traço e estados run/stop/sem sinal/sem comunicação, rotas futuras com estado honesto "Em desenvolvimento · próxima etapa", backend servindo /app; 38 testes e2e (Edge local, 4 tamanhos, zero requisição externa); suíte 572 + 38 verdes; Mística: zero scroll horizontal em 41 rotas × 3 tamanhos, alvos ≥ 44 px, drawer com foco preso; Ultron: 16 passos do aceite §89 medidos.
- **Ficou de fora:** Tendências/Histórico (E), Alertas/Early Warning/Casos (F), Comunicação/Alarmes/Ficha/Componentes (G), Logs (L), Relatórios/Backup/Usuários/Documentos (M); render de STALE e "Edge sem resposta" sem teste e2e (precisa injeção de falha); cenário "parada em operação" no simulador (STOP_NORMAL já nasce parado).
- **Ultron:** voltou (números crus, textos cortados, inglês fora de Detalhes técnicos) → corrigido; reconferência registrada abaixo.
- **Ultron (reconferência):** pontos 1 (números crus/hora UTC) e 2 (texto cortado/"ON") passaram; ponto 3 sobrou "config/rules/R-BELTLOAD-001.yaml" em Fontes → corrigido pela Pepper (referência técnica só em Detalhes técnicos) e verificado por leitura do DOM: nenhum código visível fora de Detalhes técnicos. Achado extra do Ultron virou correção de produto: eventos deixados em aberto por execução anterior passam a EXPIRED na partida, com nota em português ("Encerrado automaticamente: o Forja Edge foi reiniciado…"); se a condição persistir, a regra reabre. Verificado: 0 abertos após reinício, 1 reaberto em ~40 s na Barrilha.
- **Cutucadas registradas, não bloqueantes:** mesmo número com formatos diferentes lado a lado (75,4% × 75,41 %); "Edge" é nome que o mecânico não conhece (tooltip explica); "Early Warning" no menu é inglês (nome da spec §46; avaliar "Alerta antecipado").
- **Commits:** 1a5f233 (B/C/D), 6299185 (revisão Shuri/Mística), c05ba36 (e2e), 72e7a89 (acabamento Ultron), + fechamento desta sessão.
