<script lang="ts">
  /** Mais › Dados › Resumo do turno: uma folha para imprimir no fim do turno, com o tempo de cada
   *  dosador dentro do normal, fora do normal e sem dados (FORJA_RULE) e o que aconteceu. Os
   *  turnos vêm da configuração da planta; sem turno configurado, a tela pede o período. A folha é
   *  sempre clara, como no papel, e foi feita para caber numa página A4. */
  import { onMount } from 'svelte'
  import Printer from '@lucide/svelte/icons/printer'
  import TimeSplitBar from '../components/data/TimeSplitBar.svelte'
  import Badge from '../components/ui/Badge.svelte'
  import Button from '../components/ui/Button.svelte'
  import Disclosure from '../components/ui/Disclosure.svelte'
  import PageHeader from '../components/ui/PageHeader.svelte'
  import { errorMessage } from '../lib/api'
  import { live } from '../lib/live.svelte'
  import { plantTitle } from '../lib/plant'
  import {
    localInputValue,
    shiftApi,
    type ShiftsResponse,
    type ShiftSummary,
    type ShiftSummaryItem,
  } from '../lib/shift'
  import { hoursText, pctText } from '../lib/timesplit'

  /** Sem turnos configurados, o período sugerido é o das últimas 8 h. */
  const DEFAULT_SPAN_MS = 8 * 3600_000
  /** Turno em andamento: a folha se atualiza a cada minuto até a impressão. */
  const REFRESH_MS = 60_000

  let config = $state<ShiftsResponse | null>(null)
  let configError = $state<string | null>(null)
  let day = $state('')
  let index = $state<number | null>(null)
  let from = $state('')
  let to = $state('')
  let sheet = $state<ShiftSummary | null>(null)
  let loading = $state(false)
  let error = $state<string | null>(null)
  let seq = 0

  const hasShifts = $derived((config?.shifts.length ?? 0) > 0)
  const rangeOk = $derived(Boolean(from && to) && new Date(to).getTime() > new Date(from).getTime())
  const title = $derived(plantTitle(live.plant, 'Forja KCM'))
  const tz = $derived(sheet?.timezone ?? config?.timezone)
  const items = $derived(sheet?.equipments ?? [])
  /** Linhas de ocorrência por cartão: menos linhas quando há mais dosadores (uma página só). */
  const maxLines = $derived(items.length <= 4 ? 6 : items.length <= 8 ? 4 : 3)
  const printCols = $derived(items.length <= 4 ? 2 : 3)

  onMount(() => {
    void loadConfig()
  })

  async function loadConfig(): Promise<void> {
    try {
      const res = await shiftApi.shifts()
      config = res
      if (res.shifts.length) {
        day = res.current?.date ?? res.today
        index = res.current?.index ?? 0
      } else {
        const now = new Date()
        to = localInputValue(now)
        from = localInputValue(new Date(now.getTime() - DEFAULT_SPAN_MS))
      }
    } catch (err) {
      configError = errorMessage(err)
    }
  }

  async function load(): Promise<void> {
    const mine = ++seq
    loading = true
    try {
      const res =
        hasShifts && index != null
          ? await shiftApi.byShift(index, day)
          : await shiftApi.byPeriod(new Date(from), new Date(to))
      if (mine !== seq) return
      sheet = res
      error = null
    } catch (err) {
      if (mine !== seq) return
      sheet = null
      error = errorMessage(err)
    } finally {
      if (mine === seq) loading = false
    }
  }

  // Monta a folha a cada escolha válida (com uma pausa curta enquanto se digita a data).
  $effect(() => {
    if (!config) return
    const ready = hasShifts ? index != null && /^\d{4}-\d{2}-\d{2}$/.test(day) : rangeOk
    void [index, day, from, to]
    if (!ready) {
      sheet = null
      error = null
      return
    }
    const id = window.setTimeout(() => void load(), 250)
    return () => window.clearTimeout(id)
  })

  $effect(() => {
    if (!sheet?.in_progress) return
    const id = window.setInterval(() => void load(), REFRESH_MS)
    return () => window.clearInterval(id)
  })

  function fmt(iso: string, opts: Intl.DateTimeFormatOptions): string {
    return new Intl.DateTimeFormat('pt-BR', { ...opts, timeZone: tz }).format(new Date(iso))
  }
  const clock = (iso: string): string => fmt(iso, { hour: '2-digit', minute: '2-digit' })
  const dateTime = (iso: string): string =>
    fmt(iso, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
  /** "11 de out. de 2026" a partir de AAAA-MM-DD, sem trocar de dia por fuso. */
  function longDate(ymd: string): string {
    return new Intl.DateTimeFormat('pt-BR', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(
      new Date(`${ymd}T12:00:00Z`),
    )
  }

  const period = $derived.by(() => {
    if (!sheet) return ''
    if (sheet.shift && sheet.date) {
      return `${sheet.shift.name} · ${sheet.shift.start} às ${sheet.shift.end} · ${longDate(sheet.date)}`
    }
    return `${dateTime(sheet.from_utc)} até ${dateTime(sheet.to_utc)}`
  })

  const SOURCE_PT = { SIMULATED: 'Dados simulados', EQUIPMENT: 'Dados do equipamento', MIXED: 'Dados simulados e do equipamento' } as const

  interface Line {
    key: string
    when: string
    text: string
  }

  /** Hora do evento; o que já estava aberto antes do período leva "desde" e a data. */
  function startText(iso: string): string {
    if (!sheet || Date.parse(iso) >= Date.parse(sheet.from_utc)) return clock(iso)
    return `desde ${fmt(iso, { day: '2-digit', month: '2-digit' })} ${clock(iso)}`
  }

  /** Eventos da Forja e alarmes do KCM do dosador, na ordem do tempo. */
  function linesOf(item: ShiftSummaryItem): Line[] {
    const events: Line[] = item.events.map((e) => ({ key: e.id, when: e.start_utc, text: `${startText(e.start_utc)} ${e.title_pt}` }))
    const alarms: Line[] = item.kcm_alarms.map((a) => ({
      key: `kcm-${a.code}`,
      when: a.first_utc,
      text: `${clock(a.first_utc)} Alarme do KCM ${a.code} · ${a.title_pt}${a.times > 1 ? ` (${a.times} vezes)` : ''}`,
    }))
    return [...events, ...alarms].sort((a, b) => a.when.localeCompare(b.when))
  }

  function hiddenCount(item: ShiftSummaryItem, shown: number): number {
    return item.events_total - item.events.length + Math.max(0, item.events.length + item.kcm_alarms.length - shown)
  }

  function barLabel(item: ShiftSummaryItem): string {
    return (
      `${item.name}: ${pctText(item.normal_pct)}% dentro do normal, ` +
      `${pctText(item.out_pct)}% fora do normal e ${pctText(item.no_data_pct)}% sem dados`
    )
  }
</script>

<section class="shift" data-testid="shift-summary" aria-labelledby="shift-title">
  <PageHeader
    kicker="Dados"
    title="Resumo do turno"
    titleId="shift-title"
    lead="Uma folha para imprimir no fim do turno, com o tempo de cada dosador e o que aconteceu."
    noPrint
  >
    {#snippet more()}
      <p>{sheet?.definition_pt ?? 'Sem dados: sem leitura válida. Fora do normal: evento da Forja aberto (atenção para cima) ou alarme do KCM ativo. Dentro do normal: o resto do tempo com dado.'}</p>
      <p>Os horários dos turnos vêm da configuração da planta. A folha sai sempre clara e foi feita para caber numa página A4.</p>
    {/snippet}
    {#snippet actions()}
      <Button variant="primary" disabled={!sheet} onclick={() => window.print()} testid="shift-print">
        <Printer size={16} aria-hidden="true" /> Imprimir
      </Button>
    {/snippet}
  </PageHeader>

  <div class="sh-controls no-print" data-testid="shift-controls">
    {#if configError}
      <p class="err" role="alert">{configError}</p>
    {:else if !config}
      <p class="muted">Lendo os turnos da planta…</p>
    {:else if hasShifts}
      <div class="row">
        <label class="field date">
          <span class="label">Data em que o turno começa</span>
          <input type="date" bind:value={day} max={config.today} data-testid="shift-date" />
        </label>
        <div class="field">
          <span class="label" id="shift-pick">Turno</span>
          <div class="chips" role="group" aria-labelledby="shift-pick">
            {#each config.shifts as s (s.index)}
              <Button variant={index === s.index ? 'primary' : 'ghost'} pressed={index === s.index} onclick={() => (index = s.index)} testid={`shift-chip-${s.index}`}>
                {s.name} · <span class="num">{s.start}–{s.end}</span>
              </Button>
            {/each}
          </div>
        </div>
      </div>
    {:else}
      <p class="notice" data-testid="shift-not-configured">Os turnos da planta ainda não foram configurados. Escolha o início e o fim.</p>
      <div class="range">
        <label class="field">
          <span class="label">Início</span>
          <input type="datetime-local" bind:value={from} aria-invalid={!rangeOk} data-testid="shift-from" />
        </label>
        <label class="field">
          <span class="label">Fim</span>
          <input type="datetime-local" bind:value={to} aria-invalid={!rangeOk} data-testid="shift-to" />
        </label>
      </div>
      {#if !rangeOk}<p class="err" role="alert" data-testid="shift-range-error">O fim precisa ser depois do início.</p>{/if}
      <Disclosure summary="Detalhes técnicos" size="sm">
        <p class="muted">Os turnos ficam em <code>config/forja.yaml</code>, seção <code>plant.shifts</code>: nome, início e fim (HH:MM), no fuso da planta.</p>
      </Disclosure>
    {/if}
  </div>

  {#if error}
    <p class="err sheet-err" role="alert" data-testid="shift-error">{error}</p>
  {/if}

  {#if sheet}
    <article
      class="sheet surface-light"
      class:busy={loading}
      aria-busy={loading}
      aria-labelledby="sheet-title"
      data-testid="shift-sheet"
      style:--print-cols={printCols}
    >
      <header class="s-head">
        <div class="s-id">
          <p class="s-kicker">Forja KCM Intelligence · somente leitura</p>
          <h2 class="s-title" id="sheet-title">Resumo do turno · {title}</h2>
          <p class="s-period" data-testid="shift-period">
            {period}{#if sheet.in_progress}<span class="s-live" data-testid="shift-in-progress"> · em andamento, até {clock(sheet.to_utc)}</span>{/if}
          </p>
          <p class="s-emitted">Emitido em {dateTime(sheet.generated_at_utc)}</p>
        </div>
        <div class="s-side">
          {#if sheet.data_source}
            <Badge tone={sheet.data_source === 'EQUIPMENT' ? 'neutral' : 'sim'} hatch={sheet.data_source !== 'EQUIPMENT'} testid="shift-source">
              {SOURCE_PT[sheet.data_source]}
            </Badge>
          {/if}
          <p class="legend" aria-hidden="true">
            <span class="sw ok"></span>dentro <span class="sw out"></span>fora <span class="sw none"></span>sem dados
          </p>
        </div>
      </header>

      {#if items.length === 0}
        <p class="muted">Nenhum dosador configurado.</p>
      {:else}
        <div class="cards">
          {#each items as item (item.id)}
            {@const lines = linesOf(item)}
            {@const hidden = hiddenCount(item, maxLines)}
            <section class="card" data-testid={`shift-card-${item.id}`} aria-label={item.name}>
              <h3 class="c-name">
                {item.name}
                {#if sheet.data_source === 'MIXED' && item.data_source === 'SIMULATED'}<span class="c-sim">Simulado</span>{/if}
              </h3>
              <TimeSplitBar normal={item.normal_pct} out={item.out_pct} noData={item.no_data_pct} height={8} label={barLabel(item)} />
              <dl class="parts">
                <div><dt>Dentro do normal</dt><dd><b class="num">{pctText(item.normal_pct)}%</b> <span>{hoursText(item.normal_s)}</span></dd></div>
                <div><dt>Fora do normal</dt><dd><b class="num">{pctText(item.out_pct)}%</b> <span>{hoursText(item.out_s)}</span></dd></div>
                <div><dt>Sem dados</dt><dd><b class="num">{pctText(item.no_data_pct)}%</b> <span>{hoursText(item.no_data_s)}</span></dd></div>
              </dl>
              {#if lines.length}
                <ul class="lines" data-testid="shift-lines">
                  {#each lines.slice(0, maxLines) as line (line.key)}<li>{line.text}</li>{/each}
                  {#if hidden > 0}<li class="more">e mais {hidden}</li>{/if}
                </ul>
              {:else}
                <p class="none">Nenhum evento da Forja nem alarme do KCM no período.</p>
              {/if}
              {#if item.early_warnings}
                <p class="warnings">Avisos antecipados: <span class="num">{item.early_warnings}</span> (contados à parte)</p>
              {/if}
            </section>
          {/each}
        </div>
      {/if}

      <section class="handwrite" aria-label="Observações">
        <p class="hw-label">Observações</p>
        <i></i><i></i><i></i>
      </section>
      <section class="sign" aria-label="Assinatura" data-testid="shift-signature">
        <span>Responsável pelo turno</span><i></i>
        <span>Data e hora</span><i></i>
      </section>
      <footer class="s-foot">
        <p>{sheet.definition_pt} Classificação: regra da Forja.</p>
        <p>A Forja observa o KCM e não comanda nada.</p>
      </footer>
    </article>
  {/if}
</section>

<style>
  .shift { display: flex; flex-direction: column; gap: var(--sp-5); }
  .sh-controls {
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: var(--sp-3);
    padding: var(--sp-4);
    border: 1px solid var(--border-1);
    border-radius: var(--r-4);
    background: var(--surf-1);
  }
  .field { display: flex; flex-direction: column; gap: var(--sp-1); min-width: 0; }
  .row { display: flex; flex-wrap: wrap; align-items: flex-end; gap: var(--sp-3) var(--sp-5); }
  .date { width: min(240px, 100%); }
  .range { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(220px, 100%), 280px)); gap: var(--sp-3); }
  .chips { display: flex; flex-wrap: wrap; gap: var(--sp-2); }
  input {
    width: 100%;
    min-height: var(--touch);
    padding: var(--sp-2) var(--sp-3);
    border: 1px solid var(--border-input);
    border-radius: var(--r-2);
    background: var(--surf-2);
    color: var(--text-1);
    font: 16px / 1.3 var(--font-ui);
  }
  input[aria-invalid='true'] { border-color: var(--st-crit); }
  input:focus-visible { outline: none; box-shadow: var(--focus); }
  .notice { margin: 0; color: var(--text-1); }
  .muted { margin: 0; color: var(--text-2); }
  .err { margin: 0; color: var(--st-crit); font: 500 var(--fs-body) / var(--lh-body) var(--font-ui); }
  code { font: var(--fs-mono) / var(--lh-mono) var(--font-mono); }

  /* ---- a folha: sempre clara, como no papel ---- */
  .sheet {
    display: flex;
    flex-direction: column;
    gap: var(--sp-4);
    width: 100%;
    max-width: 860px;
    padding: var(--sp-6);
    border-radius: var(--r-2);
    background: var(--surf-1);
    color: var(--text-1);
    box-shadow: 0 0 0 1px var(--border-2);
    font: var(--fs-body) / var(--lh-body) var(--font-ui);
    transition: opacity var(--dur-base) var(--ease-std);
    animation: rise var(--dur-screen) var(--ease-out);
  }
  .sheet.busy { opacity: 0.7; }
  @keyframes rise {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: none; }
  }
  .s-head { display: flex; flex-wrap: wrap; justify-content: space-between; gap: var(--sp-3); padding-bottom: var(--sp-3); border-bottom: 2px solid var(--text-1); }
  .s-id { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .s-kicker, .s-emitted { margin: 0; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .s-title { margin: 0; font: 600 20px / 1.25 var(--font-ui); }
  .s-period { margin: 0; color: var(--text-1); font: 500 var(--fs-body) / var(--lh-body) var(--font-ui); }
  .s-live { color: var(--st-warn); }
  .s-side { display: flex; flex-direction: column; align-items: flex-end; gap: var(--sp-2); }
  .legend { display: flex; align-items: center; gap: 6px; margin: 0; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .sw { display: inline-block; width: 14px; height: 7px; border-radius: var(--r-pill); }
  .sw.ok { background: var(--st-ok); }
  .sw.out { margin-left: 6px; background: var(--st-warn); }
  .sw.none { margin-left: 6px; background: repeating-linear-gradient(135deg, var(--text-3) 0 3px, transparent 3px 6px); box-shadow: inset 0 0 0 1px var(--text-3); }

  .cards { display: grid; gap: var(--sp-3); grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }
  .card {
    display: flex;
    flex-direction: column;
    gap: var(--sp-2);
    min-width: 0;
    padding: var(--sp-3);
    border: 1px solid var(--border-2);
    border-radius: var(--r-3);
    break-inside: avoid;
  }
  .c-name { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--sp-2); margin: 0; font: 600 var(--fs-body-lg) / 1.3 var(--font-ui); }
  .c-sim { color: var(--q-sim); font: 600 var(--fs-caption) / 1 var(--font-ui); letter-spacing: var(--ls-label); text-transform: uppercase; }
  /* rótulo que quebra em duas linhas não desalinha os números: as três colunas dividem as linhas */
  .parts { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); grid-template-rows: auto auto; column-gap: var(--sp-2); margin: 0; }
  .parts div { display: grid; grid-row: span 2; grid-template-rows: subgrid; min-width: 0; }
  .parts dt { align-self: end; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .parts dd { display: flex; flex-direction: column; margin: 0; font: var(--fs-caption) / var(--lh-caption) var(--font-ui); font-variant-numeric: tabular-nums; }
  .parts b { color: var(--text-1); font-size: 15px; }
  .parts dd span { color: var(--text-2); white-space: nowrap; }
  .lines { margin: 0; padding-left: var(--sp-4); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .lines .more { color: var(--text-2); list-style: none; margin-left: calc(-1 * var(--sp-4)); }
  .none, .warnings { margin: 0; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }

  .handwrite { display: flex; flex-direction: column; gap: var(--sp-5); }
  .hw-label { margin: 0; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .handwrite i, .sign i { display: block; height: 1px; background: var(--border-input); }
  .sign { display: grid; grid-template-columns: auto minmax(0, 1fr) auto minmax(0, 1fr); align-items: end; gap: var(--sp-3); padding-top: var(--sp-2); color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .s-foot { display: flex; flex-direction: column; gap: 2px; padding-top: var(--sp-2); border-top: 1px solid var(--border-2); }
  .s-foot p { margin: 0; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }

  @media (max-width: 599px) {
    .sheet { padding: var(--sp-4); }
    .s-side { align-items: flex-start; }
    .sign { grid-template-columns: auto minmax(0, 1fr); }
  }
  @media (prefers-reduced-motion: reduce) {
    .sheet { animation: none; }
  }

  /* ---- papel: página A4 com nome próprio (só esta folha), colunas pelo número de dosadores ---- */
  @media print {
    .shift { display: block; }
    .sheet { max-width: none; padding: 0; border-radius: 0; box-shadow: none; page: resumo-turno; gap: 10px; }
    .cards { grid-template-columns: repeat(var(--print-cols), minmax(0, 1fr)); gap: 8px; }
    .card { padding: 8px; }
    .handwrite { gap: 22px; }
    .err, .sheet-err { display: none; }
  }
</style>
