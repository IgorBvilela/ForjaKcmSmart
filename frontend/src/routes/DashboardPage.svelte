<script lang="ts">
  /** Dashboard do equipamento: condição, dosador animado, 6 indicadores, eventos e diagnóstico aberto. */
  import { untrack } from 'svelte'
  import ArrowRight from '@lucide/svelte/icons/arrow-right'
  import Eye from '@lucide/svelte/icons/eye'
  import {
    api,
    connectionTone,
    errorMessage,
    isUsable,
    severityTone,
    stateTone,
    worstQuality,
    type Diagnosis,
    type EquipmentDetail,
    type EventView,
    type Quality,
    type StateTone,
  } from '../lib/api'
  import { ageSince, fmtAge, fmtNumber, fmtTime, fmtWhen } from '../lib/format'
  import { live } from '../lib/live.svelte'
  import { href } from '../lib/router'
  import { app } from '../lib/state.svelte'
  import { TID } from '../lib/testids'
  import type { TimelineItem } from '../lib/timeline'
  import KpiTile from '../components/data/KpiTile.svelte'
  import Timeline from '../components/data/Timeline.svelte'
  import WhatChanged from '../components/data/WhatChanged.svelte'
  import Badge from '../components/ui/Badge.svelte'
  import Button from '../components/ui/Button.svelte'
  import Card from '../components/ui/Card.svelte'
  import EmptyState from '../components/ui/EmptyState.svelte'
  import StatusDot from '../components/ui/StatusDot.svelte'
  import WbfMachine from '../components/wbf/WbfMachine.svelte'

  let { equipmentId }: { equipmentId: string } = $props()

  /** Os 6 indicadores do contrato, na ordem da tela. Cor = série de gráfico (tokens --s*). */
  const TILES = [
    { tag: 'mass_flow', fallback: 'Vazão', color: 'var(--s1)' },
    { tag: 'setpoint', fallback: 'Setpoint', color: 'var(--s-ref)' },
    { tag: 'drive_command', fallback: 'Esforço do acionamento', color: 'var(--s2)' },
    { tag: 'rpm', fallback: 'Velocidade indicada', color: 'var(--s3)' },
    { tag: 'belt_load', fallback: 'Material na correia', color: 'var(--s4)' },
    { tag: 'int_channel_pct', fallback: 'Canal de integração', color: 'var(--s3)' },
  ] as const
  const TILE_TAGS = TILES.map((t) => t.tag)
  const HISTORY_WINDOW_S = 90

  let detail = $state<EquipmentDetail | null>(null)
  let detailError = $state<string | null>(null)
  let events = $state<EventView[]>([])
  let eventsError = $state<string | null>(null)
  let diagnosis = $state<Diagnosis | null>(null)
  let diagnosisFor = $state<string | null>(null)

  const eq = $derived(live.live[equipmentId])
  const card = $derived(live.cardOf(equipmentId))
  const profile = $derived(detail?.profile ?? null)
  const refs = $derived(profile?.reference_values ?? {})
  const isExample = $derived(card?.is_example ?? profile?.is_example ?? false)
  const simulated = $derived((card?.data_source ?? eq?.data_source) === 'SIMULATED')
  const name = $derived(card?.name ?? eq?.name ?? profile?.name ?? equipmentId)
  const connection = $derived(eq?.connection ?? card?.connection ?? null)
  const connectionPt = $derived(eq?.connection_pt ?? card?.connection_pt ?? 'Sem informação')
  const statePt = $derived(card?.state_pt ?? null)
  const stateT: StateTone = $derived(stateTone(statePt))

  function tagOf(tag: string) {
    return eq?.tags[tag]
  }
  function numOf(tag: string): number | null {
    const t = tagOf(tag)
    if (!t) return null
    return isUsable(t.quality) || t.quality === 'STALE' ? t.value : null
  }

  const machineQuality: Quality = $derived(worstQuality(TILE_TAGS.map((t) => tagOf(t)?.quality)))
  const machineState = $derived.by(() => {
    const v = tagOf('machine_state')?.value
    return v === 0 || v === 1 || v === 2 ? v : null
  })
  const scenario = $derived.by(() => {
    const opt = profile?.communication.options?.scenario
    return typeof opt === 'string' ? opt : undefined
  })

  const applicationText = $derived.by(() => {
    const a = card?.application ?? profile?.application
    if (a === 'WBF') return 'WBF · dosador de correia'
    if (a === 'LWF') return 'LWF · dosador de perda de peso'
    return 'Aplicação não confirmada'
  })
  const controllerText = $derived.by(() => {
    const c = profile?.controller
    if (!c) return 'KCM'
    const parts = [c.manufacturer, c.model].filter((p) => p && p !== 'UNKNOWN')
    return parts.length ? parts.join(' ') : 'Controlador não identificado'
  })

  const openAnomaly = $derived.by(() => {
    const order = { CRITICAL: 0, ATTENTION: 1, INFO: 2 } as const
    return (
      [...events]
        .filter((e) => e.is_open && e.severity !== 'INFO')
        .sort((a, b) => order[a.severity] - order[b.severity] || b.start_utc.localeCompare(a.start_utc))[0] ??
      null
    )
  })
  const openDiagnosis = $derived(openAnomaly && diagnosisFor === openAnomaly.id ? diagnosis : null)

  const condition = $derived.by(() => {
    const mf = tagOf('mass_flow')
    const sp = tagOf('setpoint')
    const anyReason = Object.values(eq?.tags ?? {}).find((t) => t.reason_pt)?.reason_pt ?? null
    if (!card && !eq) {
      return { chip: 'CARREGANDO', tone: 'unknown' as StateTone, text: 'Consultando o Edge local.' }
    }
    switch (statePt) {
      case 'Sem comunicação': {
        const since = eq?.last_ok_utc ? ` Última leitura válida às ${fmtTime(eq.last_ok_utc)}.` : ''
        return {
          chip: 'SEM COMUNICAÇÃO',
          tone: 'info' as StateTone,
          text: `Sem leitura do KCM${anyReason ? `: ${anyReason.toLowerCase()}` : ''}.${since} Estado da máquina: desconhecido.`,
        }
      }
      case 'Crítico':
      case 'Atenção': {
        const ev = openAnomaly
        const text = ev
          ? `${ev.title_pt}. ${ev.summary_pt}`
          : `${card?.active_anomaly_pt ?? 'Condição fora do padrão'}. Detalhes na lista de eventos.`
        return {
          chip: openDiagnosis ? 'DIAGNÓSTICO DISPONÍVEL' : statePt.toUpperCase(),
          tone: stateT,
          text,
        }
      }
      case 'Parado':
        return {
          chip: 'PARADO',
          tone: 'neutral' as StateTone,
          text: 'Máquina parada segundo o KCM. Parada não é falha. O material permanece na correia.',
        }
      case 'Normal': {
        const q = mf?.quality_pt ?? 'sem qualidade informada'
        let flow = ''
        if (mf && sp && isUsable(mf.quality) && isUsable(sp.quality) && mf.value != null && sp.value != null) {
          flow = ` Vazão em ${fmtNumber(mf.value, mf.decimals)} ${mf.unit} para setpoint de ${fmtNumber(sp.value, sp.decimals)} ${sp.unit}.`
        }
        return {
          chip: 'NORMAL',
          tone: 'ok' as StateTone,
          text: `Nenhum evento aberto. Leituras chegando com qualidade "${q}".${flow}`,
        }
      }
      default:
        return {
          chip: 'DESCONHECIDO',
          tone: 'unknown' as StateTone,
          text: 'Sem dados utilizáveis para classificar o estado deste equipamento.',
        }
    }
  })

  const flowCaption = $derived.by(() => {
    const mf = tagOf('mass_flow')
    const sp = tagOf('setpoint')
    if (!mf || !sp || !isUsable(mf.quality) || !isUsable(sp.quality)) return null
    if (mf.value == null || sp.value == null || sp.value === 0) return null
    const pct = ((mf.value - sp.value) / sp.value) * 100
    if (Math.abs(pct) < 0.05) return 'no setpoint'
    return `${fmtNumber(Math.abs(pct), 1)} % ${pct < 0 ? 'abaixo' : 'acima'} do setpoint`
  })

  const setpointRef = $derived.by(() => {
    const sp = tagOf('setpoint')
    return sp && isUsable(sp.quality) ? sp.value : null
  })

  const timelineItems: TimelineItem[] = $derived(
    events.slice(0, 8).map((e) => ({
      id: e.id,
      ts_utc: e.start_utc,
      title: e.title_pt,
      text: e.summary_pt,
      tone: severityTone(e.severity),
      href: href.event(equipmentId, e.id),
      muted: !e.is_open,
      meta: e.end_utc ? `Encerrado às ${fmtTime(e.end_utc)}` : null,
    })),
  )

  async function loadEvents(id: string): Promise<void> {
    try {
      const r = await api.events(id, { limit: 20 })
      if (id === equipmentId) {
        events = r.events
        eventsError = null
      }
    } catch (err) {
      if (id === equipmentId) eventsError = errorMessage(err)
    }
  }

  async function seedHistory(id: string): Promise<void> {
    try {
      const from = new Date(Date.now() - HISTORY_WINDOW_S * 1000).toISOString()
      const r = await api.history(id, [...TILE_TAGS], { from, maxPoints: HISTORY_WINDOW_S })
      for (const s of r.series) {
        live.seedSeries(
          id,
          s.tag,
          s.points.map((p) => ({ t: Date.parse(p.ts_utc), v: p.value, q: p.quality })),
        )
      }
    } catch {
      // sem histórico ainda: a mini-tendência enche com o tempo real
    }
  }

  // Perfil + histórico + reconciliação periódica do live (STALE é decidido pelo servidor).
  $effect(() => {
    const id = equipmentId
    let cancelled = false
    untrack(() => {
      detail = null
      detailError = null
      events = []
      eventsError = null
      diagnosis = null
      diagnosisFor = null
    })
    void (async () => {
      try {
        const d = await api.equipment(id)
        if (!cancelled) detail = d
      } catch (err) {
        if (!cancelled) detailError = errorMessage(err)
      }
    })()
    void seedHistory(id)
    void live.reconcileLive(id)
    const timer = window.setInterval(() => void live.reconcileLive(id), 10_000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  })

  // Eventos: ao trocar de equipamento e a cada transição recebida pelo SSE.
  $effect(() => {
    const id = equipmentId
    void live.eventsVersion
    void live.diagnosisVersion
    untrack(() => void loadEvents(id))
  })

  // Diagnóstico do evento aberto mais grave.
  $effect(() => {
    const ev = openAnomaly
    void live.diagnosisVersion
    if (!ev) return
    let cancelled = false
    api
      .diagnosis(ev.id)
      .then((d) => {
        if (cancelled) return
        diagnosis = d
        diagnosisFor = ev.id
      })
      .catch(() => {
        if (!cancelled) {
          diagnosis = null
          diagnosisFor = ev.id
        }
      })
    return () => {
      cancelled = true
    }
  })
</script>

<section class="dash" data-equipment={equipmentId} data-state={statePt ?? ''}>
  <header class="dash-head">
    <div class="dash-title">
      <h1>{name}</h1>
      <div class="dash-meta">
        <span>{applicationText}</span>
        <span class="sep" aria-hidden="true">|</span>
        <span>{controllerText}</span>
        <span class="sep" aria-hidden="true">|</span>
        <span class="conn" data-conn={connection ?? ''}>
          <StatusDot state={connectionTone(connection)} hollow={connection !== 'CONNECTED'} size={8} />
          {connectionPt}
        </span>
        {#if isExample}
          <Badge tone="ghost" title="Perfil de exemplo: existência real não confirmada">exemplo</Badge>
        {/if}
        {#if simulated}<Badge tone="sim" hatch>Simulado</Badge>{/if}
      </div>
      {#if card?.display_path}<p class="dash-path">{card.display_path}</p>{/if}
    </div>
    <div class="dash-actions">
      <Button href={href.eq(equipmentId, 'events')} variant="ghost" size="sm">Eventos</Button>
      {#if simulated}
        <Button href={href.eq(equipmentId, 'simulator')} variant="ghost" size="sm">Simulador</Button>
      {/if}
    </div>
  </header>

  {#if detailError && !card && !eq}
    <EmptyState title="Equipamento indisponível" text={detailError} />
  {:else}
    <div class="dash-grid">
      <!-- Dosador animado -->
      <Card class="area-machine machine-card" padded={false} testid="dashboard-machine">
        <div class="machine-head">
          <span class="label">Dosador de correia · corte lateral</span>
          <span class="machine-note">Desenho reage a velocidade e material na correia</span>
        </div>
        <div class="machine-body">
          <WbfMachine
            rpm={numOf('rpm')}
            beltLoad={numOf('belt_load')}
            driveCommand={numOf('drive_command')}
            massFlow={numOf('mass_flow')}
            {machineState}
            quality={machineQuality}
            connection={connection ?? 'DISCONNECTED'}
            rpmRef={refs.rpm_ref ?? null}
            beltLoadRef={refs.belt_load_ref ?? null}
            {scenario}
            reducedMotion={app.reducedMotion}
          />
        </div>
      </Card>

      <!-- O que o sistema está vendo -->
      <Card class="area-system system-card" testid={TID.systemView.root}>
        <header class="sys-head">
          <span class="sys-icon" aria-hidden="true"><Eye size={18} strokeWidth={1.75} /></span>
          <h2 class="sys-title">O que o sistema está vendo</h2>
          <Badge tone={condition.tone === 'unknown' ? 'ghost' : condition.tone === 'neutral' ? 'neutral' : condition.tone} size="md" testid={TID.systemView.chip} data-state={condition.chip}>
            <StatusDot state={condition.tone} size={7} hollow={condition.tone === 'info'} />
            {condition.chip}
          </Badge>
        </header>
        <p class="sys-text" data-testid={TID.systemView.text}>{condition.text}</p>
        {#if openAnomaly && openDiagnosis}
          <a class="sys-link" href={href.event(equipmentId, openAnomaly.id)}>
            Abrir diagnóstico <ArrowRight size={16} aria-hidden="true" />
          </a>
        {/if}
      </Card>

      <!-- 6 indicadores -->
      <div class="area-tiles tiles" data-testid={TID.kpi.grid}>
        {#each TILES as spec, i (spec.tag)}
          {@const t = tagOf(spec.tag)}
          <KpiTile
            tag={spec.tag}
            label={t?.label_pt ?? spec.fallback}
            unit={t?.unit ?? ''}
            decimals={t?.decimals ?? 1}
            value={t?.value ?? null}
            quality={t?.quality ?? 'COMM_ERROR'}
            qualityPt={t?.quality_pt ?? null}
            ageS={t ? live.ageOf(t, app.now) : null}
            reasonPt={t?.reason_pt ?? (t ? null : 'Variável não mapeada neste equipamento')}
            explanation={t?.explanation_pt ?? ''}
            points={live.seriesFor(equipmentId, spec.tag)}
            refValue={spec.tag === 'mass_flow' ? setpointRef : null}
            caption={spec.tag === 'mass_flow' ? flowCaption : null}
            color={spec.color}
            index={i}
            animate={!app.reducedMotion}
          />
        {/each}
      </div>

      <!-- Linha do tempo -->
      <Card class="area-timeline" title="Sequência de eventos" kicker="Linha do tempo">
        {#snippet actions()}
          <Button href={href.eq(equipmentId, 'events')} variant="link" size="sm">
            Ver todos <ArrowRight size={14} aria-hidden="true" />
          </Button>
        {/snippet}
        {#if eventsError}
          <p class="err">{eventsError}</p>
        {:else}
          <Timeline items={timelineItems} emptyText="Nenhum evento registrado para este equipamento." />
        {/if}
      </Card>

      <!-- Diagnóstico aberto -->
      <Card class="area-diagnosis" title="Diagnóstico" kicker="Condição aberta" testid={TID.diagnosisSummary}>
        {#if openAnomaly && openDiagnosis}
          <div class="diag">
            <div class="diag-head">
              <Badge tone={severityTone(openAnomaly.severity)}>{openAnomaly.severity_pt}</Badge>
              <span class="diag-since">desde {fmtWhen(openAnomaly.start_utc, app.now)} · {fmtAge(ageSince(openAnomaly.start_utc, app.now)).replace('há ', '')} em aberto</span>
            </div>
            <h3 class="diag-title">{openDiagnosis.summary.title_pt}</h3>
            <p class="diag-text">{openDiagnosis.summary.text_pt}</p>
            <p class="label">O que mudou</p>
            <WhatChanged items={openDiagnosis.what_changed} limit={3} compact />
            <div class="diag-actions">
              <Button href={href.event(equipmentId, openAnomaly.id)} variant="primary">
                Abrir diagnóstico <ArrowRight size={16} aria-hidden="true" />
              </Button>
              <span class="diag-note">{openDiagnosis.hypotheses.length} hipóteses · {openDiagnosis.next_checks.length} verificações</span>
            </div>
          </div>
        {:else if openAnomaly}
          <div class="diag">
            <div class="diag-head">
              <Badge tone={severityTone(openAnomaly.severity)}>{openAnomaly.severity_pt}</Badge>
              <span class="diag-since">desde {fmtWhen(openAnomaly.start_utc, app.now)}</span>
            </div>
            <h3 class="diag-title">{openAnomaly.title_pt}</h3>
            <p class="diag-text">{openAnomaly.summary_pt}</p>
            <p class="diag-pending">Ainda não há diagnóstico para este evento. O motor publica o JSON v1.0 logo após a detecção.</p>
            <div class="diag-actions">
              <Button href={href.event(equipmentId, openAnomaly.id)} variant="ghost">Ver evento</Button>
            </div>
          </div>
        {:else}
          <EmptyState
            compact
            title="Nenhum diagnóstico aberto"
            text="Quando uma condição sair do padrão, aparece aqui o que mudou, as hipóteses e o que verificar primeiro."
            testid="dashboard-diagnosis-empty"
          />
        {/if}
      </Card>
    </div>
  {/if}
</section>

<style>
  .dash { display: flex; flex-direction: column; gap: var(--sp-5); }

  .dash-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--sp-4);
    flex-wrap: wrap;
  }
  .dash-title { display: flex; flex-direction: column; gap: var(--sp-1); min-width: 0; }
  .dash-title h1 {
    margin: 0;
    font: 600 var(--fs-h1) / var(--lh-h1) var(--font-ui);
    color: var(--text-1);
  }
  .dash-meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--sp-2);
    color: var(--text-2);
    font: var(--fs-body) / var(--lh-body) var(--font-ui);
  }
  .sep { color: var(--border-2); }
  .conn { display: inline-flex; align-items: center; gap: var(--sp-2); }
  .dash-path {
    margin: 0;
    color: var(--text-3);
    font: var(--fs-caption) / var(--lh-caption) var(--font-ui);
  }
  .dash-actions { display: flex; gap: var(--sp-2); flex: none; }

  .dash-grid {
    display: grid;
    gap: var(--sp-5);
    grid-template-columns: minmax(0, 5fr) minmax(0, 7fr);
    grid-template-areas:
      'machine system'
      'machine tiles'
      'timeline diagnosis';
    align-items: start;
  }
  .dash-grid :global(.area-machine) { grid-area: machine; align-self: stretch; }
  .dash-grid :global(.area-system) { grid-area: system; }
  .area-tiles { grid-area: tiles; }
  .dash-grid :global(.area-timeline) { grid-area: timeline; }
  .dash-grid :global(.area-diagnosis) { grid-area: diagnosis; }

  .tiles {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--sp-4);
  }

  @media (max-width: 1279px) {
    .dash-grid {
      grid-template-columns: minmax(0, 1fr);
      grid-template-areas:
        'system'
        'tiles'
        'machine'
        'timeline'
        'diagnosis';
    }
    .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }
  @media (max-width: 767px) {
    .dash { gap: var(--sp-4); }
    .dash-grid { gap: var(--sp-4); }
    .tiles { grid-template-columns: minmax(0, 1fr); gap: var(--sp-3); }
    .dash-actions { width: 100%; }
  }

  /* dosador */
  .dash-grid :global(.machine-card) {
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .machine-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--sp-3);
    padding: var(--sp-4) var(--sp-5) 0;
  }
  .machine-note {
    color: var(--text-3);
    font: var(--fs-caption) / var(--lh-caption) var(--font-ui);
    text-align: right;
  }
  .machine-body {
    flex: 1 1 auto;
    min-height: 280px;
    padding: var(--sp-3) var(--sp-4) var(--sp-4);
    display: flex;
    flex-direction: column;
    justify-content: center;
  }
  .machine-body > :global(*) { flex: 0 1 auto; width: 100%; }

  /* o que o sistema está vendo */
  .sys-head {
    display: flex;
    align-items: center;
    gap: var(--sp-3);
    flex-wrap: wrap;
    margin-bottom: var(--sp-3);
  }
  .sys-icon {
    display: grid;
    place-items: center;
    width: 32px;
    height: 32px;
    border-radius: var(--r-3);
    background: var(--accent-soft);
    color: var(--accent-text);
  }
  .sys-title {
    margin: 0;
    flex: 1 1 auto;
    font: 600 var(--fs-h2) / var(--lh-h2) var(--font-ui);
    color: var(--text-1);
  }
  .sys-text {
    margin: 0;
    font: var(--fs-body-lg) / var(--lh-body-lg) var(--font-ui);
    color: var(--text-1);
    max-width: 80ch;
  }
  .sys-link {
    display: inline-flex;
    align-items: center;
    gap: var(--sp-1);
    margin-top: var(--sp-3);
    color: var(--accent-text);
    font: 500 var(--fs-body) / var(--lh-body) var(--font-ui);
    text-decoration: none;
    border-radius: var(--r-1);
  }
  .sys-link:hover { text-decoration: underline; }

  .err { margin: 0; color: var(--st-crit); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }

  /* diagnóstico */
  .diag { display: flex; flex-direction: column; gap: var(--sp-3); }
  .diag-head { display: flex; align-items: center; gap: var(--sp-3); flex-wrap: wrap; }
  .diag-since { color: var(--text-3); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .diag-title {
    margin: 0;
    font: 600 var(--fs-h2) / var(--lh-h2) var(--font-ui);
    color: var(--text-1);
  }
  .diag-text {
    margin: 0;
    color: var(--text-2);
    font: var(--fs-body) / var(--lh-body) var(--font-ui);
    display: -webkit-box;
    -webkit-line-clamp: 3;
    line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .diag-pending { margin: 0; color: var(--text-3); font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  .diag-actions { display: flex; align-items: center; gap: var(--sp-3); flex-wrap: wrap; margin-top: var(--sp-1); }
  .diag-note { color: var(--text-3); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
</style>
