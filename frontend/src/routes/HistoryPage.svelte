<script lang="ts">
  /** Histórico: consulta ao historiador por período. Resumo por variável, eventos do período,
   *  tabela de pontos com qualidade e exportação CSV (pontos gravados ou resumo por intervalo).
   *  Ponto sem leitura aparece como "sem leitura", nunca como zero. */
  import { untrack } from 'svelte'
  import Download from '@lucide/svelte/icons/download'
  import {
    api,
    errorMessage,
    QUALITY_PT,
    type CsvDialect,
    type EventView,
    type HistorySeries,
    type TagWindowStats,
  } from '../lib/api'
  import { discreteText } from '../lib/discrete'
  import { fmtDateTime, fmtDuration, fmtNumber } from '../lib/format'
  import { live } from '../lib/live.svelte'
  import { periodFromSearch, resolvePeriod, searchFor, tagsFromSearch, type Period } from '../lib/period'
  import { href } from '../lib/router'
  import { app } from '../lib/state.svelte'
  import { DEFAULT_TREND_TAGS, sortTags, tagCatalog } from '../lib/tagmeta.svelte'
  import EventRow from '../components/data/EventRow.svelte'
  import PeriodPicker from '../components/data/PeriodPicker.svelte'
  import TagPicker from '../components/data/TagPicker.svelte'
  import Card from '../components/ui/Card.svelte'
  import PageHeader from '../components/ui/PageHeader.svelte'
  import EmptyState from '../components/ui/EmptyState.svelte'
  import QualityBadge from '../components/ui/QualityBadge.svelte'

  let { equipmentId }: { equipmentId: string } = $props()

  const PAGE = 100
  let readable = $state<string[]>([])
  const initialPeriod = periodFromSearch(location.search)
  let period = $state<Period>(initialPeriod)
  let tags = $state<string[]>(tagsFromSearch(location.search) ?? [])
  let tableTag = $state<string | null>(null)
  let windowMs = $state(resolvePeriod(initialPeriod, Date.now()))
  let stats = $state<Record<string, TagWindowStats>>({})
  let events = $state<EventView[]>([])
  let tableSeries = $state<HistorySeries | null>(null)
  let page = $state(0)
  let dialect = $state<CsvDialect>('br')
  let loading = $state(true)
  let error = $state<string | null>(null)

  const name = $derived(live.cardOf(equipmentId)?.name ?? equipmentId)
  const available = $derived(sortTags(readable).map((t) => tagCatalog.meta(t)))
  const shown = $derived(sortTags(tags.filter((t) => readable.includes(t))))
  const rows = $derived(tableSeries ? [...tableSeries.points].reverse() : [])
  const pageRows = $derived(rows.slice(page * PAGE, page * PAGE + PAGE))
  const pages = $derived(Math.max(1, Math.ceil(rows.length / PAGE)))
  const iso = $derived({ from: new Date(windowMs.from).toISOString(), to: new Date(windowMs.to).toISOString() })
  const csvRaw = $derived(
    api.historyCsvUrl(equipmentId, { tags: shown, ...iso, dialect, resolution: 'raw' }),
  )
  const csvAgg = $derived(
    api.historyCsvUrl(equipmentId, { tags: shown, ...iso, dialect, resolution: 'auto' }),
  )

  async function loadMeta(id: string): Promise<void> {
    try {
      await tagCatalog.ensure()
      const detail = await api.equipment(id)
      if (id !== equipmentId) return
      readable = detail.mapping.readable_tags
      if (tags.length === 0 || tags.every((t) => !readable.includes(t))) {
        const preferred = DEFAULT_TREND_TAGS.filter((t) => readable.includes(t))
        tags = preferred.length ? [...preferred] : readable.slice(0, 4)
      }
    } catch (err) {
      if (id === equipmentId) {
        error = errorMessage(err)
        loading = false
      }
    }
  }

  async function load(): Promise<void> {
    const id = equipmentId
    const list = shown
    if (!list.length) return
    const range = resolvePeriod(period, Date.now())
    const from = new Date(range.from).toISOString()
    const to = new Date(range.to).toISOString()
    const tag = tableTag && list.includes(tableTag) ? tableTag : list[0]
    try {
      const [changed, evs, hist] = await Promise.all([
        api.whatChanged(id, list, { from, to }),
        api.events(id, { since: from, until: to, limit: 200 }),
        api.history(id, [tag], { from, to, maxPoints: 2000 }),
      ])
      if (id !== equipmentId) return
      stats = changed.stats
      events = evs.events
      tableSeries = hist.series[0] ?? null
      tableTag = tag
      windowMs = range
      page = 0
      error = null
    } catch (err) {
      if (id === equipmentId) error = errorMessage(err)
    } finally {
      if (id === equipmentId) loading = false
    }
  }

  $effect(() => {
    void loadMeta(equipmentId)
  })

  $effect(() => {
    void period
    void tableTag
    const key = shown.join(',')
    if (!key) return
    untrack(() => {
      history.replaceState(null, '', location.pathname + searchFor(period, shown))
      loading = true
      void load()
    })
  })

  function cell(tag: string, v: number | null): string {
    if (v == null) return 'sem leitura'
    const meta = tagCatalog.meta(tag)
    return meta.kind === 'CONTINUOUS' ? fmtNumber(v, meta.decimals) : discreteText(tag, v)
  }
