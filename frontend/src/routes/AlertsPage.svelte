<script lang="ts">
  /** Alertas: condições abertas agora, separadas por quem informou. O alarme é do KCM; eventos e
   *  avisos antecipados são da Forja. Reconhecer na Forja só registra quem viu (auditado). */
  import { untrack } from 'svelte'
  import Bell from '@lucide/svelte/icons/bell'
  import Radar from '@lucide/svelte/icons/radar'
  import Siren from '@lucide/svelte/icons/siren'
  import { errorMessage, severityTone, type EventView } from '../lib/api'
  import { fmtDateTime, fmtWhen } from '../lib/format'
  import { intelligenceApi, KCM_ALARM_TONE, type AlertsResponse } from '../lib/intelligence'
  import { live } from '../lib/live.svelte'
  import { href } from '../lib/router'
  import { app } from '../lib/state.svelte'
  import AckForm from '../components/data/AckForm.svelte'
  import Badge from '../components/ui/Badge.svelte'
  import Card from '../components/ui/Card.svelte'
  import EmptyState from '../components/ui/EmptyState.svelte'
  import QualityBadge from '../components/ui/QualityBadge.svelte'
  import StatusDot from '../components/ui/StatusDot.svelte'

  let { equipmentId }: { equipmentId: string } = $props()

  const REFRESH_MS = 5000
  let data = $state<AlertsResponse | null>(null)
  let error = $state<string | null>(null)

  const name = $derived(data?.name ?? live.cardOf(equipmentId)?.name ?? equipmentId)
  const kcm = $derived(data?.kcm_alarm ?? null)
  const kcmValue = $derived(
    !kcm
      ? '—'
      : kcm.state === 'ACTIVE'
        ? 'Ativo'
        : kcm.state === 'NONE'
          ? 'Nenhum'
          : kcm.state === 'UNKNOWN'
            ? 'Desconhecido'
            : 'Não mapeado',
  )
  const unack = $derived(data ? data.forja_events.filter((e) => e.status === 'OPEN').length : 0)

  async function load(id: string): Promise<void> {
    try {
      const r = await intelligenceApi.alerts(id)
      if (id !== equipmentId) return
      data = r
      error = null
    } catch (err) {
      if (id === equipmentId) error = errorMessage(err)
    }
  }

  $effect(() => {
    const id = equipmentId
    void live.eventsVersion
    untrack(() => void load(id))
  })

  $effect(() => {
    const id = equipmentId
    const timer = setInterval(() => void load(id), REFRESH_MS)
    return () => clearInterval(timer)
  })

  function replaced(updated: EventView): void {
    if (!data) return
    const swap = (list: EventView[]) => list.map((e) => (e.id === updated.id ? updated : e))
    data = { ...data, forja_events: swap(data.forja_events), early_warnings: swap(data.early_warnings) }
  }

  function goTo(id: string): void {
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    document.getElementById(id)?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' })
  }
</script>

