# Contratos da Fase H — Multi-equipamento

Complementa `CONTRATOS_A1.md` e `CONTRATOS_G.md`. As rotas desta fase gravam a configuração da Forja (YAML em `config/equipment`, com histórico e auditoria) e nunca falam com o KCM. Cada equipamento tem o próprio perfil, mapping, driver, conexão, historiador, eventos, diagnóstico, qualidade e estado; a falha de um não derruba os outros (uma task por equipamento, porteira da coleta e avisos antecipados isolados por equipamento).

## Cadastro (`src/forja/api/routers/equipment_admin.py`)

| Rota | O que faz |
|---|---|
| `POST /api/v1/equipments` | Cria o perfil com o protocolo não identificado (`driver: UNKNOWN`) e a coleta desligada, e um mapping próprio modelo (`<id em minúsculas>`, driver e endereços `UNKNOWN`, 10 variáveis). Recusa id repetido (409 `EQUIPMENT_EXISTS`), id de equipamento arquivado (409 `EQUIPMENT_ARCHIVED`), id fora de `^[A-Z0-9][A-Z0-9_]{1,63}$` e aplicação fora de WBF/LWF/UNKNOWN (422). Auditoria `EQUIPMENT_CREATE`. O equipamento entra na memória e sobe na hora (`EquipmentManager.add`). |
| `GET /api/v1/equipments/{id}/datasheet` | Ficha: identificação, controlador, interface Host, componentes, `config_hash`, resumo do mapping e `unknown_fields` (o que falta levantar em campo). |
| `POST /api/v1/equipments/{id}/datasheet` | Grava identificação, controlador, interface Host e componentes com `base_hash` (409 `CONFIG_CONFLICT` se o arquivo mudou). A comunicação não muda por aqui. Auditoria `EQUIPMENT_DATASHEET_SAVE` com antes e depois. |
| `POST /api/v1/equipments/{id}/archive` | Exige `confirm_id` igual ao id e motivo. Move o YAML para `config/_archive/equipment/<arquivo>__<instante>.yaml`, para a coleta e tira o equipamento da memória (`EquipmentManager.remove`). O histórico no banco fica. Auditoria `EQUIPMENT_ARCHIVE`. |
| `GET /api/v1/archived-equipments` | Arquivados (o mais recente de cada id). |
| `POST /api/v1/archived-equipments/{id}/restore` | Devolve o arquivo para `config/equipment` (sem sobrescrever) e sobe o equipamento; a porteira do teste somente leitura vale. Auditoria `EQUIPMENT_RESTORE`. |
| `GET /api/v1/equipments/{id}/alarm-catalog` | Chave do equipamento (fabricante, controlador, aplicação, versão), alarmes catalogados exatamente nessa chave e, à parte, os de outras chaves ("não valem para este equipamento"). |

Atualização do programa (`forja init`) não recria perfil da semente que foi arquivado: a semente pula `config/equipment/<nome>.yaml` quando existe `config/_archive/equipment/<nome>__*.yaml`.

`GET /api/v1/plant` e `GET /api/v1/equipments` ganham `plant`, `area` e `line` em cada equipamento.

## Interface

- **Sistema › Equipamentos** (`/app/system/equipments`): equipamentos na planta (ordenados por área e linha), com Ficha técnica, Comunicação e Arquivar (pede o id digitado e o motivo); cadastro com id sugerido a partir da área e do nome; arquivados com Restaurar. Responsável lembrado neste navegador (o mesmo da Comunicação e do Comissionamento).
- **KCM › Ficha Técnica** (`/app/eq/{id}/kcm/datasheet`): leitura com "Desconhecido" destacado e a lista "O que falta levantar em campo"; edição com evidência (`KnowledgeState`) para aplicação e interface Host; campo em branco grava `UNKNOWN`.
- **KCM › Componentes**: KCM, MDU, balança, SFT, encoder, SIB, motor, Anybus e outros, com modelo, série, quantidade, evidência e nota.
- **KCM › Alarmes**: catálogo da chave do equipamento, aviso quando parte da chave é desconhecida e as outras chaves recolhidas.
- **Planta**: cards agrupados por área e linha quando há mais de um grupo; "Área não informada" para quem não tem área.

## Provas

- `tests/integration/test_api_equipment_admin.py`: criar (protocolo não identificado, coleta desligada, mapping todo `UNKNOWN`, cabeçalho de origem, auditoria), id repetido e inválido, ficha com evidência e conflito, arquivar e restaurar sem apagar, semente não traz arquivado de volta, catálogo por chave.
- `tests/e2e/test_equipments.py`: cadastrar, ver na planta agrupada, editar a ficha, comunicação nasce sem protocolo, arquivar com confirmação e restaurar, catálogo de alarmes, componentes, telas em 375 px.
