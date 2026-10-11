# Tarefas · Fase Q · Interface enxuta

Plano: `tasks/plan.md`. Especificação: `docs/produto/especificacao_interface_enxuta.md`.

## Fase 0 · Prévia
- [x] T0 · Prévia interativa em localhost (`previa.html`), conferida em 375 / 768 / 1440
- [x] Checkpoint 0 · Escolhas registradas no §15 da especificação; prévia apagada

## Fase 1 · Agora
- [x] T1 · Junção dos dados e `GET /api/v1/situation`
- [x] T2 · Início do alarme do KCM pelo historiador ("início não determinado" quando não houver)
- [x] T3 · Tela Agora (`/app/now`)
- [x] Checkpoint A · Núcleo e navegador verdes; conferência visual da tela Agora

## Fase 2 · Navegação enxuta
- [x] T4 · Títulos independentes do menu
- [x] T5 · Menu com 4 entradas e engrenagem; rota inicial `/app/now`
  - Corrigidos os defeitos antigos do cabeçalho: seletor de equipamento com 16 px abaixo de 1024 px (nome e estado cabem a partir de 360 px); botões de dica e link com alvo mínimo de 24 px
- [x] T6 · Abas do Dashboard (feito antes de T5, para nenhuma tela ficar sem caminho)
- [x] Checkpoint B · Todas as telas a até 2 cliques; bateria completa verde (806 núcleo + 95 navegador); conferência visual do menu e da gaveta sem achados

## Fase 3 · Planta e Comunicação
- [x] T7 · Planta em grade quase quadrada (4 = 2 × 2) e cartão enxuto
  - A linha "Último evento", cortada com reticências a 375 e 768 px, saiu do cartão
- [x] T8 · Comunicação direta
- [x] T9 · Texto enxuto: telas de dados (cabeçalho padrão com uma frase de apoio e "Saiba mais")
  - Corrigidos na conferência visual: resumo do diagnóstico cortado com reticências; opções de formato do CSV com 20 e 24 px (agora a linha inteira é o alvo); "Abrir diagnóstico" e títulos da linha do tempo com 20 px; eixo do gráfico repetindo "62, 62, 62"; coluna "Sem leitura" escondida atrás da rolagem no quadro estreito
- [ ] T10 · Texto enxuto: telas de sistema
- [ ] T11 · Texto enxuto: telas do dosador e de inteligência
- [ ] Checkpoint C · Uma frase de apoio por tela principal; bateria verde; conferência visual

## Fase 4 · Modo TV
- [ ] T12 · Modo TV (`/app/tv`)

## Fase 5 · Acabamento
- [ ] T13 · Animações (genjutsu cast)
- [ ] T14 · ADR 0033, CONTRATOS_Q, README, especificação atualizada

## Fase 6 · Extras aprovados na prévia
- [ ] T15 · Medida de tempo: dentro do normal, fora do normal e sem dados
- [ ] T16 · Resumo do turno para imprimir (turnos vêm da configuração da planta)
- [ ] T17 · Placar do dia na TV
- [ ] T18 · Atalhos de teclado de 1 a 4, com opção de desligar
- [ ] T19 · Tema claro opcional, conferido nos dois temas
- Etapa de rede e login (fora desta fase): QR code na TV

## Achados para decidir depois
- Resolvido no T9: com evento aberto o servidor manda uma atualização por segundo; o cliente agora só reconsulta quando estado, gravidade, qualidade ou reconhecimento mudam (o detalhe do próprio evento continua acompanhando).
- Regra "Pouco material sobre a correia": o evento se encerra cerca de 50 s depois de abrir, embora a carga continue baixa, porque a regra olha a queda dentro de 60 s e não o nível. O alarme do KCM e o evento "Esforço do acionamento alto" seguem ativos. Decisão de domínio para o usuário.
