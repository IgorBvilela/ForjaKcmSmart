<script lang="ts">
  /** Visão da planta: um card por equipamento, com estado, vazão e qualidade. Clique abre o dashboard. */
  import { isUsable, stateTone, type PlantCard } from '../lib/api'
  import { ageSince, fmtAge, fmtNumber, fmtWhen, plural } from '../lib/format'
  import { live } from '../lib/live.svelte'
  import { href } from '../lib/router'
  import { app } from '../lib/state.svelte'
  import { TID } from '../lib/testids'
  import Sparkline from '../components/data/Sparkline.svelte'
  import Badge from '../components/ui/Badge.svelte'
  import EmptyState from '../components/ui/EmptyState.svelte'
  import QualityBadge from '../components/ui/QualityBadge.svelte'
  import StatusDot from '../components/ui/StatusDot.svelte'

  const cards = $derived(live.plant)

  const title = $derived.by(() => {
    const prefixes = new Set<string>()
    for (const c of cards) {
      const suffix = ` — ${c.name}`
      if (c.display_path.endsWith(suffix)) {
        const p = c.display_path.slice(0, -suffix.length)
        if (p) prefixes.add(p)
      }
    }
    return prefixes.size ? [...prefixes].join(' · ') : 'Planta'
  })

  const summary = $derived.by(() => {
    if (cards.length === 0) return ''
    const counts = new Map<string, number>()
    for (const c of cards) counts.set(c.state_pt, (counts.get(c.state_pt) ?? 0) + 1)
    const parts = [plural(cards.length, 'equipamento', 'equipamentos')]
    for (const k of ['Crítico', 'Atenção', 'Sem comunicação', 'Parado', 'Desconhecido']) {
      const n = counts.get(k)
      if (n) parts.push(`${fmtNumber(n, 0)} ${k.toLowerCase()}`)
    }
    if (parts.length === 1) parts.push('todos em condição normal')
    return parts.join(' · ')
  })

  function applicationText(c: PlantCard): string {
    if (c.application === 'WBF') return 'WBF · dosador de correia'
    if (c.application === 'LWF') return 'LWF · dosador de perda de peso'
    return 'Aplicação não confirmada'
  }

  function anomalyText(c: PlantCard): string | null {
    if (c.active_anomaly_pt) return c.active_anomaly_pt
    if (c.state_pt === 'Sem comunicação') {
      const reason = c.mass_flow?.reason_pt
      return `Sem leitura do KCM${reason ? `: ${reason.toLowerCase()}` : ''}. Estado da máquina: desconhecido.`
    }
    if (c.state_pt === 'Parado') return 'Máquina parada segundo o KCM. Parada não é falha.'
    return null
  }
</script>

