<script lang="ts">
  /** Ferramentas › Relatórios: relatório por período de um equipamento, para ler ou imprimir.
   *  Mostra só o que foi gravado: qualidade do dado no tempo, eventos e avisos, alarmes do KCM. */
  import FileText from '@lucide/svelte/icons/file-text'
  import Printer from '@lucide/svelte/icons/printer'
  import { errorMessage, severityTone } from '../lib/api'
  import { fmtDateTime, fmtDuration, fmtNumber } from '../lib/format'
  import { live } from '../lib/live.svelte'
  import { resolvePeriod, type Period } from '../lib/period'
  import { reportsApi, type PeriodReport } from '../lib/reports'
  import { href } from '../lib/router'
  import { app } from '../lib/state.svelte'
  import PeriodPicker from '../components/data/PeriodPicker.svelte'
  import Badge from '../components/ui/Badge.svelte'
  import Card from '../components/ui/Card.svelte'
  import EmptyState from '../components/ui/EmptyState.svelte'

  const cards = $derived(live.plant)
  let equipmentId = $state(app.equipmentId ?? '')
  let period = $state<Period>({ kind: 'preset', preset: '24h' })
  let report = $state<PeriodReport | null>(null)
  let loading = $state(false)
  let error = $state<string | null>(null)

  $effect(() => {
    if (!equipmentId && cards.length) equipmentId = cards[0].id
  })

  async function generate(): Promise<void> {
    if (!equipmentId) return
    const { from, to } = resolvePeriod(period, Date.now())
    loading = true
    error = null
    try {
      report = await reportsApi.report(equipmentId, new Date(from).toISOString(), new Date(to).toISOString())
    } catch (err) {
      error = errorMessage(err)
      report = null
    } finally {
      loading = false
    }
  }

  function pct(v: number): string {
    return `${fmtNumber(v * 100, 1)}%`
  }
</script>