<section class="alerts" data-testid="alerts">
  <header class="head">
    <p class="label">{name}</p>
    <h1 class="title">Alertas</h1>
    <p class="sub">
      Condições abertas agora, separadas por quem as informou. O alarme é do KCM; eventos e avisos
      antecipados são detectados pela Forja.
    </p>
  </header>

  {#if error && !data}
    <EmptyState title="Não foi possível carregar os alertas" text={error} />
  {:else if !data}
    <div class="tiles skeleton" aria-busy="true" aria-label="Carregando alertas">
      <div class="sk"></div><div class="sk"></div><div class="sk"></div>
    </div>
  {:else}
    <div class="tiles" role="group" aria-label="Resumo dos alertas">
      <button class="tile" type="button" data-tone={KCM_ALARM_TONE[data.kcm_alarm.state]} onclick={() => goTo('alerts-kcm')} data-testid="alerts-tile-kcm">
        <span class="tile-icon" aria-hidden="true"><Siren size={18} /></span>
        <span class="tile-label">Alarme do KCM</span>
        <span class="tile-value">{kcmValue}</span>
      </button>
      <button class="tile" type="button" data-tone={data.counts.forja_events ? (unack ? 'warn' : 'info') : 'ok'} onclick={() => goTo('alerts-forja')} data-testid="alerts-tile-forja">
        <span class="tile-icon" aria-hidden="true"><Bell size={18} /></span>
        <span class="tile-label">Eventos da Forja</span>
        <span class="tile-value num">{data.counts.forja_events}</span>
        <span class="tile-meta">{unack} sem reconhecimento</span>
      </button>
      <button class="tile" type="button" data-tone={data.counts.early_warnings ? 'warn' : 'ok'} onclick={() => goTo('alerts-ew')} data-testid="alerts-tile-ew">
        <span class="tile-icon" aria-hidden="true"><Radar size={18} /></span>
        <span class="tile-label">Avisos antecipados</span>
        <span class="tile-value num">{data.counts.early_warnings}</span>
      </button>
    </div>

    <div id="alerts-kcm" class="anchor">
      <Card title="Alarme do KCM" kicker="informado pelo KCM" testid="alerts-kcm">
        <div class="kcm" data-state={data.kcm_alarm.state}>
          <span class="kcm-dot">
            <StatusDot state={KCM_ALARM_TONE[data.kcm_alarm.state]} size={12} pulse={data.kcm_alarm.state === 'ACTIVE'} />
          </span>
          <div class="kcm-body">
            <p class="kcm-state">{data.kcm_alarm.state_pt}</p>
            {#if data.kcm_alarm.state === 'ACTIVE' && data.kcm_alarm.code}
              <p class="kcm-line">
                <span class="code num">Código {data.kcm_alarm.code}</span>
                {#if data.kcm_alarm.qualifier_pt}
                  <Badge tone={data.kcm_alarm.catalogued ? 'info' : 'unknown'}>{data.kcm_alarm.qualifier_pt}</Badge>
                {/if}
              </p>
            {/if}
            {#if data.kcm_alarm.since_utc && data.kcm_alarm.state === 'ACTIVE'}
              <p class="muted">Leitura de {fmtDateTime(data.kcm_alarm.since_utc)}</p>
            {/if}
            {#if data.kcm_alarm.quality}
              <QualityBadge quality={data.kcm_alarm.quality} qualityPt={data.kcm_alarm.quality_pt ?? null} />
            {/if}
          </div>
        </div>
        <p class="note">{data.kcm_alarm.note_pt}</p>
      </Card>
    </div>

    <div id="alerts-forja" class="anchor">
      <Card title="Eventos detectados pela Forja" kicker="regras determinísticas" testid="alerts-forja">
        <p class="note top">{data.notes_pt.forja}</p>
        {#if data.forja_events.length === 0}
          <EmptyState inline title="Nenhum evento da Forja em aberto" text="Enquanto nenhuma regra for atendida, esta lista fica vazia. Isso é bom." />
        {:else}
          <div class="list">
            {#each data.forja_events as e, i (e.id)}
              <article class="item" data-testid="alert-event-{e.id}" data-status={e.status} style:--i={i}>
                <div class="badges">
                  <Badge tone={severityTone(e.severity)}>{e.severity_pt}</Badge>
                  <Badge tone={e.status === 'OPEN' ? 'warn' : 'info'}>{e.status_pt}</Badge>
                  {#if e.quality === 'SIMULATED'}<Badge tone="sim" hatch>Simulado</Badge>{/if}
                </div>
                <h3 class="item-title">{e.title_pt}</h3>
                <p class="item-summary">{e.summary_pt}</p>
                {#if e.pre_event?.changes?.length}
                  <p class="before"><span class="before-tag">Antes</span> {e.pre_event.narrative_pt[0]}</p>
                {/if}
                <p class="meta">
                  Aberto <time datetime={e.start_utc} class="num">{fmtWhen(e.start_utc, app.now)}</time>
                </p>
                <div class="actions">
                  <a class="link" href={href.event(equipmentId, e.id)}>Ver detalhes</a>
                  <AckForm event={e} ondone={replaced} />
                </div>
              </article>
            {/each}
          </div>
        {/if}
      </Card>
    </div>

    <div id="alerts-ew" class="anchor">
      <Card title="Avisos antecipados" kicker="tendência e desvio do padrão" testid="alerts-ew">
        <p class="note top">{data.notes_pt.early_warning}</p>
        {#if data.early_warnings.length === 0}
          <EmptyState inline title="Nenhum aviso antecipado em aberto" text="Os sinais configurados estão dentro do padrão ou ainda não se confirmaram." />
        {:else}
          <div class="list">
            {#each data.early_warnings as e, i (e.id)}
              <article class="item ew" data-testid="alert-warning-{e.id}" data-status={e.status} style:--i={i}>
                <div class="badges">
                  <Badge tone={severityTone(e.severity)}>{e.severity_pt}</Badge>
                  <Badge tone="ghost">{e.origin_pt}</Badge>
                  {#if e.quality === 'SIMULATED'}<Badge tone="sim" hatch>Simulado</Badge>{/if}
                </div>
                <h3 class="item-title">{e.title_pt}</h3>
                <p class="item-summary">{e.summary_pt}</p>
                <p class="meta">
                  Desde <time datetime={e.start_utc} class="num">{fmtWhen(e.start_utc, app.now)}</time>
                </p>
                <div class="actions">
                  <a class="link" href={href.eq(equipmentId, 'early-warning')}>Ver sinais</a>
                  <AckForm event={e} ondone={replaced} />
                </div>
              </article>
            {/each}
          </div>
        {/if}
      </Card>
    </div>
  {/if}
</section>

<style>
  .alerts { display: flex; flex-direction: column; gap: var(--sp-5); }
  .head .label { margin: 0 0 var(--sp-1); }
  .title { margin: 0; color: var(--text-1); font: 600 var(--fs-h1) / var(--lh-h1) var(--font-ui); }
  @media (min-width: 1024px) {
    .title { font-size: var(--fs-display); line-height: var(--lh-display); }
  }
  .sub { margin: var(--sp-1) 0 0; max-width: 72ch; color: var(--text-2); font: var(--fs-body) / var(--lh-body) var(--font-ui); }

  .tiles { display: grid; gap: var(--sp-3); grid-template-columns: 1fr; }
  @media (min-width: 768px) { .tiles { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
  .tile {
    --tone: var(--text-2);
    display: grid;
    grid-template-columns: auto 1fr;
    grid-template-areas: 'icon label' 'icon value' 'icon meta';
    column-gap: var(--sp-3);
    align-items: center;
    min-height: 72px;
    padding: var(--sp-3) var(--sp-4);
    border: 1px solid var(--border-1);
    border-left: 3px solid var(--tone);
    border-radius: var(--r-4);
    background: var(--surf-1);
    color: var(--text-1);
    text-align: left;
    cursor: pointer;
    animation: rise var(--dur-screen) var(--ease-out) backwards;
    transition: background-color var(--dur-base) var(--ease-std), transform var(--dur-micro) var(--ease-std);
  }
  .tile:nth-child(2) { animation-delay: var(--stagger); }
  .tile:nth-child(3) { animation-delay: calc(var(--stagger) * 2); }
  .tile:hover { background: var(--surf-2); }
  .tile:active { transform: scale(0.99); }
  .tile:focus-visible { outline: none; box-shadow: var(--focus); }
  .tile[data-tone='ok'] { --tone: var(--st-ok); }
  .tile[data-tone='warn'] { --tone: var(--st-warn); }
  .tile[data-tone='crit'] { --tone: var(--st-crit); }
  .tile[data-tone='info'] { --tone: var(--st-info); }
  .tile[data-tone='unknown'] { --tone: var(--text-3); }
  .tile-icon { grid-area: icon; color: var(--tone); }
  .tile-label { grid-area: label; color: var(--text-2); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .tile-value { grid-area: value; color: var(--text-1); font: 600 var(--fs-h2) / var(--lh-h2) var(--font-ui); }
  .tile-value.num { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
  .tile-meta { grid-area: meta; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  @keyframes rise {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: none; }
  }

  .anchor { scroll-margin-top: calc(var(--header-h) + var(--sp-4)); }
  .kcm { display: flex; gap: var(--sp-3); align-items: flex-start; }
  .kcm-dot { display: grid; place-items: center; height: var(--lh-h2); }
  .kcm-body { display: flex; flex-direction: column; align-items: flex-start; gap: var(--sp-2); min-width: 0; }
  .kcm-state { margin: 0; color: var(--text-1); font: 600 var(--fs-h2) / var(--lh-h2) var(--font-ui); overflow-wrap: anywhere; }
  .kcm-line { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-2); margin: 0; }
  .code { color: var(--text-1); font: 500 var(--fs-mono) / var(--lh-mono) var(--font-mono); }
  .muted { margin: 0; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .note { margin: var(--sp-3) 0 0; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); max-width: 80ch; }
  .note.top { margin: 0 0 var(--sp-3); }

  .list { display: flex; flex-direction: column; gap: var(--sp-3); }
  .item {
    display: flex;
    flex-direction: column;
    gap: var(--sp-2);
    padding: var(--sp-3) var(--sp-4);
    border: 1px solid var(--border-1);
    border-left: 3px solid var(--st-warn);
    border-radius: var(--r-3);
    background: var(--surf-2);
    min-width: 0;
    animation: rise var(--dur-screen) var(--ease-out) backwards;
    animation-delay: calc(var(--i, 0) * var(--stagger));
  }
  .item[data-status='ACKNOWLEDGED'] { border-left-color: var(--st-info); }
  .item.ew { border-left-style: dashed; }
  .badges { display: flex; flex-wrap: wrap; gap: var(--sp-2); }
  .item-title { margin: 0; color: var(--text-1); font: 600 var(--fs-body) / var(--lh-body) var(--font-ui); }
  .item-summary { margin: 0; color: var(--text-2); font: var(--fs-body) / var(--lh-body) var(--font-ui); overflow-wrap: anywhere; }
  .before { margin: 0; color: var(--text-1); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .before-tag {
    display: inline-block;
    margin-right: var(--sp-1);
    padding: 0 6px;
    border-radius: var(--r-pill);
    background: var(--st-info-bg);
    color: var(--st-info);
    font-weight: 600;
  }
  .meta { margin: 0; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .actions { display: flex; flex-wrap: wrap; align-items: flex-start; gap: var(--sp-2) var(--sp-4); }
  .actions :global(form) { flex: 1 1 280px; }
  .link {
    display: inline-flex;
    align-items: center;
    min-height: var(--touch);
    color: var(--accent-text);
    font: 600 var(--fs-body) / 1.2 var(--font-ui);
    text-decoration: underline;
    text-underline-offset: 3px;
  }
  .link:focus-visible { outline: none; box-shadow: var(--focus); border-radius: var(--r-1); }

  .skeleton .sk { height: 72px; border-radius: var(--r-4); background: var(--surf-2); opacity: 0.6; }
</style>
