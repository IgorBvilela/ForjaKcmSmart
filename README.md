# Forja KCM Intelligence

Observador **somente leitura** de controladores Coperion K-Tron KCM. Historiza, detecta o que mudou e ajuda a manutenção a diagnosticar. Não comanda nada.

> O KCM controla a dosagem. A Forja observa o KCM, entende o comportamento e ajuda a manutenção a diagnosticar.

## Rodar (desenvolvimento, Windows)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e . -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\forja.exe run            # UI/API em http://127.0.0.1:8765 (dados simulados)
.\.venv\Scripts\forja.exe diagnose --json --demo BELTLOAD_LOW
```

## Documentos
- `docs/auditoria/2026-09-30_auditoria_inicial.md`: auditoria, decisões e plano por fases.
- `docs/contracts/CONTRATOS_A1.md`: contrato entre módulos do núcleo.
- `doc/Forja_KCM_Intelligence_Documento_Mestre_Claude.docx`: Documento Mestre (fonte); derivado em `docs/derived/`.

Tudo que depende da planta GTEX permanece `UNKNOWN` até validação em campo.
