<script lang="ts">
  /** Detalhe do evento + painel de diagnóstico (7 seções) + detalhes técnicos (JSON) colapsados. */
  import { untrack } from 'svelte'
  import ArrowLeft from '@lucide/svelte/icons/arrow-left'
  import { api, errorMessage, isNotFound, severityTone, type Diagnosis, type EventView } from '../lib/api'
  import { ageSince, fmtDateTime, fmtDuration } from '../lib/format'
  import { live } from '../lib/live.svelte'
  import { href } from '../lib/router'
  import { app } from '../lib/state.svelte'
  import { TID } from '../lib/testids'
  import type { TimelineItem } from '../lib/timeline'
  import DiagnosisPanel from '../components/data/DiagnosisPanel.svelte'
  import Timeline from '../components/data/Timeline.svelte'
  import Badge from '../components/ui/Badge.svelte'
  import Card from '../components/ui/Card.svelte'
  import Disclosure from '../components/ui/Disclosure.svelte'
  import EmptyState from '../components/ui/EmptyState.svelte'
  import QualityBadge from '../components/ui/QualityBadge.svelte'

  let { equipmentId, eventId }: { equipmentId: string; eventId: string } = $props()

  let event = $state<EventView | null>(null)
  let diagnosis = $state<Diagnosis | null>(null)
  let loading = $state(true)
  let error = $state<string | null>(null)
  let notFound = $state(false)

  const card = $derived(live.cardOf(equipmentId))
  const name = $derived(card?.name ?? equipmentId)

  const duration = $derived.by(() => {
    if (!event) return '—'
    if (event.end_utc) return fmtDuration(event.duration_s)
    return fmtDuration(ageSince(event.start_utc, app.now))
  })

  const contextTimeline: TimelineItem[] = $derived(
    (event?.context.timeline ?? []).map((p, i) => ({
      id: `${i}-${p.ts_utc}`,
      ts_utc: p.ts_utc,
      title: p.text_pt,
      tone: p.kind === 'kcm' ? 'info' : p.kind === 'human' ? 'neutral' : 'warn',
      meta: p.kind === 'kcm' ? 'informado pelo KCM' : p.kind === 'human' ? 'registro humano' : null,
    })),
  )

  const technical = $derived.by(() => {
    if (!event) return ''
    const { context, ...rest } = event
    const { pre_samples, during_samples, post_samples, ...ctx } = context
    void pre_samples
    void during_samples
    void post_samples
    return JSON.stringify({ event: { ...rest, context: ctx }, diagnosis }, null, 2)
  })

  async function load(id: string): Promise<void> {
    try {
      const ev = await api.event(id)
      if (id !== eventId) return
      event = ev
      notFound = false
      error = null
      diagnosis = await api.diagnosis(id)
    } catch (err) {
      if (id !== eventId) return
      if (isNotFound(err)) notFound = true
      else error = errorMessage(err)
    } finally {
      if (id === eventId) loading = false
    }
  }

  $effect(() => {
    const id = eventId
    void live.eventsVersion
    void live.diagnosisVersion
    untrack(() => {
      if (!event || event.id !== id) {
        loading = true
        event = null
        diagnosis = null
      }
      void load(id)
    })
  })
</script>