</script>

<section class="hist" data-testid="history">
  <PageHeader kicker={name} title="Histórico" lead="Os pontos gravados de um período, com a qualidade de cada valor.">
    {#snippet more()}
      <p>A consulta traz o resumo por variável, os eventos do período e os pontos gravados.</p>
    {/snippet}
  </PageHeader>

  <Card padded class="controls">
    <PeriodPicker {period} now={app.now} onchange={(p) => (period = p)} testid="history-period" />
    {#if available.length}
      <TagPicker {available} selected={shown} max={12} collapsible={app.isMobile} onchange={(t) => (tags = t)} testid="history-tag" />
    {/if}
    <p class="window num">{fmtDateTime(windowMs.from)} até {fmtDateTime(windowMs.to)} · {fmtDuration((windowMs.to - windowMs.from) / 1000)}</p>
  </Card>

  {#if error}
    <EmptyState title="Não foi possível consultar o histórico" text={error} />
  {:else if !loading && readable.length === 0}
    <EmptyState
      title="Nenhuma variável mapeada para este equipamento"
      text="O histórico aparece quando o mapping tiver endereços legíveis. Configure em KCM › Comunicação."
    />
  {:else}
    <div class="grid">
      <Card title="Exportar" testid="history-export">
        <fieldset class="dialect">
          <legend>Formato</legend>
          <label class="choice"><input type="radio" name="dialect" value="br" bind:group={dialect} /><span class="choice-mark" data-kind="radio" aria-hidden="true"></span> Excel em português (ponto e vírgula, vírgula decimal)</label>
          <label class="choice"><input type="radio" name="dialect" value="std" bind:group={dialect} /><span class="choice-mark" data-kind="radio" aria-hidden="true"></span> Padrão (vírgula, ponto decimal)</label>
        </fieldset>
        <div class="dl">
          <a class="dl-btn primary" href={csvRaw} download data-testid="history-export-raw">
            <Download size={16} aria-hidden="true" /> Pontos gravados (CSV)
          </a>
          <a class="dl-btn" href={csvAgg} download data-testid="history-export-agg">
            <Download size={16} aria-hidden="true" /> Resumo por intervalo (CSV)
          </a>
        </div>
        <p class="muted">
          Cada linha traz instante (UTC e horário da planta), valor, unidade e qualidade. Leitura
          sem valor sai em branco com o motivo. Pontos gravados: até 250.000 linhas por arquivo.
        </p>
      </Card>

      <Card title="Resumo por variável" testid="history-summary">
        {#if Object.keys(stats).length === 0}
          <p class="muted">{loading ? 'Consultando…' : 'Sem leituras gravadas neste período.'}</p>
        {:else}
          <div class="table-wrap">
            <table class="resp">
              <thead>
                <tr>
                  <th scope="col">Variável</th>
                  <th scope="col" class="r">Mín.</th>
                  <th scope="col" class="r">Máx.</th>
                  <th scope="col" class="r">Média</th>
                  <th scope="col" class="r">Pontos</th>
                  <th scope="col" class="r">Sem leitura</th>
                </tr>
              </thead>
              <tbody>
                {#each shown as tag (tag)}
                  {@const s = stats[tag]}
                  {#if s}
                    <tr>
                      <th scope="row">{s.label_pt}{#if s.unit}<span class="u"> {s.unit}</span>{/if}</th>
                      <td class="r num" data-label="Mínimo">{fmtNumber(s.min, s.decimals)}</td>
                      <td class="r num" data-label="Máximo">{fmtNumber(s.max, s.decimals)}</td>
                      <td class="r num" data-label="Média">{fmtNumber(s.avg, s.decimals)}</td>
                      <td class="r num" data-label="Pontos">{s.points}</td>
                      <td class="r num" data-label="Sem leitura">{s.comm_error_points}</td>
                    </tr>
                  {/if}
                {/each}
              </tbody>
            </table>
          </div>
        {/if}
      </Card>

      <Card title={`Eventos do período (${events.length})`} padded={false} testid="history-events">
        {#if events.length === 0}
          <p class="muted pad">Nenhum evento detectado pela Forja neste período.</p>
        {:else}
          <div class="ev">
            {#each events as e, i (e.id)}
              <EventRow event={e} href={href.event(equipmentId, e.id)} hasDiagnosis={null} index={i} />
            {/each}
          </div>
        {/if}
      </Card>

      <Card title="Pontos" testid="history-points">
        {#snippet actions()}
          {#if shown.length > 1}
            <label class="pick">
              <span class="sr">Variável da tabela</span>
              <select bind:value={tableTag} data-testid="history-table-tag">
                {#each shown as t (t)}<option value={t}>{tagCatalog.meta(t).label_pt}</option>{/each}
              </select>
            </label>
          {/if}
        {/snippet}
        {#if !tableSeries}
          <p class="muted">{loading ? 'Consultando…' : 'Sem pontos.'}</p>
        {:else}
          <p class="muted">
            {tableSeries.downsampled
              ? `Cada linha resume ${fmtDuration(tableSeries.bucket_s)} (média, mínimo e máximo). Exporte os pontos gravados para o detalhe.`
              : 'Pontos como gravados pelo historiador (mais recentes primeiro).'}
            {#if tableSeries.gap_count}{tableSeries.gap_count} trecho(s) sem leitura.{/if}
          </p>
          <div class="table-wrap">
            <table data-testid="history-table" data-rows={rows.length}>
              <thead>
                <tr>
                  <th scope="col">Instante</th>
                  <th scope="col" class="r">Valor</th>
                  {#if tableSeries.downsampled}
                    <th scope="col" class="r">Mín.</th>
                    <th scope="col" class="r">Máx.</th>
                    <th scope="col" class="r">Leituras</th>
                  {/if}
                  <th scope="col">Qualidade</th>
                </tr>
              </thead>
              <tbody>
                {#each pageRows as p (p.ts_utc)}
                  <tr class:gap={p.value == null}>
                    <td class="num">{fmtDateTime(p.ts_utc)}</td>
                    <td class="r num">{cell(tableSeries.tag, p.value)}</td>
                    {#if tableSeries.downsampled}
                      <td class="r num">{fmtNumber(p.min, tagCatalog.meta(tableSeries.tag).decimals)}</td>
                      <td class="r num">{fmtNumber(p.max, tagCatalog.meta(tableSeries.tag).decimals)}</td>
                      <td class="r num">{p.n}</td>
                    {/if}
                    <td><QualityBadge quality={p.quality} qualityPt={p.value == null && p.n === 0 ? 'Sem leitura' : QUALITY_PT[p.quality]} /></td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
          {#if pages > 1}
            <nav class="pager" aria-label="Páginas">
              <button type="button" disabled={page === 0} onclick={() => (page -= 1)}>Anterior</button>
              <span class="num">{page + 1} de {pages}</span>
              <button type="button" disabled={page >= pages - 1} onclick={() => (page += 1)}>Próxima</button>
            </nav>
          {/if}
        {/if}
      </Card>
    </div>
  {/if}
</section>

<style>
  .hist { display: flex; flex-direction: column; gap: var(--sp-5); min-width: 0; }
  :global(.controls) { display: flex; flex-direction: column; gap: var(--sp-3); }
  .window { margin: 0; color: var(--text-2); font-size: var(--fs-mono-sm); }
  .grid { display: grid; gap: var(--sp-4); grid-template-columns: minmax(0, 1fr); }
  @media (min-width: 1280px) {
    .grid { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
  }
  .muted { margin: 0; color: var(--text-3); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .pad { padding: var(--sp-4); }
  .dialect { margin: 0 0 var(--sp-3); padding: 0; border: 0; display: flex; flex-direction: column; gap: var(--sp-2); }
  .dialect legend { margin-bottom: var(--sp-2); color: var(--text-3); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .dl { display: flex; flex-wrap: wrap; gap: var(--sp-2); margin-bottom: var(--sp-3); }
  .dl-btn {
    display: inline-flex;
    align-items: center;
    gap: var(--sp-2);
    min-height: var(--touch);
    padding: 0 var(--sp-4);
    border: 1px solid var(--border-2);
    border-radius: var(--r-3);
    color: var(--text-1);
    background: var(--surf-2);
    text-decoration: none;
    font: 500 var(--fs-body) / 1 var(--font-ui);
  }
  .dl-btn.primary { background: var(--accent); border-color: var(--accent); color: var(--on-accent); }
  .dl-btn:hover { border-color: var(--accent); }
  .ev { display: flex; flex-direction: column; max-height: 420px; overflow-y: auto; }
  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  th, td { padding: var(--sp-2); border-bottom: 1px solid var(--border-1); text-align: left; }
  thead th { color: var(--text-3); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  tbody th { color: var(--text-1); font-weight: 500; }
  td.num { color: var(--text-1); font-size: var(--fs-mono); white-space: nowrap; }
  tr.gap td.num { color: var(--text-3); }
  .u { margin-left: 6px; color: var(--text-3); font-weight: 400; }
  .r { text-align: right; }
  .pick select {
    min-height: var(--touch);
    padding: 0 var(--sp-2);
    border: 1px solid var(--border-input);
    border-radius: var(--r-2);
    background: var(--surf-2);
    color: var(--text-1);
    font: 16px / 1 var(--font-ui);
  }
  .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
  .pager { display: flex; align-items: center; justify-content: flex-end; gap: var(--sp-3); margin-top: var(--sp-3); color: var(--text-2); }
  .pager button {
    min-height: var(--touch);
    padding: 0 var(--sp-4);
    border: 1px solid var(--border-2);
    border-radius: var(--r-3);
    background: var(--surf-1);
    color: var(--text-1);
    font: 500 var(--fs-body) / 1 var(--font-ui);
    cursor: pointer;
  }
  .pager button:disabled { opacity: 0.45; cursor: not-allowed; }
</style>
