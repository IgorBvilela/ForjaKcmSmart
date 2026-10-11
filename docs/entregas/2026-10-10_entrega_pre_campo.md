# Entrega antes da validação em campo — 10/10/2026

Relatório do trabalho de continuação do Forja KCM Intelligence até o ponto de levar a um KCM real. Tudo o que está aqui foi verificado no código e nos testes desta data.

## 1. Estado inicial encontrado

- Fases A0, A1, B, C e D concluídas: domínio, configuração externa, simulador WBF com 9 cenários, historiador SQLite, aquisição isolada por equipamento, motor de eventos, diagnóstico JSON v1.0 com 7 seções, API local, interface (planta, dashboard, eventos, diagnóstico, simulador).
- Testes de partida: 572 do núcleo e 38 de navegador, lint e tipos sem erro.
- Drivers Modbus TCP e EtherNet/IP só registrados como indisponíveis; sem central de comunicação, sem teste somente leitura, sem tendências e histórico reais, sem comissionamento, sem saúde/logs, sem instalador.
- Telas futuras mostradas como "Em desenvolvimento".
- `requirements.lock.txt` com caminho de máquina embutido.

## 2. O que foi implementado

| Fase | Entrega |
|---|---|
| E | Tempo Real, Tendências e Histórico sobre o historiador: gráfico em degrau, buraco nunca interpolado, zoom, "o que mudou primeiro" por janela, CSV com qualidade |
| G | Central de Comunicação: conferir sem conectar, teste somente leitura (bruto, decodificado, qualidade, latência), comparação com a tela do KCM, mapping com versão e histórico, ativação da coleta só com teste válido |
| J | Driver Modbus TCP somente leitura (funções 01 a 04, leitura em bloco, timeout, reconexão, quadro bruto) |
| K | EtherNet/IP somente leitura configurável, cliente CIP mínimo próprio, nada fixo no código (experimental) |
| L | Saúde e logs em português (coleta, disco, bancos, registros do serviço, da comunicação e da auditoria) |
| O | Comissionamento: sessão com cabeçalho, conferência Forja × tela do KCM, relatório CSV e impressão |
| N | Pacote Windows: executável, serviço (LocalService), instalador e atualizador com backup, remoção sem apagar dados, build reproduzível |
| F | Alertas com três vozes separadas (alarme do KCM, evento da Forja, aviso antecipado), reconhecimento auditado, aviso antecipado por tendência e desvio do padrão com limites configuráveis, casos anteriores, "antes do evento" |
| H | Cadastro de equipamentos, ficha técnica com evidência e o que falta levantar, componentes, catálogo de alarmes por chave, arquivar/restaurar sem apagar histórico, planta por área |
| M | Relatório por período, exportações CSV, backup com configuração e rotina diária, configuração em uso |
| Auditoria | Cadeia de hash da trilha de auditoria com conferência |

Correções de segurança operacional feitas no caminho: a coleta de driver real agora exige teste somente leitura também na partida do serviço (antes só pela API); o pacote nunca sai em modo desenvolvimento.

## 3. Arquivos e módulos principais

- Backend: `src/forja/drivers/{modbus_tcp,ethernet_ip}`, `src/forja/normalization/plan.py`, `src/forja/service/{commcenter,edge,winservice,seed,backups}.py`, `src/forja/events/{early_warning,ew_engine,ew_rules,pre_event,recurrence,window_analysis}.py`, `src/forja/reports/{period,events_csv,commissioning,csv_export}.py`, `src/forja/api/routers/{communication,commissioning,intelligence,equipment_admin,backups,reports,system,history}.py`, `src/forja/historian/{backup,core_store}.py` e migrações `0002`/`0003`, `src/forja/tools/admin.py`.
- Configuração: `config/early_warning/EW-*.yaml`.
- Interface: `frontend/src/routes/*Page.svelte` (Comunicação, Comissionamento, Alertas, Aviso antecipado, Casos, Equipamentos, Ficha técnica, Componentes, Alarmes, Backup, Relatórios, Exportações, Configuração, Saúde e logs, Tendências, Histórico, Tempo Real).
- Distribuição: `packaging/` e `scripts/build_windows.ps1`.
- Documentação: `docs/contracts/CONTRATOS_{E,F,G,H,J_K,L,M,N,O}.md`, ADR 0020 a 0032, `docs/campo/guia_visita_de_campo.md`.

## 4. Testes executados e resultados reais

- Núcleo (unidade, integração, contrato): 796 passando.
- Navegador (Edge real, várias larguras, sem requisição externa): 76 passando na bateria completa final.
- Lint (ruff), formatação e tipos (mypy estrito): sem erro. `svelte-check`: 0 erro, 0 aviso.
- Somente leitura provado: contrato da porta de driver, varredura de tokens de escrita, lista fechada de rotas mutantes, servidor Modbus e CIP falsos recebendo só funções de leitura, porteira da coleta sem nenhum pacote ao equipamento.
- Executável testado: init, backup com o Edge ligado (com a configuração no backup), `audit verify`, `/health`, `/app`, `/docs` fechado, instalação e atualização em bancada, atualização recusada com o programa em uso. Pacote final: `build/release/ForjaKCM-0.1.0-win64.zip` (18 MB).
- Conferência visual: ver seção 12.

## 5. Fases realmente concluídas