<section class="detail" data-testid={TID.events.detail} data-event={eventId}>
  <a class="back" href={href.eq(equipmentId, 'events')}>
    <ArrowLeft size={16} aria-hidden="true" /> Eventos de {name}
  </a>

  {#if error}
    <EmptyState title="Não foi possível carregar o evento" text={error} />
  {:else if notFound}
    <EmptyState title="Evento não encontrado" text="O identificador não corresponde a nenhum evento registrado neste Edge." />
  {:else if loading && !event}
    <Card><p class="muted">Carregando evento…</p></Card>
  {:else if event}
    <Card class="ev-card" testid="event-header">
      <div class="ev-head">
        <Badge tone={severityTone(event.severity)} size="md">{event.severity_pt}</Badge>
        <Badge tone={event.status === 'OPEN' ? 'warn' : event.status === 'ACKNOWLEDGED' ? 'info' : 'ghost'} size="md">{event.status_pt}</Badge>
        <QualityBadge quality={event.quality} qualityPt={event.quality_pt} />
      </div>
      <h1 class="ev-title">{event.title_pt}</h1>
      <p class="ev-summary">{event.summary_pt}</p>
      <dl class="facts">
        <div><dt class="label">Início</dt><dd class="num">{fmtDateTime(event.start_utc)}</dd></div>
        <div><dt class="label">Fim</dt>{#if event.end_utc}<dd class="num">{fmtDateTime(event.end_utc)}</dd>{:else}<dd class="plain">em aberto</dd>{/if}</div>
        <div><dt class="label">Duração</dt><dd class="num">{duration}{#if !event.end_utc}<span class="plain"> · em aberto</span>{/if}</dd></div>
        <div><dt class="label">Amostras guardadas</dt><dd class="num">{event.context.pre_sample_count} antes · {event.context.during_sample_count} durante · {event.context.post_sample_count} depois</dd></div>
        {#if event.context.gap_count || event.context.stale_count || event.context.comm_error_count}
          <div><dt class="label">Qualidade na janela</dt><dd class="num">{event.context.gap_count} buracos · {event.context.stale_count} antigos · {event.context.comm_error_count} sem comunicação</dd></div>
        {/if}
        {#if event.acked_by}
          <div><dt class="label">Reconhecido por</dt><dd>{event.acked_by} · {fmtDateTime(event.acked_at_utc)}</dd></div>
        {/if}
      </dl>
      {#if contextTimeline.length}
        <h2 class="label sub">Linha do tempo do evento</h2>
        <Timeline items={contextTimeline} testid="event-context-timeline" />
      {/if}
    </Card>

    <Card class="diag-card" title="Diagnóstico" kicker="Forja KCM Intelligence · contrato v1.0">
      {#if diagnosis}
        <DiagnosisPanel {diagnosis} />
      {:else}
        <EmptyState
          compact
          title="Ainda não há diagnóstico para este evento"
          text="O motor publica o JSON v1.0 logo após a detecção. Se o evento é recente, aguarde alguns segundos; esta página atualiza sozinha."
          testid="diagnosis-empty"
        />
      {/if}
    </Card>

    <Card padded={false} class="tech-card">
      <div class="tech">
        <Disclosure summary="Detalhes técnicos" testid="event-technical">
          <dl class="tech-facts">
            <div><dt>Tipo (código interno)</dt><dd class="num">{event.type}</dd></div>
            <div><dt>Regra</dt><dd class="num">{event.rule_id} v{event.rule_version}</dd></div>
            <div><dt>Id do evento</dt><dd class="num">{event.id}</dd></div>
            {#if diagnosis}
              <div><dt>Id do diagnóstico</dt><dd class="num">{diagnosis.diagnosis_id}</dd></div>
              <div><dt>Código interno</dt><dd class="num">{diagnosis.summary.internal_code}</dd></div>
              <div><dt>Motor</dt><dd class="num">{diagnosis.engine_version}</dd></div>
            {/if}
            {#if event.diagnosis_ref}
              <div><dt>Entrada da biblioteca</dt><dd class="num">{event.diagnosis_ref}</dd></div>
            {/if}
          </dl>
          <pre class="json num">{technical}</pre>
        </Disclosure>
      </div>
    </Card>
  {/if}
</section>

<style>
  .detail { display: flex; flex-direction: column; gap: var(--sp-5); }
  .back {
    display: inline-flex;
    align-items: center;
    gap: var(--sp-2);
    align-self: flex-start;
    min-height: 36px;
    color: var(--text-2);
    text-decoration: none;
    font: 500 var(--fs-body) / var(--lh-body) var(--font-ui);
    border-radius: var(--r-2);
  }
  .back:hover { color: var(--text-1); }
  @media (max-width: 767px), (pointer: coarse) {
    .back { min-height: var(--touch); }
  }
  .muted { margin: 0; color: var(--text-3); }

  .ev-head { display: flex; align-items: center; gap: var(--sp-2); flex-wrap: wrap; margin-bottom: var(--sp-3); }
  .ev-title {
    margin: 0;
    font: 600 var(--fs-h1) / var(--lh-h1) var(--font-ui);
    color: var(--text-1);
  }
  .ev-summary {
    margin: var(--sp-2) 0 0;
    max-width: 80ch;
    color: var(--text-1);
    font: var(--fs-body-lg) / var(--lh-body-lg) var(--font-ui);
  }
  .facts {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: var(--sp-3) var(--sp-5);
    margin: var(--sp-5) 0 0;
    padding-top: var(--sp-4);
    border-top: 1px solid var(--border-1);
  }
  .facts div { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .facts dt { margin: 0; }
  .facts dd {
    margin: 0;
    color: var(--text-1);
    font-size: var(--fs-mono);
    line-height: var(--lh-mono);
  }
  /* texto, não número: fonte da interface */
  .facts .plain { font-family: var(--font-ui); font-size: var(--fs-body); color: var(--text-2); }
  .sub { margin: var(--sp-5) 0 var(--sp-2); }

  .tech { padding: var(--sp-3) var(--sp-5); }
  .tech-facts {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: var(--sp-2) var(--sp-4);
    margin: 0 0 var(--sp-3);
  }
  .tech-facts div { display: flex; flex-direction: column; }
  .tech-facts dt { color: var(--text-3); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .tech-facts dd { margin: 0; color: var(--text-2); font-size: var(--fs-mono-sm); line-height: var(--lh-mono-sm); word-break: break-all; }
  .json {
    margin: 0;
    max-height: 480px;
    overflow: auto;
    padding: var(--sp-3) var(--sp-4);
    border: 1px solid var(--border-1);
    border-radius: var(--r-3);
    background: var(--bg-0);
    color: var(--text-2);
    font-size: var(--fs-mono-sm);
    line-height: var(--lh-mono-sm);
    white-space: pre;
  }
  @media (max-width: 767px) {
    .tech { padding: var(--sp-2) var(--sp-4); }
    .json { max-height: 320px; }
  }
</style>