<section class="rep" data-testid="reports">
  <header class="head no-print">
    <p class="label">Ferramentas</p>
    <h1 class="title">Relatórios</h1>
    <p class="sub">
      Relatório por período de um equipamento: qualidade do dado no tempo, eventos e avisos da Forja e
      alarmes que o KCM informou. Pode ser impresso ou salvo em PDF pelo navegador.
    </p>
  </header>

  <Card title="Período e equipamento" class="no-print" testid="reports-form">
    <div class="form">
      <label class="field">
        <span class="label">Equipamento</span>
        <select bind:value={equipmentId} data-testid="reports-equipment">
          {#each cards as c (c.id)}<option value={c.id}>{c.name}</option>{/each}
        </select>
      </label>
      <div class="field wide">
        <span class="label">Período</span>
        <PeriodPicker {period} now={app.now} onchange={(p) => (period = p)} testid="reports-period" />
      </div>
    </div>
    <div class="actions">
      <button class="btn primary" type="button" disabled={loading || !equipmentId} onclick={generate} data-testid="reports-generate">
        <FileText size={16} aria-hidden="true" /> {loading ? 'Montando…' : 'Gerar relatório'}
      </button>
      {#if report}
        <button class="btn ghost" type="button" onclick={() => window.print()}>
          <Printer size={16} aria-hidden="true" /> Imprimir ou salvar em PDF
        </button>
      {/if}
    </div>
    {#if error}<p class="err" role="alert">{error}</p>{/if}
  </Card>

  {#if report}
    <article class="doc" data-testid="report-doc">
      <header class="doc-head">
        <p class="label">Relatório do período · Forja KCM Intelligence · somente leitura</p>
        <h2 class="doc-title">{report.name}</h2>
        <p class="muted">{report.display_path} · {report.application === 'UNKNOWN' ? 'aplicação não confirmada' : report.application}</p>
        <p class="muted">
          De <span class="num">{fmtDateTime(report.from_utc)}</span> a <span class="num">{fmtDateTime(report.to_utc)}</span>
          ({report.period_pt}) · gerado em <span class="num">{fmtDateTime(report.generated_at_utc)}</span>
        </p>
        {#if report.data_source === 'SIMULATED'}<Badge tone="sim" hatch>Dados simulados</Badge>{/if}
      </header>

      <section class="block" data-testid="report-summary">
        <h3 class="label">Resumo</h3>
        <ul class="summary">{#each report.narrative_pt as line (line)}<li>{line}</li>{/each}</ul>
      </section>

      <section class="block">
        <h3 class="label">Qualidade do dado no período</h3>
        <table class="resp">
          <thead><tr><th>Variável</th><th>Leitura no período</th><th>Média</th><th>Mínimo</th><th>Máximo</th></tr></thead>
          <tbody>
            {#each report.tags as t (t.tag)}
              <tr>
                <th data-label="Variável">{t.label_pt}</th>
                <td data-label="Leitura no período" class="wide">
                  <span class="bar" style:--v={t.coverage} data-low={t.coverage < 0.95}><span></span></span>
                  <span class="num">{pct(t.coverage)}</span>
                </td>
                <td data-label="Média" class="num">{t.average == null ? '—' : fmtNumber(t.average, t.decimals)} {t.unit}</td>
                <td data-label="Mínimo" class="num">{t.min == null ? '—' : fmtNumber(t.min, t.decimals)}</td>
                <td data-label="Máximo" class="num">{t.max == null ? '—' : fmtNumber(t.max, t.decimals)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </section>

      <section class="block">
        <h3 class="label">Eventos e avisos por tipo</h3>
        {#if report.event_groups.length === 0}
          <p class="muted">Nenhum evento nem aviso no período.</p>
        {:else}
          <table class="resp">
            <thead><tr><th>Tipo</th><th>Origem</th><th>Ocorrências</th><th>Tempo no período</th></tr></thead>
            <tbody>
              {#each report.event_groups as g (g.origin + g.type)}
                <tr>
                  <th data-label="Tipo"><Badge tone={severityTone(g.worst_severity)}>{g.title_pt}</Badge></th>
                  <td data-label="Origem">{g.origin_pt}</td>
                  <td data-label="Ocorrências" class="num">{g.count}</td>
                  <td data-label="Tempo no período" class="num">{fmtDuration(g.duration_in_period_s)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </section>

      {#if report.events.length}
        <section class="block">
          <h3 class="label">Eventos e avisos ({report.events_total})</h3>
          <table class="resp">
            <thead><tr><th>Início</th><th>Título</th><th>Duração</th><th>Saiu primeiro</th><th>Estado</th></tr></thead>
            <tbody>
              {#each report.events as e (e.id)}
                <tr>
                  <th data-label="Início" class="num">{fmtDateTime(e.start_utc)}</th>
                  <td data-label="Título" class="wide"><a class="inline no-print-link" href={href.event(report.equipment_id, e.id)}>{e.title_pt}</a><span class="muted">{e.origin_pt}</span></td>
                  <td data-label="Duração" class="num">{fmtDuration(e.duration_in_period_s)}{e.end_utc ? '' : ' (em aberto)'}</td>
                  <td data-label="Saiu primeiro">{e.first_label_pt ?? '—'}</td>
                  <td data-label="Estado">{e.acked_by ? `reconhecido por ${e.acked_by}` : e.status === 'OPEN' ? 'aberto' : 'encerrado'}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </section>
      {/if}

      <section class="block">
        <h3 class="label">Alarmes informados pelo KCM</h3>
        {#if report.kcm_alarms.length === 0}
          <p class="muted">Nenhum alarme informado no período (ou o mapping não traz o alarme).</p>
        {:else}
          <table class="resp">
            <thead><tr><th>Código</th><th>Significado (catálogo)</th><th>Vezes</th><th>Primeira</th><th>Última</th></tr></thead>
            <tbody>
              {#each report.kcm_alarms as a (a.code)}
                <tr>
                  <th data-label="Código" class="num">{a.code}</th>
                  <td data-label="Significado" class="wide">{a.title_pt}<span class="muted">{a.qualifier_pt}</span></td>
                  <td data-label="Vezes" class="num">{a.times}</td>
                  <td data-label="Primeira" class="num">{fmtDateTime(a.first_utc)}</td>
                  <td data-label="Última" class="num">{fmtDateTime(a.last_utc)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </section>

      <section class="block">
        <h3 class="label">Ressalvas</h3>
        <ul class="summary small">{#each report.caveats_pt as c (c)}<li>{c}</li>{/each}</ul>
      </section>
    </article>
  {:else if !loading}
    <EmptyState title="Escolha o equipamento e o período" text="O relatório usa só o que a Forja gravou neste Edge." />
  {/if}
</section>

<style>
  .rep { display: flex; flex-direction: column; gap: var(--sp-5); }
  .head .label { margin: 0 0 var(--sp-1); }
  .title { margin: 0; color: var(--text-1); font: 600 var(--fs-h1) / var(--lh-h1) var(--font-ui); }
  @media (min-width: 1024px) {
    .title { font-size: var(--fs-display); line-height: var(--lh-display); }
  }
  .sub { margin: var(--sp-1) 0 0; max-width: 72ch; color: var(--text-2); font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  .form { display: grid; gap: var(--sp-3); grid-template-columns: 1fr; }
  @media (min-width: 1024px) { .form { grid-template-columns: minmax(0, 1fr) minmax(0, 2fr); } }
  .field { display: flex; flex-direction: column; gap: var(--sp-1); min-width: 0; }
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
  .actions { display: flex; flex-wrap: wrap; gap: var(--sp-2); margin-top: var(--sp-3); }
  .err { margin: var(--sp-2) 0 0; color: var(--st-crit); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .doc {
    display: flex;
    flex-direction: column;
    gap: var(--sp-5);
    padding: var(--sp-5);
    border: 1px solid var(--border-1);
    border-radius: var(--r-4);
    background: var(--surf-1);
    animation: rise var(--dur-screen) var(--ease-out);
  }
  @keyframes rise {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: none; }
  }
  .doc-head { display: flex; flex-direction: column; gap: var(--sp-1); align-items: flex-start; }
  .doc-title { margin: 0; color: var(--text-1); font: 600 var(--fs-h1) / var(--lh-h1) var(--font-ui); }
  .muted { display: block; margin: 0; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .num { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
  .block h3 { margin: 0 0 var(--sp-2); }
  .summary { margin: 0; padding-left: var(--sp-5); color: var(--text-1); font: var(--fs-body-lg) / var(--lh-body-lg) var(--font-ui); }
  .summary.small { font-size: var(--fs-caption); line-height: var(--lh-caption); color: var(--text-2); }
  table { width: 100%; border-collapse: collapse; font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  th, td { padding: var(--sp-2); border-bottom: 1px solid var(--border-1); text-align: left; vertical-align: top; color: var(--text-1); }
  thead th { color: var(--text-2); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .bar {
    display: inline-block;
    width: 120px;
    height: 8px;
    margin-right: var(--sp-2);
    border-radius: var(--r-pill);
    background: var(--surf-3);
    overflow: hidden;
    vertical-align: middle;
  }
  .bar > span {
    display: block;
    height: 100%;
    width: calc(var(--v) * 100%);
    background: var(--st-ok);
    border-radius: inherit;
    transform-origin: left;
    animation: grow var(--dur-draw) var(--ease-out);
  }
  .bar[data-low='true'] > span { background: var(--st-warn); }
  @keyframes grow {
    from { transform: scaleX(0); }
    to { transform: scaleX(1); }
  }
  .inline { color: var(--accent-text); text-decoration: underline; }
  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--sp-2);
    min-height: var(--touch);
    padding: 0 var(--sp-4);
    border-radius: var(--r-3);
    font: 600 var(--fs-body) / 1.2 var(--font-ui);
    cursor: pointer;
    transition: transform var(--dur-micro) var(--ease-std);
  }
  .btn:active:not(:disabled) { transform: scale(0.97); }
  .btn:disabled { opacity: 0.55; cursor: not-allowed; }
  .btn.primary { border: 1px solid var(--accent); background: var(--accent); color: var(--on-accent); }
  .btn.ghost { border: 1px solid var(--border-2); background: var(--surf-1); color: var(--text-1); }
  .btn:focus-visible { outline: none; box-shadow: var(--focus); }
  @media print {
    .doc { border: 0; padding: 0; }
    .no-print-link { color: inherit; text-decoration: none; }
  }
</style>