A0, A1, B, C, D, E, F, G, H, I, J (experimental até o KCM real), K (experimental), L, M, N (serviço não registrado num PC real) e O (ferramenta; validação depende de campo). Fica para depois: P (biblioteca de documentos e manuais).

## 6. O que ainda depende de campo

- Protocolo carregado no Anybus, IP, máscara, gateway, porta, unit id.
- Mapa de registradores ou classe/instância/atributo, tipos, ordem dos bytes e escalas.
- Versão de software do KCM, KGR, Host File, modelo/part number/MAC do Anybus.
- Codificação real de estado da máquina, alarme e motivo de parada.
- Se o KCM aceita mais uma conexão de leitura; topologia e SPAN/TAP para observação passiva.
- Conferência de cada valor contra a tela do KCM (comissionamento).
- Ajuste dos limiares das regras e dos avisos antecipados na operação real.
- Registro e partida do serviço Windows no PC da planta.

## 7. Como rodar (desenvolvimento)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip install -e . --no-deps
.\scripts\build_ui.ps1
.\.venv\Scripts\forja.exe run          # http://127.0.0.1:8765/app
```

Pacote para a planta: `.\scripts\build_windows.ps1` e, no PC da planta, `install.ps1` como Administrador (`packaging/LEIA-ME.txt`).

## 8. Como testar o fluxo de demonstração

1. Planta → Barrilha (exemplo) → Simulador → "Pouco material na correia".
2. Em cerca de um minuto: Alertas mostra o alarme simulado do KCM (código 56) e o evento da Forja, separados; "Reconhecer" registra quem viu.
3. Detalhe do evento: "Antes do evento" mostra quem saiu do padrão primeiro e quanto antes; diagnóstico em 7 seções.
4. Tendências: o degrau da queda; zoom no trecho; "o que mudou primeiro".
5. Aviso antecipado: os sinais medidos contra os limites configurados (o aviso se confirma alguns minutos depois).
6. Ferramentas › Relatórios: relatório do período para imprimir.

## 9. Como usar o modo de comissionamento

1. KCM › Comunicação: configurar, testar somente leitura e salvar (sem isso, a coleta não liga).
2. KCM › Comissionamento: abrir a sessão com técnico, data, protocolo encontrado, versão do KCM, Host/Anybus, IP, máscara e mapping.
3. Para cada variável exposta pelo KCM: anotar o valor da tela do KCM ao lado do valor da Forja; o resultado (confere, diverge, não exposta) fica gravado como evidência (não se apaga).
4. Encerrar com a conclusão; exportar o CSV e imprimir.
5. Roteiro completo: `docs/campo/guia_visita_de_campo.md`.

## 10. Commits criados

`0b87ae4` histórico e análise de janela · `413e690` tendências · `6631c45` Modbus · `cfc6733` prova de somente leitura · `d1a7e1f` reconhecimento auditado · `a5df8b2` tipos do mapping · `356ce13` central de comunicação · `925522c` EtherNet/IP · `31ee293` assistente de comunicação · `61eae1f` comissionamento · `e857dfb` saúde e logs · `0ebf18b` pacote Windows · `6e2fadd` porteira da coleta · `bbfa644` inteligência · `c1d84d5` contratos G/J/K/L/O · `8596229` multi-equipamento, relatórios e backup · `ab9abe5` contratos H/M · `80b597f` cadeia da auditoria · e os commits finais de conferência visual e documentação.

## 11. Riscos e pendências reais

- Nenhum KCM real foi lido ainda: os drivers estão provados contra servidores falsos e ficam experimentais até a validação.
- Serviço Windows: instalação provada em bancada; registro, partida automática e reinício só no PC da planta (exige administrador).
- O repositório traz o nome do cliente e da planta em configuração, conhecimento, testes e documentos (herdado do projeto). Antes de entregar à TI, trocar por nomes neutros é recomendado.
- Sem login nesta versão (ADR 0030): seguro enquanto a interface escutar só em 127.0.0.1.
- Tema claro só na impressão; a interface é escura.
- A etapa de prévia antes de construir telas foi pulada nesta rodada, por pedido de não parar.
- O simulador não tem cenário de deriva lenta; o aviso antecipado está provado por testes com séries sintéticas.
- Executável sem assinatura digital (o Windows pode alertar no primeiro uso).

## 12. Conferência visual

Motor da skill de conferência visual, num Edge local com cópia dos dados de teste (apagada no fim), 16 telas × 375, 768 e 1440 px, com os blocos recolhíveis abertos e passagem de foco por Tab.

- 1ª rodada: 577 achados, todos de 4 causas de base: rótulos e selos em 11 px; números em 12 px (a regra pede 13); contorno de foco cortado no fim do menu lateral que rola; dois campos de marcar com 20 px (mínimo 24 com mouse).
- Correções: rótulo/selo 13 px, legenda e número pequeno 13 px, texto dos eixos dos gráficos 13 px, folga de rolagem no menu lateral, campos de marcar com 24 px (ADR 0032).
- 2ª rodada: 0 erro e 0 aviso nas 48 combinações; Planta e Equipamentos reconferidas depois dos últimos ajustes de texto: 0 achado.
- Não conferido: tema claro (a interface só tem o escuro; o claro existe na impressão) e o que exige ação que o motor não faz (enviar formulários, arrastar no gráfico); esses fluxos são cobertos pelos testes de navegador.
