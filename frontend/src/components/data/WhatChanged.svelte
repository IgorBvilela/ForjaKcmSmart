<script lang="ts">
  /** ANTES / AGORA / VARIAÇÃO por variável. "Mudou primeiro" é a ordem da história, não causa. */
  import type { WhatChangedItem } from '../../lib/api'
  import { deltaDirection, fmtDelta, fmtNumber, fmtTime } from '../../lib/format'
  import Badge from '../ui/Badge.svelte'

  let {
    items = [],
    limit,
    compact = false,
  }: { items?: WhatChangedItem[]; limit?: number; compact?: boolean } = $props()

  const shown = $derived(limit ? items.slice(0, limit) : items)

  function decimalsFor(item: WhatChangedItem): number {
    const ref = Math.max(Math.abs(item.before ?? 0), Math.abs(item.now ?? 0))
    if (ref >= 1000) return 0
    if (ref >= 100) return 1
    return 2
  }
</script>

{#if shown.length === 0}
  <p class="none">Nenhuma variável saiu do padrão neste evento.</p>
{:else}
  <div class="wc" class:compact role="table" aria-label="O que mudou: antes, agora e variação">
    <div class="row head" role="row">
      <span role="columnheader" class="label">Variável</span>
      <span role="columnheader" class="label num-col">Antes</span>
      <span role="columnheader" class="label num-col">Agora</span>
      <span role="columnheader" class="label num-col">Variação</span>
    </div>
    {#each shown as item (item.tag)}
      <div class="row" role="row" data-tag={item.tag} class:first={item.changed_first}>
        <span role="cell" class="var">
          <span class="var-name">{item.label_pt}</span>
          {#if item.changed_first}
            <Badge tone="ghost" title="Primeira variável a sair do padrão">mudou primeiro</Badge>
          {/if}
          {#if item.ts_start_utc && !compact}
            <span class="when">saiu do padrão às {fmtTime(item.ts_start_utc)}</span>
          {/if}
        </span>
        <span role="cell" class="num num-col">
          {fmtNumber(item.before, decimalsFor(item))}<span class="unit">{item.unit}</span>
        </span>
        <span role="cell" class="num num-col strong">
          {fmtNumber(item.now, decimalsFor(item))}<span class="unit">{item.unit}</span>
        </span>
        <span role="cell" class="num num-col delta" data-dir={deltaDirection(item.delta)}>
          {fmtDelta(item)}
        </span>
      </div>
    {/each}
  </div>
{/if}

<style>
  .none {
    margin: 0;
    color: var(--text-3);
    font: var(--fs-body) / var(--lh-body) var(--font-ui);
  }
  .wc {
    display: flex;
    flex-direction: column;
    border: 1px solid var(--border-1);
    border-radius: var(--r-3);
    overflow: hidden;
  }
  .row {
    display: grid;
    grid-template-columns: minmax(0, 2fr) repeat(3, minmax(88px, 1fr));
    gap: var(--sp-3);
    align-items: center;
    padding: var(--sp-3) var(--sp-4);
    border-top: 1px solid var(--border-1);
    background: var(--surf-1);
  }
  .row.head {
    border-top: 0;
    background: var(--surf-2);
    padding-top: var(--sp-2);
    padding-bottom: var(--sp-2);
  }
  .row.first { background: var(--surf-2); }
  .var {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--sp-2);
    min-width: 0;
    color: var(--text-1);
    font: 500 var(--fs-body) / var(--lh-body) var(--font-ui);
  }
  .when {
    flex-basis: 100%;
    color: var(--text-3);
    font: var(--fs-caption) / var(--lh-caption) var(--font-ui);
  }
  .num-col { text-align: right; }
  .num {
    font-size: var(--fs-mono);
    line-height: var(--lh-mono);
    color: var(--text-2);
    white-space: nowrap;
  }
  .num.strong { color: var(--text-1); }
  .unit {
    margin-left: 4px;
    color: var(--text-3);
    font-size: var(--fs-mono-sm);
  }
  .delta { color: var(--text-1); }
  .delta[data-dir='flat'] { color: var(--text-3); }
  @media (max-width: 767px) {
    .row {
      grid-template-columns: repeat(3, minmax(0, 1fr));
      row-gap: var(--sp-1);
    }
    .row.head { display: none; }
    .var { grid-column: 1 / -1; }
    .num-col { text-align: left; }
    .num::before {
      display: block;
      content: attr(data-label);
      color: var(--text-3);
      font: 500 var(--fs-label) / var(--lh-label) var(--font-ui);
      letter-spacing: var(--ls-label);
      text-transform: uppercase;
    }
    .row .num-col:nth-child(2)::before { content: 'Antes'; }
    .row .num-col:nth-child(3)::before { content: 'Agora'; }
    .row .num-col:nth-child(4)::before { content: 'Variação'; }
  }
</style>
