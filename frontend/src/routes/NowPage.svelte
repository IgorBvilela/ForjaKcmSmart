<script lang="ts">
  /** Agora: está tudo bem? O que a manutenção verifica primeiro? Gerente à esquerda, manutenção à direita. */
  import { onMount } from 'svelte'
  import Check from '@lucide/svelte/icons/check'
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert'
  import NowCard from '../components/now/NowCard.svelte'
  import Badge from '../components/ui/Badge.svelte'
  import EmptyState from '../components/ui/EmptyState.svelte'
  import StatusDot from '../components/ui/StatusDot.svelte'
  import { errorMessage, stateTone } from '../lib/api'
  import { ageSince, fmtAge, fmtNumber } from '../lib/format'
  import { live } from '../lib/live.svelte'
  import { href } from '../lib/router'
  import {
    sinceText,
    situationApi,
    type SituationEntry,
    type SituationResponse,
  } from '../lib/situation'
  import { app } from '../lib/state.svelte'

  const REFRESH_MS = 15_000

  let data = $state<SituationResponse | null>(null)
  let error = $state<string | null>(null)
  let timer: number | undefined

  async function load(): Promise<void> {
    try {
      data = await situationApi.get()
      error = null
    } catch (err) {
      error = errorMessage(err)
    }
  }

  function schedule(delayMs = 300): void {
    if (timer) clearTimeout(timer)
    timer = window.setTimeout(() => void load(), delayMs)
  }

  onMount(() => {
    void load()
    const id = window.setInterval(() => void load(), REFRESH_MS)
    return () => {
      clearInterval(id)
      if (timer) clearTimeout(timer)
    }
  })

  // Evento, diagnóstico ou estado novo no SSE: a situação é refeita logo em seguida.
  $effect(() => {
    void live.eventsVersion
    void live.diagnosisVersion
    void live.plant
    if (data) schedule()
  })

  const summary = $derived(data?.summary)
  const problems = $derived(data?.equipments.filter((e) => e.group === 'problem') ?? [])
  const noData = $derived(data?.equipments.filter((e) => e.group === 'no_data') ?? [])
  const calm = $derived(
    data?.equipments.filter((e) => e.group === 'normal' || e.group === 'stopped') ?? [],
  )
  const updated = $derived(data ? fmtAge(ageSince(data.generated_at_utc, app.now)) : '')

  /** Vazão com unidade; leitura sem valor utilizável vira travessão, nunca zero. */
  function flowText(entry: SituationEntry): string {
    const flow = entry.mass_flow
    if (!flow || !flow.is_usable || flow.value == null) return '—'
    return `${fmtNumber(flow.value, flow.decimals)} ${flow.unit}`.trim()
  }
</script>

