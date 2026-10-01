<script lang="ts">
  /** Faixa permanente de origem dos dados. Lilás com hachura quando simulado. Abaixo de 768 px
   *  recebe o selo Somente leitura (que nunca some). Edge offline ganha uma segunda faixa. */
  import WifiOff from '@lucide/svelte/icons/wifi-off'
  import { DATA_SOURCE_PT, live } from '../../lib/live.svelte'
  import { app } from '../../lib/state.svelte'
  import { TID } from '../../lib/testids'
  import type { DataSource } from '../../lib/api'
  import ReadOnlyBadge from './ReadOnlyBadge.svelte'

  const selectedId = $derived(app.route.name === 'eq' ? app.route.id : null)
  const source: DataSource | null = $derived.by(() => {
    if (selectedId) {
      const card = live.cardOf(selectedId)
      if (card) return card.data_source
    }
    return live.dataSource
  })
  const text = $derived(source ? DATA_SOURCE_PT[source] : 'ORIGEM DOS DADOS: consultando o Edge')
  const detail = $derived(
    source === 'SIMULATED'
      ? 'nenhum valor representa um KCM real'
      : source === 'EQUIPMENT'
        ? 'leitura direta do KCM via Host/Anybus'
        : source === 'MIXED'
          ? 'cada card e cada valor mostram a própria origem'
          : '',
  )
  const offlineFor = $derived(
    live.lastHeartbeatAt ? Math.round((app.now - live.lastHeartbeatAt) / 1000) : null,
  )
</script>

<div
  class="banner"
  data-testid={TID.banner.dataSource}
  data-source={source ?? ''}
  role="status"
  aria-live="polite"
>
  <span class="banner-text">
    <strong class="banner-main">{text}</strong>
    {#if detail}<span class="banner-detail"> · {detail}</span>{/if}
  </span>
  {#if app.isMobile}
    <span class="banner-ro"><ReadOnlyBadge compact align="end" /></span>
  {/if}
</div>

{#if live.edge === 'offline'}
  <div class="offline" data-testid={TID.banner.edgeOffline} role="alert">
    <WifiOff size={14} aria-hidden="true" />
    <span>
      <strong>EDGE SEM RESPOSTA</strong>
      {#if offlineFor != null} · sem sinal do serviço local há {offlineFor} s{/if}
      · os valores na tela são os últimos recebidos
    </span>
  </div>
{/if}

<style>
  .banner {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--sp-3);
    min-height: var(--banner-h);
    padding: 0 var(--sp-6);
    border-bottom: 1px solid var(--border-1);
    background: var(--surf-1);
    color: var(--text-2);
    font: 500 var(--fs-label) / var(--lh-label) var(--font-ui);
    letter-spacing: var(--ls-label);
    text-transform: uppercase;
  }
  .banner[data-source='SIMULATED'] {
    color: var(--q-sim);
    background-color: var(--surf-1);
    background-image: var(--q-sim-hatch);
    border-bottom-color: color-mix(in srgb, var(--q-sim) 35%, var(--border-1));
  }
  .banner[data-source='EQUIPMENT'] { color: var(--st-info); }
  .banner[data-source='MIXED'] { color: var(--st-warn); }
  .banner-text { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .banner-main { font-weight: 600; }
  .banner-detail { color: var(--text-3); text-transform: none; letter-spacing: 0; }
  .banner-ro { flex: none; }

  .offline {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    min-height: var(--banner-h);
    padding: var(--sp-1) var(--sp-6);
    border-bottom: 1px solid var(--border-1);
    background: var(--st-crit-bg);
    color: var(--st-crit);
    font: var(--fs-caption) / var(--lh-caption) var(--font-ui);
  }
  .offline strong { font-weight: 600; letter-spacing: var(--ls-label); }

  @media (max-width: 767px) {
    .banner,
    .offline { padding-left: var(--sp-4); padding-right: var(--sp-4); }
    .banner { min-height: 40px; }
    .banner-detail { display: none; }
  }
  /* 320 px / zoom 200 %: o selo fica só com o cadeado (o nome acessível continua no botão) */
  @media (max-width: 359px) {
    .banner-ro :global(.txt) { display: none; }
    .banner-ro :global(.tip-btn) { min-width: var(--touch); justify-content: center; }
  }
</style>
