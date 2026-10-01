# Forja KCM Intelligence — regras do projeto

Kit ativo: fluxo `agent-skills:incremental-implementation` + `agent-skills:test-driven-development` · design `design-taste-frontend` + `dataviz` · UI/front `agent-skills:frontend-ui-engineering` · animações `genjutsu:cast` (só depois do shell parado) · API `agent-skills:api-and-interface-design` · back `agent-skills:source-driven-development` · segurança `agent-skills:security-and-hardening` · auditoria `agent-skills:code-review-and-quality` + `agent-skills:documentation-and-adrs`.

## O que é
Observador **somente leitura** de controladores Coperion K-Tron KCM (dosagem). Historiza, detecta o que mudou, ajuda a manutenção a diagnosticar. Não é supervisório: não comanda nada. Frase central: "O KCM controla a dosagem. A Forja observa o KCM, entende o comportamento e ajuda a manutenção a diagnosticar."

## Regras inegociáveis
- Read-only por construção: driver só `connect/disconnect/read/health/capabilities`. Sem `write` em lugar nenhum (código, API, UI, perfis, IA). `ReadOnlyDriverBase` recusa subclasse com escrita.
- PLC e SCADA não são fonte nem fallback. Leitura direta do KCM via Host/Anybus.
- Nada específico da GTEX em código: protocolo, IP, KGR, Host File, registers, assemblies, bits de MDU/SFT, alarmes, firmware, thresholds vivem em `config/` e `knowledge/`. Desconhecido = literal `UNKNOWN`. Nunca inventar para "fazer funcionar".
- Toda informação técnica leva classificação: FACT, OFFICIAL_DOC, MACHINE_DOC, FIELD_CONFIRMED, FIELD_OBSERVED, FORJA_RULE, TECHNICAL_OPINION, HYPOTHESIS, UNKNOWN. Hipótese não vira fato sem evidência.
- `COMM_ERROR` (tentativa falhou) ≠ `STALE` (valor velho). STALE nunca é gravado; é estado derivado por relógio monotônico. Nunca interpolar GAP.
- Diagnóstico = JSON v1.0 com 7 seções (RESUMO, EVIDÊNCIAS, O QUE MUDOU, HIPÓTESES, PRÓXIMAS VERIFICAÇÕES, FONTES, RESSALVAS). Hipótese é "comportamento compatível com", nunca "causa". UI consome JSON.
- Textos para o usuário em português do Brasil. Código interno só em "Detalhes técnicos".
- Offline-first: sem CDN, sem Google Fonts, sem script remoto. Bind padrão 127.0.0.1.
- Demo mostra DADOS SIMULADOS; dado real mostra DADOS DO EQUIPAMENTO com qualidade.
- Sem tela falsa: botão existe = funciona, ou mostra "Não configurado" / "Disponível após configuração de campo".
- Git só local. Nada sai da máquina. Testes sem rede (só 127.0.0.1).

## Stack (decidida em 2026-09-30, ver docs/auditoria e docs/contracts)
Python 3.14 (`.venv`), FastAPI + uvicorn embutido, Pydantic v2, SQLite WAL em dois arquivos (`forja_core.db`, `forja_historian.db`) com SQL à mão e migrações numeradas, SSE para tempo real, pymodbus (fase J), EtherNet/IP decidido na fase I, serviço Windows com pywin32 + sc.exe (fase N), PyInstaller onedir. Front: Vite + Svelte 5 + TypeScript em `frontend/`, build estático servido pelo FastAPI (fase B; pendente de confirmação do chefe sobre Node).

## Como rodar
```
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\forja.exe run          # http://127.0.0.1:8765
.\.venv\Scripts\forja.exe diagnose --json --demo BELTLOAD_LOW
```

## Estrutura
`src/forja/{domain,config,infra,drivers,normalization,acquisition,historian,events,diagnostics,api,service,tools}`, `config/{equipment,mappings,rules,alarms,stop_by}`, `knowledge/{diagnostics,cases,documents,i18n}`, `tests/{unit,integration,contract,e2e,fixtures}`, `docs/{adr,contracts,field,reference,research,gates,auditoria,derived}`.
Contrato entre módulos: `docs/contracts/CONTRATOS_A1.md`. Auditoria inicial: `docs/auditoria/2026-09-30_auditoria_inicial.md`. Documento Mestre original: `doc/*.docx` (derivado em `docs/derived/`).

## Fases
A0 fundação ✔ · A1 núcleo ✔ (2026-10-01, 528 testes) · B shell/design ✔ · C planta/dashboard ✔ · D dosador animado ✔ (2026-10-01, 566+ testes incl. 38 e2e) · E tendências/timeline · F diagnóstico UX · G comunicação/wizard/mapping · H multi-equipamento · I abstrações de driver · J Modbus TCP · K EtherNet/IP · L saúde/logs · M relatórios/backup/usuários · N instalador Windows · O campo GTEX · P pós-campo. Nenhuma fase avança com teste vermelho.