<div class="now-wrap">
<section class="now" data-testid="now">
  {#if error && !data}
    <EmptyState title="Sem resposta do Edge" text={error}>
      <button class="retry" type="button" onclick={() => void load()}>Tentar de novo</button>
    </EmptyState>
  {:else if !data || !summary}
    <p class="loading" data-testid="now-loading">Lendo a situação da planta…</p>
  {:else}
    <div class="manager" aria-labelledby="now-headline">
      <p class="label">Para o gerente · atualizado {updated}</p>
      {#key summary.headline_pt}
        <div class="headline" data-tone={summary.tone}>
          <span class="ico" aria-hidden="true">
            {#if summary.tone === 'ok'}<Check size={26} />{:else}<TriangleAlert size={26} />{/if}
          </span>
          <h1 id="now-headline" data-testid="now-headline">{summary.headline_pt}</h1>
        </div>
      {/key}
      <dl class="numbers">
        <div data-testid="now-count-normal">
          <dt>{summary.normal + summary.stopped === 1 ? 'normal' : 'normais'}</dt>
          <dd class="big ok">{summary.normal + summary.stopped}</dd>
        </div>
        <div data-testid="now-count-attention">
          <dt>em atenção</dt>
          <dd class="big" class:warn={summary.attention > 0}>{summary.attention}</dd>
        </div>
        <div data-testid="now-count-nodata">
          <dt>sem dados</dt>
          <dd class="big muted">{summary.no_data}</dd>
        </div>
      </dl>
    </div>

    <div class="maintenance">
      <h2 class="label">Para a manutenção</h2>
      {#each problems as entry (entry.id)}
        <NowCard {entry} now={app.now} />
      {:else}
        <p class="calm" data-testid="now-nothing"><Check size={20} aria-hidden="true" /> Nada para verificar agora.</p>
      {/each}

      {#if noData.length}
        <h2 class="label">Sem dados</h2>
        <ul class="rows" data-testid="now-nodata">
          {#each noData as entry (entry.id)}
            <li data-testid={`now-row-${entry.id}`}>
              <a class="row" href={href.eq(entry.id)}>
                <Badge tone={stateTone(entry.state_pt) === 'info' ? 'info' : 'neutral'}>{entry.state_pt}</Badge>
                <span class="row-name">{entry.name}</span>
                <span class="row-detail">{entry.reason_pt ?? ''}{sinceText(entry) ? ` · ${sinceText(entry)}` : ''}</span>
              </a>
            </li>
          {/each}
        </ul>
      {/if}

      {#if calm.length}
        <h2 class="label">Normais</h2>
        <ul class="rows" data-testid="now-normal">
          {#each calm as entry (entry.id)}
            <li data-testid={`now-row-${entry.id}`}>
              <a class="row" href={href.eq(entry.id)}>
                <StatusDot state={entry.group === 'stopped' ? 'neutral' : 'ok'} />
                <span class="row-name">{entry.name}</span>
                {#if entry.group === 'stopped'}<Badge tone="neutral">Parado</Badge>{/if}
                <span class="row-value num">{flowText(entry)}</span>
              </a>
            </li>
          {/each}
        </ul>
      {/if}
    </div>
  {/if}
</section>
</div>

<style>
  /* a largura que decide o layout é a da área de conteúdo, não a da janela */
  .now-wrap { container-type: inline-size; }
  .now {
    display: grid;
    gap: var(--sp-5);
    grid-template-columns: minmax(0, 1fr);
    align-items: start;
  }
  @container (min-width: 880px) {
    .now { grid-template-columns: minmax(260px, 340px) minmax(0, 1fr); }
    .manager { position: sticky; top: var(--sp-4); }
  }
  .manager, .maintenance { display: flex; flex-direction: column; gap: var(--sp-3); min-width: 0; }
  .manager {
    padding: var(--sp-5);
    border: 1px solid var(--border-1);
    border-radius: var(--r-4);
    background: var(--surf-1);
  }
  .label { margin: 0; }
  .headline { display: flex; align-items: center; gap: var(--sp-3); color: var(--st-warn); animation: rise var(--dur-screen) var(--ease-out) both; }
  .headline[data-tone='ok'] { color: var(--st-ok); }
  .headline[data-tone='crit'] { color: var(--st-crit); }
  .headline[data-tone='info'] { color: var(--st-info); }
  .ico { display: grid; place-items: center; flex: none; width: 48px; height: 48px; border-radius: var(--r-pill); background: currentColor; }
  .ico :global(svg) { color: var(--on-accent); }
  h1 { margin: 0; color: var(--text-1); font: 600 var(--fs-display) / var(--lh-display) var(--font-ui); }
  .numbers { display: flex; flex-direction: column; gap: var(--sp-2); margin: var(--sp-2) 0 0; }
  .numbers div { display: flex; align-items: baseline; gap: var(--sp-2); }
  .numbers dt { order: 2; color: var(--text-2); font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  .numbers dd { margin: 0; }
  .big { min-width: 1.6ch; color: var(--text-1); font: 500 40px / 44px var(--font-mono); font-variant-numeric: tabular-nums; }
  .big.ok { color: var(--st-ok); }
  .big.warn { color: var(--st-warn); }
  .big.muted { color: var(--text-2); }
  .calm { display: flex; align-items: center; gap: var(--sp-2); margin: 0; color: var(--st-ok); font: 600 var(--fs-body-lg) / var(--lh-body-lg) var(--font-ui); }
  .rows { display: flex; flex-direction: column; gap: var(--sp-1); margin: 0; padding: 0; list-style: none; }
  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--sp-2) var(--sp-3);
    min-height: var(--touch);
    padding: var(--sp-2) var(--sp-3);
    border-radius: var(--r-2);
    background: var(--surf-1);
    color: inherit;
    text-decoration: none;
    transition: background-color var(--dur-micro) var(--ease-std);
  }
  .row:hover { background: var(--surf-2); }
  .row-name { color: var(--text-1); font: 500 var(--fs-body) / var(--lh-body) var(--font-ui); }
  .row-detail { color: var(--text-2); font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  .row-value { margin-left: auto; color: var(--text-2); }
  .loading { margin: 0; color: var(--text-2); }
  .retry {
    min-height: var(--touch);
    padding: 0 var(--sp-4);
    border: 1px solid var(--accent);
    border-radius: var(--r-3);
    background: var(--accent);
    color: var(--on-accent);
    font: 600 var(--fs-body) / 1.2 var(--font-ui);
    cursor: pointer;
  }
  @keyframes rise {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: none; }
  }
  @media (max-width: 560px) {
    h1 { font-size: var(--fs-h1); line-height: var(--lh-h1); }
    .ico { width: 40px; height: 40px; }
  }
</style>
