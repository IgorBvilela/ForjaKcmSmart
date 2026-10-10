<script lang="ts">
  /** Ferramentas › Exportações: CSV das variáveis, dos eventos e dos registros do sistema.
   *  Toda linha leva a qualidade ao lado do valor; leitura sem valor sai vazia, nunca zero. */
  import Download from '@lucide/svelte/icons/download'
  import { api } from '../lib/api'
  import { live } from '../lib/live.svelte'
  import { resolvePeriod, type Period } from '../lib/period'
  import { reportsApi } from '../lib/reports'
  import { app } from '../lib/state.svelte'
  import PeriodPicker from '../components/data/PeriodPicker.svelte'
  import Card from '../components/ui/Card.svelte'

  const cards = $derived(live.plant)
  let equipmentId = $state(app.equipmentId ?? '')
  let period = $state<Period>({ kind: 'preset', preset: '24h' })
  let dialect = $state<'br' | 'std'>('br')
  let tags = $state<string[]>([])

  $effect(() => {
    if (!equipmentId && cards.length) equipmentId = cards[0].id
  })

  $effect(() => {
    const id = equipmentId
    if (!id) return
    void api.equipment(id).then((d) => {
      if (id === equipmentId) tags = d.mapping.readable_tags
    })
  })

  const iso = $derived.by(() => {
    const r = resolvePeriod(period, app.now)
    return { from: new Date(r.from).toISOString(), to: new Date(r.to).toISOString() }
  })
  const rawUrl = $derived(
    equipmentId && tags.length ? api.historyCsvUrl(equipmentId, { tags, ...iso, dialect, resolution: 'raw' }) : null,
  )
  const aggUrl = $derived(
    equipmentId && tags.length ? api.historyCsvUrl(equipmentId, { tags, ...iso, dialect, resolution: 'auto' }) : null,
  )
  const eventsUrl = $derived(equipmentId ? reportsApi.eventsCsvUrl(equipmentId, iso.from, iso.to, dialect) : null)
</script>

<section class="exp" data-testid="exports">
  <header class="head">
    <p class="label">Ferramentas</p>
    <h1 class="title">Exportações</h1>
    <p class="sub">
      Arquivos CSV para planilha ou análise. Toda linha leva o instante (UTC e horário da planta) e a
      qualidade ao lado do valor; leitura sem valor sai vazia, nunca como zero.
    </p>
  </header>

  <Card title="O que exportar" testid="exports-form">
    <div class="form">
      <label class="field">
        <span class="label">Equipamento</span>
        <select bind:value={equipmentId} data-testid="exports-equipment">
          {#each cards as c (c.id)}<option value={c.id}>{c.name}</option>{/each}
        </select>
      </label>
      <div class="field wide">
        <span class="label">Período</span>
        <PeriodPicker {period} now={app.now} onchange={(p) => (period = p)} testid="exports-period" />
      </div>
      <fieldset class="field">
        <legend class="label">Formato</legend>
        <label class="radio"><input type="radio" bind:group={dialect} value="br" /> Excel em português (; e vírgula)</label>
        <label class="radio"><input type="radio" bind:group={dialect} value="std" /> Padrão (, e ponto)</label>
      </fieldset>
    </div>
  </Card>

  <div class="files">
    <Card title="Variáveis: pontos gravados" kicker="um ponto por leitura gravada" testid="exports-raw">
      <p class="muted">{tags.length} variável(is) com endereço no mapping. Períodos muito longos pedem o resumo.</p>
      {#if rawUrl}<a class="btn primary" href={rawUrl} download data-testid="exports-raw-link"><Download size={16} aria-hidden="true" /> Baixar CSV</a>{/if}
    </Card>
    <Card title="Variáveis: resumo por intervalo" kicker="média, mínimo, máximo e pior qualidade" testid="exports-agg">
      <p class="muted">Bom para dias e semanas: um intervalo por linha, sem preencher buraco.</p>
      {#if aggUrl}<a class="btn primary" href={aggUrl} download data-testid="exports-agg-link"><Download size={16} aria-hidden="true" /> Baixar CSV</a>{/if}
    </Card>
    <Card title="Eventos e avisos" kicker="detectados pela Forja" testid="exports-events">
      <p class="muted">Uma linha por evento ou aviso: origem, duração, estado, primeira variável a sair do padrão.</p>
      {#if eventsUrl}<a class="btn primary" href={eventsUrl} download data-testid="exports-events-link"><Download size={16} aria-hidden="true" /> Baixar CSV</a>{/if}
    </Card>
    <Card title="Registros do sistema" kicker="serviço, comunicação e auditoria" testid="exports-logs">
      <p class="muted">O mesmo conteúdo de Sistema › Saúde e logs.</p>
      <a class="btn primary" href={reportsApi.logsCsvUrl()} download><Download size={16} aria-hidden="true" /> Baixar CSV</a>
    </Card>
  </div>
</section>

<style>
  .exp { display: flex; flex-direction: column; gap: var(--sp-5); }
  .head .label { margin: 0 0 var(--sp-1); }
  .title { margin: 0; color: var(--text-1); font: 600 var(--fs-h1) / var(--lh-h1) var(--font-ui); }
  @media (min-width: 1024px) {
    .title { font-size: var(--fs-display); line-height: var(--lh-display); }
  }
  .sub { margin: var(--sp-1) 0 0; max-width: 72ch; color: var(--text-2); font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  .form { display: grid; gap: var(--sp-3); grid-template-columns: 1fr; }
  @media (min-width: 1024px) {
    .form { grid-template-columns: minmax(0, 1fr) minmax(0, 2fr); }
    .form fieldset { grid-column: span 2; }
  }
  .field { display: flex; flex-direction: column; gap: var(--sp-1); min-width: 0; margin: 0; padding: 0; border: 0; }
  select {
    width: 100%;
    min-height: var(--touch);
    padding: var(--sp-2);
    border: 1px solid var(--border-input);
    border-radius: var(--r-2);
    background: var(--surf-2);
    color: var(--text-1);
    font: 16px / 1.3 var(--font-ui);
  }
  select:focus-visible { outline: none; box-shadow: var(--focus); }
  .radio { display: inline-flex; align-items: center; gap: var(--sp-2); min-height: var(--touch); color: var(--text-1); font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  .radio input { width: 24px; height: 24px; accent-color: var(--accent); }
  .files { display: grid; gap: var(--sp-4); grid-template-columns: 1fr; }
  @media (min-width: 768px) { .files { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
  .muted { margin: 0 0 var(--sp-3); color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--sp-2);
    min-height: var(--touch);
    padding: 0 var(--sp-4);
    border-radius: var(--r-3);
    font: 600 var(--fs-body) / 1.2 var(--font-ui);
    text-decoration: none;
    transition: transform var(--dur-micro) var(--ease-std);
  }
  .btn:active { transform: scale(0.97); }
  .btn.primary { border: 1px solid var(--accent); background: var(--accent); color: var(--on-accent); }
  .btn:focus-visible { outline: none; box-shadow: var(--focus); }
</style>