<section class="plant">
  <header class="plant-head">
    <div>
      <p class="label">Visão da planta</p>
      <h1 class="plant-title" data-testid={TID.plant.title}>{title}</h1>
    </div>
    {#if summary}
      <p class="plant-summary" data-testid={TID.plant.summary}>{summary}</p>
    {/if}
  </header>

  {#if cards.length === 0}
    {#if live.plantError}
      <EmptyState
        title="Sem resposta do Edge"
        text={`${live.plantError} A interface volta a tentar sozinha a cada 15 s.`}
      />
    {:else if live.edge === 'connecting'}
      <EmptyState title="Conectando ao serviço local" text="Aguardando o primeiro snapshot do Edge." />
    {:else}
      <EmptyState
        title="Nenhum equipamento configurado"
        text="Os perfis ficam em config/equipment. Sem perfil, não há o que observar."
      />
    {/if}
  {:else}
    <div class="grid" data-testid={TID.plant.grid}>
      {#each cards as c, i (c.id)}
        {@const tone = stateTone(c.state_pt)}
        {@const mf = c.mass_flow}
        {@const usable = mf ? isUsable(mf.quality) : false}
        {@const anomaly = anomalyText(c)}
        <a
          class="pcard"
          href={href.eq(c.id)}
          data-testid={TID.plant.card(c.id)}
          data-state={c.state_pt}
          data-conn={c.connection}
          data-quality={mf?.quality ?? ''}
          style:--i={i}
          aria-label={`${c.name}: ${c.state_pt}. Abrir dashboard`}
        >
          <header class="pcard-head">
            <span class="pcard-state" data-tone={tone}>
              <StatusDot state={tone} hollow={tone === 'info'} size={9} />
              <span>{c.state_pt}</span>
            </span>
            <span class="pcard-badges">
              {#if c.data_source === 'SIMULATED'}
                <Badge tone="sim" hatch>Simulado</Badge>
              {/if}
            </span>
          </header>

          <h2 class="pcard-name">{c.name}</h2>
          <p class="pcard-app">
            {applicationText(c)}{#if c.is_example}<span title="Perfil de exemplo: existência real não confirmada">{' · perfil de exemplo'}</span>{/if}
          </p>

          {#if anomaly}
            <p class="pcard-anomaly" data-tone={tone}>{anomaly}</p>
          {:else}
            <p class="pcard-anomaly quiet">Nenhum evento aberto.</p>
          {/if}

          <div class="pcard-flow">
            <div class="pcard-flow-head">
              <span class="label">{mf?.label_pt ?? 'Vazão'}</span>
              {#if mf}
                <QualityBadge
                  quality={mf.quality}
                  qualityPt={mf.quality_pt}
                  ageS={mf.quality === 'STALE' ? ageSince(mf.ts_utc, app.now) : null}
                  reasonPt={mf.reason_pt}
                />
              {/if}
            </div>
            <div class="pcard-value" class:faded={!usable}>
              <span class="num big">
                {mf && (usable || mf.quality === 'STALE') ? fmtNumber(mf.value, mf.decimals) : '—'}
              </span>
              {#if mf && (usable || mf.quality === 'STALE')}<span class="unit">{mf.unit}</span>{/if}
            </div>
            <Sparkline points={live.seriesFor(c.id, 'mass_flow')} faded={!usable} height={28} showWindow={false} />
          </div>

          <footer class="pcard-foot">
            <span>Última leitura {fmtAge(ageSince(c.last_read_utc, app.now))}</span>
            {#if c.last_event}
              <span class="pcard-last">
                Último evento: {c.last_event.title_pt} · {fmtWhen(c.last_event.start_utc, app.now)}
              </span>
            {:else}
              <span class="pcard-last">Nenhum evento registrado</span>
            {/if}
          </footer>
        </a>
      {/each}
    </div>
  {/if}
</section>

<style>
  .plant { display: flex; flex-direction: column; gap: var(--sp-6); }
  .plant-head {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: var(--sp-4);
    flex-wrap: wrap;
  }
  .plant-head .label { margin: 0 0 var(--sp-1); }
  .plant-title {
    margin: 0;
    font: 600 var(--fs-h1) / var(--lh-h1) var(--font-ui);
    color: var(--text-1);
  }
  @media (min-width: 1024px) {
    .plant-title { font-size: var(--fs-display); line-height: var(--lh-display); }
  }
  .plant-summary {
    margin: 0;
    color: var(--text-2);
    font: var(--fs-body) / var(--lh-body) var(--font-ui);
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(var(--card-min), 1fr));
    gap: var(--sp-5);
    /* em 1920 os cards não boiam: a grade tem teto e os cards crescem um pouco */
    max-width: 1280px;
  }
  @media (min-width: 1600px) {
    .grid { --card-min: 400px; }
  }
  @media (max-width: 767px) {
    .grid { grid-template-columns: 1fr; gap: var(--sp-4); }
  }

  .pcard {
    display: flex;
    flex-direction: column;
    gap: var(--sp-3);
    padding: var(--sp-5);
    background: var(--surf-1);
    border: 1px solid var(--border-1);
    border-radius: var(--r-4);
    color: inherit;
    text-decoration: none;
    min-width: 0;
    animation: rise var(--dur-screen) var(--ease-out) backwards;
    animation-delay: calc(var(--i, 0) * var(--stagger));
    transition:
      border-color var(--dur-base) var(--ease-std),
      background-color var(--dur-base) var(--ease-std),
      transform var(--dur-base) var(--ease-out);
  }
  @keyframes rise {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: none; }
  }
  .pcard:hover { border-color: var(--border-2); background: var(--surf-2); }
  .pcard:focus-visible { outline: none; box-shadow: var(--focus); }
  .pcard[data-state='Sem comunicação'] .pcard-value { color: var(--text-3); }

  .pcard-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--sp-2);
  }
  .pcard-state {
    display: inline-flex;
    align-items: center;
    gap: var(--sp-2);
    font: 600 var(--fs-label) / var(--lh-label) var(--font-ui);
    letter-spacing: var(--ls-label);
    text-transform: uppercase;
    color: var(--text-2);
    white-space: nowrap;
  }
  .pcard-state[data-tone='ok'] { color: var(--st-ok); }
  .pcard-state[data-tone='warn'] { color: var(--st-warn); }
  .pcard-state[data-tone='crit'] { color: var(--st-crit); }
  .pcard-state[data-tone='info'] { color: var(--st-info); }
  .pcard-badges { display: inline-flex; gap: var(--sp-2); flex-wrap: wrap; justify-content: flex-end; }

  .pcard-name {
    margin: 0;
    font: 600 var(--fs-h2) / var(--lh-h2) var(--font-ui);
    color: var(--text-1);
  }
  .pcard-app {
    margin: calc(-1 * var(--sp-2)) 0 0;
    color: var(--text-3);
    font: var(--fs-caption) / var(--lh-caption) var(--font-ui);
  }
  .pcard-anomaly {
    margin: 0;
    padding: var(--sp-2) var(--sp-3);
    border-radius: var(--r-2);
    background: var(--surf-2);
    color: var(--text-1);
    font: var(--fs-caption) / var(--lh-caption) var(--font-ui);
    border-left: 2px solid var(--border-2);
  }
  .pcard-anomaly[data-tone='warn'] { border-left-color: var(--st-warn); }
  .pcard-anomaly[data-tone='crit'] { border-left-color: var(--st-crit); }
  .pcard-anomaly[data-tone='info'] { border-left-color: var(--st-info); }
  .pcard-anomaly.quiet { color: var(--text-3); background: transparent; padding-left: 0; border-left: 0; }

  .pcard-flow { display: flex; flex-direction: column; gap: var(--sp-1); margin-top: var(--sp-1); }
  .pcard-flow-head { display: flex; align-items: center; justify-content: space-between; gap: var(--sp-2); }
  .pcard-value {
    display: flex;
    align-items: baseline;
    gap: var(--sp-2);
    color: var(--text-1);
    transition: opacity var(--dur-base) var(--ease-std);
  }
  .pcard-value.faded { opacity: 0.6; }
  .big {
    font-size: var(--fs-num-lg);
    line-height: var(--lh-num-lg);
    font-weight: 500;
  }
  .unit {
    color: var(--text-3);
    font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui);
  }

  .pcard-foot {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding-top: var(--sp-3);
    border-top: 1px solid var(--border-1);
    color: var(--text-3);
    font: var(--fs-caption) / var(--lh-caption) var(--font-ui);
  }
  .pcard-last { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
