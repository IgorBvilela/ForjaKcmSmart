# Contratos da Fase E — Tempo Real, Tendências e Histórico

Complementa `CONTRATOS_A1.md` e `CONTRATOS_B.md`. Tudo aqui é leitura: nenhuma rota nova muta estado.

## API (prefixo `/api/v1`)

| Rota | O que devolve |
|---|---|
| `GET /tags` | Catálogo das variáveis semânticas: `code`, `label_pt`, `unit`, `kind`, `decimals`, `explanation_pt`. |
| `GET /equipments/{id}` | Ganha `mapping.readable_tags` (tags com endereço e tipo conhecidos). |
| `GET /equipments/{id}/history.csv?tags&from&to&dialect=br\|std&resolution=raw\|auto` | CSV para download. `raw`: linhas exatamente como gravadas (até 250.000; acima disso 422 `EXPORT_TOO_LARGE`). `auto`: um intervalo por linha (média, mínimo, máximo, leituras, pior qualidade). Sem `tags`, usa as tags legíveis do mapping. |
| `GET /equipments/{id}/what-changed?tags&from&to&togetherS=30` | Análise da janela: `changes` (ordem de saída do padrão, com `offset_s` desde a primeira), `first_changed_tag`, `together` (grupos que saíram juntos), `unchanged_tags`, `stats` por tag, `narrative_pt`, `caveats_pt`, `resolution_s`, `interpolated: false`. |

### CSV

- Colunas brutas: `data_hora_utc`, `data_hora_planta`, `equipamento`, `tag`, `variavel`, `valor`, `unidade`, `qualidade`, `qualidade_texto`, `origem`, `motivo`.
- Colunas resumidas: `inicio_utc`, `inicio_planta`, `intervalo_s`, `equipamento`, `tag`, `variavel`, `media`, `minimo`, `maximo`, `leituras`, `unidade`, `pior_qualidade`, `qualidade_texto`.
- Dialeto `br`: separador `;`, vírgula decimal, BOM UTF-8 (abre no Excel em português). Dialeto `std`: `,` e ponto.
- Leitura sem valor (COMM_ERROR, BAD) sai com `valor` vazio e o `motivo`. Nunca zero, nunca preenchida.

### Análise de janela

- Mesmo componente "O que mudou" dos eventos (`forja.events.what_changed`), em modo `baseline`: o ANTES é o padrão do início da janela (mediana dos primeiros 10% das leituras, pelo menos 3), para um ciclo anterior dentro da janela não contaminar a comparação. Os eventos continuam no modo `pre_departure`.
- Contínuas usam a série do historiador com até 2.000 pontos (até ~33 min são os pontos gravados; acima disso, intervalos com mínimo e máximo reais). Discretas usam as linhas gravadas.
- O texto descreve ordem e simultaneidade. Ressalva fixa: "não é causa".

## Historiador

- `SqliteHistorian.samples(equipment_id, tags, start, end, limit)` → `list[Sample]` (análise).
- `SqliteHistorian.export_rows(...)` → `list[ExportRow]` (tuplas leves para exportação).

## Aquisição: intervalo sem coleta

Na partida da coleta (início do serviço ou reinício pelo watchdog), para cada tag cuja última leitura observada tem mais de `max(2 × poll_interval_s, 3 s)`, o historiador recebe uma linha `COMM_ERROR` sem valor 1 ms depois dessa leitura, com o motivo "a Forja não estava coletando". Com store-on-change, sem essa marca o gráfico seguraria o último valor durante a parada.

## Interface

- Telas `Tempo Real`, `Tendências` e `Histórico` em `/app/eq/{id}/realtime|trends|history`. Período e variáveis ficam na URL (`?p=1h&tags=a,b` ou `?from=<ms>&to=<ms>`).
- Gráfico em degrau (cada ponto vale até a próxima leitura gravada), buraco sombreado, faixa de qualidade na base, faixa mínimo–máximo quando a série é resumida, cursor sincronizado entre os gráficos e zoom por arraste.
- Seleção de variáveis é caixa de seleção (não botão de ação).
