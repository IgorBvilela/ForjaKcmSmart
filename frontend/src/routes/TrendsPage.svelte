<script lang="ts">
  /** Tendências: gráficos do historiador por variável e a leitura "o que mudou nesta janela".
   *  Responde: o que mudou? quando começou? qual variável mudou primeiro? quais mudaram juntas?
   *  Buraco é buraco (sem leitura), nunca interpolado. Atalho de período atualiza sozinho. */
  import { untrack } from 'svelte'
  import ZoomOut from '@lucide/svelte/icons/zoom-out'
  import Download from '@lucide/svelte/icons/download'
  import ArrowRight from '@lucide/svelte/icons/arrow-right'
  import {
    api,
    errorMessage,
    type HistorySeries,
    type WhatChangedResponse,
  } from '../lib/api'
  import { fmtDateTime, fmtNumber, fmtTime } from '../lib/format'
  import { live } from '../lib/live.svelte'
  import {
    isLive,
    periodFromSearch,
    periodLabel,
    resolvePeriod,
    searchFor,
    tagsFromSearch,
    type Period,
  } from '../lib/period'
  import { app } from '../lib/state.svelte'
  import { DEFAULT_TREND_TAGS, sortTags, tagCatalog } from '../lib/tagmeta.svelte'
  import TrendChart from '../components/charts/TrendChart.svelte'
  import PeriodPicker from '../components/data/PeriodPicker.svelte'
  import TagPicker from '../components/data/TagPicker.svelte'
  import Card from '../components/ui/Card.svelte'
  import PageHeader from '../components/ui/PageHeader.svelte'
  import EmptyState from '../components/ui/EmptyState.svelte'

  let { equipmentId }: { equipmentId: string } = $props()

  const REFRESH_MS = 15_000
  const MAX_POINTS = 1200
  const COLORS: Record<string, string> = {
    mass_flow: '--s1',
    drive_command: '--s2',
    belt_load: '--s3',
    rpm: '--s4',
  }
  const CYCLE = ['--s1', '--s3', '--s4', '--s2']

  let readable = $state<string[]>([])
  const initialPeriod = periodFromSearch(location.search)
  let period = $state<Period>(initialPeriod)
  let tags = $state<string[]>(tagsFromSearch(location.search) ?? [])
  let zoom = $state<{ from: number; to: number } | null>(null)
  let windowMs = $state<{ from: number; to: number }>(resolvePeriod(initialPeriod, Date.now()))
  let series = $state<Record<string, HistorySeries>>({})
  let analysis = $state<WhatChangedResponse | null>(null)
  let loading = $state(true)
  let error = $state<string | null>(null)
  let lastFetch = $state<number | null>(null)

  const name = $derived(live.cardOf(equipmentId)?.name ?? equipmentId)
  const available = $derived(sortTags(readable).map((t) => tagCatalog.meta(t)))
  const shown = $derived(sortTags(tags.filter((t) => readable.includes(t))))
  const withSetpointRef = $derived(shown.includes('mass_flow') && readable.includes('setpoint') && !shown.includes('setpoint'))
  const csvHref = $derived(
    api.historyCsvUrl(equipmentId, {
      tags: shown,
      from: new Date(windowMs.from).toISOString(),
      to: new Date(windowMs.to).toISOString(),
      dialect: 'br',
      resolution: 'raw',
    }),
  )

  function colorFor(tag: string, i: number): string {
    return COLORS[tag] ?? CYCLE[i % CYCLE.length]
  }

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
    if (list.length === 0) return
    const range = zoom ?? resolvePeriod(period, Date.now())
    const from = new Date(range.from).toISOString()
    const to = new Date(range.to).toISOString()
    const query = withSetpointRef ? [...list, 'setpoint'] : list
    try {
      const [hist, changed] = await Promise.all([
        api.history(id, query, { from, to, maxPoints: MAX_POINTS }),
        api.whatChanged(id, list, { from, to }),
      ])
      if (id !== equipmentId) return
      const next: Record<string, HistorySeries> = {}
      for (const s of hist.series) next[s.tag] = s
      series = next
      analysis = changed
      windowMs = range
      error = null
      lastFetch = Date.now()
    } catch (err) {
      if (id === equipmentId) error = errorMessage(err)
    } finally {
      if (id === equipmentId) loading = false
    }
  }

  $effect(() => {
    void loadMeta(equipmentId)
  })

  // refaz a consulta quando período, zoom ou variáveis mudam; mantém a URL compartilhável
  $effect(() => {
    void period
    void zoom
    const key = shown.join(',')
    if (!key) return
    untrack(() => {
      history.replaceState(null, '', location.pathname + searchFor(period, shown))
      loading = true
      void load()
    })
  })

  // atalho de período: atualiza sozinho (o zoom congela a janela)
  $effect(() => {
    if (!isLive(period) || zoom) return
    const timer = window.setInterval(() => void load(), REFRESH_MS)
    return () => clearInterval(timer)
  })

  function onZoom(from: number, to: number): void {
    zoom = { from, to }
  }

  const changeByTag = $derived(
    Object.fromEntries((analysis?.changes ?? []).map((c) => [c.item.tag, c])),
  )
