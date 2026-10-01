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