</script>

<section class="trends" data-testid="trends">
  <PageHeader kicker={name} title="Tendências" lead="O que mudou, quando começou e qual variável mudou primeiro.">
    {#snippet more()}
      <p>Cada ponto vale até a próxima leitura gravada. Trecho sem leitura aparece sombreado e nunca é preenchido.</p>
      <p>Arraste sobre um gráfico para ampliar um trecho.</p>
    {/snippet}
    {#snippet actions()}
      <a class="export" href={csvHref} download data-testid="trends-export">
        <Download size={16} aria-hidden="true" /> Exportar este trecho (CSV)
      </a>
    {/snippet}
  </PageHeader>

  <Card padded class="controls">
    <PeriodPicker
      {period}
      now={app.now}
      onchange={(p) => {
        zoom = null
        period = p
      }}
      testid="trends-period"
    />
    {#if available.length}
      <TagPicker {available} selected={shown} collapsible={app.isMobile} onchange={(t) => (tags = t)} testid="trends-tag" />
    {/if}
    <p class="window num" data-testid="trends-window">
      {#if zoom}
        <span class="zoom-chip">
          Zoom: {fmtDateTime(zoom.from)} – {fmtTime(zoom.to)}
          <button type="button" class="zoom-reset" onclick={() => (zoom = null)} data-testid="trends-zoom-reset">
            <ZoomOut size={16} aria-hidden="true" /> Voltar ao período
          </button>
        </span>
      {:else}
        {periodLabel(period)}: {fmtDateTime(windowMs.from)} até {fmtDateTime(windowMs.to)}
        {#if isLive(period)}<span class="auto">· atualiza a cada 15 s</span>{/if}
      {/if}
    </p>
  </Card>

  {#if error}
    <EmptyState title="Não foi possível carregar as tendências" text={error} />
  {:else if !loading && readable.length === 0}
    <EmptyState
      title="Nenhuma variável mapeada para este equipamento"
      text="As tendências aparecem quando o mapping tiver endereços legíveis. Configure em Comunicação."
    />
  {:else}
    <div class="grid">
      <Card title="O que mudou nesta janela" class="changes" testid="trends-what-changed">
        {#if !analysis}
          <p class="muted" aria-busy="true">Analisando a janela…</p>
        {:else}
          <ol class="story">
            {#each analysis.narrative_pt as line, i (i)}
              <li class:first={i === 0 && analysis.first_changed_tag != null}>{line}</li>
            {/each}
          </ol>
          {#if analysis.changes.length}
            <ul class="order" aria-label="Ordem das mudanças">
              {#each analysis.changes as c, i (c.item.tag)}
                <li data-testid={`trends-change-${c.item.tag}`} data-first={c.item.changed_first}>
                  <span class="pos num">{i + 1}</span>
                  <span class="what">
                    <b>{c.item.label_pt}</b>
                    <span class="delta">{c.item.text_pt}</span>
                  </span>
                  <span class="at num">
                    {c.started_pt}
                    {#if i > 0 && c.offset_s != null}<em>+{fmtNumber(c.offset_s, 0)} s</em>{/if}
                  </span>
                </li>
              {/each}
            </ul>
          {/if}
          {#if analysis.unchanged_tags.length}
            <p class="muted">
              Sem mudança: {analysis.unchanged_tags.map((t) => tagCatalog.meta(t).label_pt).join(', ')}.
            </p>
          {/if}
          <ul class="caveats">
            {#each analysis.caveats_pt as c, i (i)}<li>{c}</li>{/each}
          </ul>
        {/if}
      </Card>

      <Card title="Gráficos" class="charts" testid="trends-charts">
        {#snippet actions()}
          {#if lastFetch}<span class="muted num">consultado às {fmtTime(lastFetch)}</span>{/if}
        {/snippet}
        {#if loading && Object.keys(series).length === 0}
          <div class="sk" aria-busy="true" aria-label="Carregando gráficos"></div>
        {:else}
          <div class="stack">
            {#each shown as tag, i (tag)}
              {#if series[tag]}
                <TrendChart
                  points={series[tag].points}
                  refPoints={tag === 'mass_flow' && withSetpointRef ? (series['setpoint']?.points ?? null) : null}
                  refLabel="setpoint"
                  meta={tagCatalog.meta(tag)}
                  color={colorFor(tag, i)}
                  from={windowMs.from}
                  to={windowMs.to}
                  downsampled={series[tag].downsampled}
                  onzoom={onZoom}
                  testid={`trend-chart-${tag}`}
                />
                {#if changeByTag[tag]}
                  <p class="mark num">
                    <ArrowRight size={14} aria-hidden="true" />
                    saiu do padrão às {changeByTag[tag].started_pt}
                  </p>
                {/if}
              {/if}
            {/each}
          </div>
          <div class="legend" aria-label="Legenda de qualidade">
            <span class="label">Qualidade (faixa na base)</span>
            <span><i data-q="GOOD"></i>Validado</span>
            <span><i data-q="SIMULATED"></i>Simulado</span>
            <span><i data-q="UNCERTAIN"></i>Não validado</span>
            <span><i data-q="COMM_ERROR"></i>Sem comunicação</span>
            <span><i data-q="BAD"></i>Inválido</span>
          </div>
          {#if Object.values(series).some((s) => s.downsampled)}
            <p class="muted">
              Período longo: cada ponto resume um intervalo
              ({Object.values(series)[0]?.resolution === 'raw' ? 'bruto' : `${Object.values(series)[0]?.bucket_s} s`}).
              Amplie um trecho para ver os pontos gravados.
            </p>
          {/if}
        {/if}
      </Card>

      {#if analysis && Object.keys(analysis.stats).length}
        <Card title="Resumo do período" class="stats" testid="trends-stats">
          <div class="table-wrap">
            <table class="resp">
              <thead>
                <tr>
                  <th scope="col">Variável</th>
                  <th scope="col" class="r">Mínimo</th>
                  <th scope="col" class="r">Máximo</th>
                  <th scope="col" class="r">Média</th>
                  <th scope="col" class="r">Último</th>
                  <th scope="col" class="r">Sem leitura</th>
                </tr>
              </thead>
              <tbody>
                {#each shown as tag (tag)}
                  {@const s = analysis.stats[tag]}
                  {#if s}
                    <tr>
                      <th scope="row">{s.label_pt}{#if s.unit}<span class="u"> {s.unit}</span>{/if}</th>
                      <td class="r num" data-label="Mínimo">{fmtNumber(s.min, s.decimals)}</td>
                      <td class="r num" data-label="Máximo">{fmtNumber(s.max, s.decimals)}</td>
                      <td class="r num" data-label="Média">{fmtNumber(s.avg, s.decimals)}</td>
                      <td class="r num" data-label="Último">{fmtNumber(s.last, s.decimals)}</td>
                      <td class="r num" data-label="Sem leitura">{s.comm_error_points}</td>
                    </tr>
                  {/if}
                {/each}
              </tbody>
            </table>
          </div>
        </Card>
      {/if}
    </div>
  {/if}
</section>

<style>
  .trends { display: flex; flex-direction: column; gap: var(--sp-5); min-width: 0; }
  .export {
    display: inline-flex;
    align-items: center;
    gap: var(--sp-2);
    min-height: var(--touch);
    padding: 0 var(--sp-4);
    border: 1px solid var(--border-2);
    border-radius: var(--r-3);
    color: var(--text-1);
    background: var(--surf-1);
    text-decoration: none;
    font: 500 var(--fs-body) / 1 var(--font-ui);
  }
  .export:hover { border-color: var(--accent); }
  :global(.controls) { display: flex; flex-direction: column; gap: var(--sp-3); }
  .window { margin: 0; color: var(--text-2); font-size: var(--fs-mono-sm); }
  .auto { color: var(--text-3); }
  .zoom-chip { display: inline-flex; flex-wrap: wrap; align-items: center; gap: var(--sp-2); }
  .zoom-reset {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-height: var(--touch);
    padding: 0 var(--sp-3);
    border: 1px solid var(--accent);
    border-radius: var(--r-pill);
    background: var(--accent-soft);
    color: var(--accent-text);
    font: 500 var(--fs-body) / 1 var(--font-ui);
    cursor: pointer;
  }

  .grid { display: grid; gap: var(--sp-4); grid-template-columns: minmax(0, 1fr); }
  @media (min-width: 1280px) {
    .grid { grid-template-columns: minmax(0, 2fr) minmax(320px, 1fr); }
    .grid :global(.charts) { grid-column: 1; grid-row: 1 / span 2; }
    .grid :global(.changes) { grid-column: 2; grid-row: 1; }
    .grid :global(.stats) { grid-column: 2; grid-row: 2; }
  }
  .stack { display: flex; flex-direction: column; gap: var(--sp-5); min-width: 0; }
  .mark {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    margin: calc(var(--sp-3) * -1) 0 0;
    color: var(--accent-text);
    font-size: var(--fs-mono-sm);
  }
  .sk { height: 320px; border-radius: var(--r-3); background: var(--surf-2); opacity: 0.6; }
  .muted { margin: 0; color: var(--text-3); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }

  .story {
    margin: 0;
    padding: 0;
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: var(--sp-2);
    color: var(--text-1);
    font: var(--fs-body) / var(--lh-body) var(--font-ui);
  }
  .story li { padding-left: var(--sp-3); border-left: 2px solid var(--border-2); }
  .story li.first { border-left-color: var(--accent); }
  .order {
    margin: var(--sp-3) 0 0;
    padding: 0;
    list-style: none;
    display: flex;
    flex-direction: column;
    border: 1px solid var(--border-1);
    border-radius: var(--r-3);
    overflow: hidden;
  }
  .order li {
    display: grid;
    grid-template-columns: 28px minmax(0, 1fr) auto;
    gap: var(--sp-3);
    align-items: start;
    padding: var(--sp-3);
    border-top: 1px solid var(--border-1);
    animation: rise var(--dur-base) var(--ease-out) both;
  }
  .order li:first-child { border-top: 0; }
  .order li[data-first='true'] { background: var(--accent-soft); }
  @keyframes rise {
    from { opacity: 0; transform: translateY(3px); }
    to { opacity: 1; transform: none; }
  }
  .pos {
    display: grid;
    place-items: center;
    width: 24px;
    height: 24px;
    border-radius: var(--r-pill);
    background: var(--surf-2);
    color: var(--text-2);
    font-size: var(--fs-mono-sm);
  }
  li[data-first='true'] .pos { background: var(--accent); color: var(--on-accent); }
  .what { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .what b { color: var(--text-1); font: 600 var(--fs-body) / var(--lh-body) var(--font-ui); }
  .delta { color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); overflow-wrap: anywhere; }
  .at { display: flex; flex-direction: column; align-items: flex-end; color: var(--text-2); font-size: var(--fs-mono-sm); }
  .at em { font-style: normal; color: var(--accent-text); }
  .caveats {
    margin: var(--sp-3) 0 0;
    padding: 0 0 0 var(--sp-4);
    color: var(--text-3);
    font: var(--fs-caption) / var(--lh-caption) var(--font-ui);
  }

  .legend {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--sp-2) var(--sp-4);
    margin-top: var(--sp-4);
    padding-top: var(--sp-3);
    border-top: 1px solid var(--border-1);
    color: var(--text-2);
    font: var(--fs-caption) / var(--lh-caption) var(--font-ui);
  }
  .legend i { display: inline-block; width: 14px; height: 6px; margin-right: 6px; border-radius: 2px; vertical-align: middle; }
  .legend i[data-q='GOOD'] { background: var(--q-good); }
  .legend i[data-q='SIMULATED'] { background: var(--q-sim); }
  .legend i[data-q='UNCERTAIN'] { background: var(--q-uncertain); }
  .legend i[data-q='COMM_ERROR'] { background: var(--q-comm); }
  .legend i[data-q='BAD'] { background: var(--q-bad); }

  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  th, td { padding: var(--sp-2) var(--sp-2); border-bottom: 1px solid var(--border-1); text-align: left; }
  thead th { color: var(--text-3); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  tbody th { color: var(--text-1); font-weight: 500; }
  .u { margin-left: 6px; color: var(--text-3); font-weight: 400; }
  .r { text-align: right; }
  td.num { color: var(--text-1); font-size: var(--fs-mono); }
</style>
