<script lang="ts">
  /** Linha do tempo vertical. Cada item já vem traduzido e com tom (nunca cobre). */
  import { fmtWhen } from '../../lib/format'
  import { app } from '../../lib/state.svelte'
  import { TID } from '../../lib/testids'
  import type { TimelineItem } from '../../lib/timeline'
  import StatusDot from '../ui/StatusDot.svelte'

  let {
    items = [],
    emptyText = 'Nenhum evento registrado.',
    testid = TID.timeline,
  }: { items?: TimelineItem[]; emptyText?: string; testid?: string } = $props()
</script>

<ol class="tl" data-testid={testid} data-count={items.length}>
  {#if items.length === 0}
    <li class="tl-empty">{emptyText}</li>
  {/if}
  {#each items as item, i (item.id)}
    <li class="tl-item" class:muted={item.muted} style:--i={i}>
      <time class="tl-time num" datetime={item.ts_utc}>{fmtWhen(item.ts_utc, app.now)}</time>
      <span class="tl-mark"><StatusDot state={item.tone} size={8} hollow={item.muted} /></span>
      <div class="tl-body">
        {#if item.href}
          <a class="tl-title" href={item.href}>{item.title}</a>
        {:else}
          <span class="tl-title">{item.title}</span>
        {/if}
        {#if item.text}<span class="tl-text">{item.text}</span>{/if}
        {#if item.meta}<span class="tl-meta">{item.meta}</span>{/if}
      </div>
    </li>
  {/each}
</ol>

<style>
  .tl {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
  }
  .tl-empty {
    color: var(--text-3);
    font: var(--fs-body) / var(--lh-body) var(--font-ui);
    padding: var(--sp-2) 0;
  }
  .tl-item {
    position: relative;
    display: grid;
    grid-template-columns: 64px 16px minmax(0, 1fr);
    gap: var(--sp-3);
    align-items: start;
    padding: var(--sp-2) 0;
    animation: rise var(--dur-screen) var(--ease-out) backwards;
    animation-delay: calc(var(--i, 0) * var(--stagger));
  }
  @keyframes rise {
    from { opacity: 0; transform: translateY(4px); }
    to { opacity: 1; transform: none; }
  }
  .tl-item::before {
    content: '';
    position: absolute;
    left: calc(64px + var(--sp-3) + 7px);
    top: 0;
    bottom: 0;
    width: 1px;
    background: var(--border-1);
  }
  .tl-item:first-child::before { top: 50%; }
  .tl-item:last-child::before { bottom: 50%; }
  .tl-item:only-child::before { display: none; }
  .tl-time {
    font-size: var(--fs-mono-sm);
    line-height: var(--lh-body);
    color: var(--text-3);
    white-space: nowrap;
  }
  .tl-mark {
    position: relative;
    z-index: 1;
    display: grid;
    place-items: center;
    height: var(--lh-body);
    background: var(--surf-1);
  }
  .tl-body {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }
  .tl-title {
    color: var(--text-1);
    font: 500 var(--fs-body) / var(--lh-body) var(--font-ui);
    text-decoration: none;
    border-radius: var(--r-1);
  }
  a.tl-title:hover { color: var(--accent-text); }
  .tl-text,
  .tl-meta {
    color: var(--text-3);
    font: var(--fs-caption) / var(--lh-caption) var(--font-ui);
  }
  .muted .tl-title { color: var(--text-2); font-weight: 400; }
  @media (max-width: 767px) {
    .tl-item { grid-template-columns: 60px 16px minmax(0, 1fr); gap: var(--sp-2); }
    .tl-item::before { left: calc(60px + var(--sp-2) + 7px); }
  }
  /* toque: título-link com 44 px; o padding do item garante que as áreas não se sobreponham */
  @media (max-width: 767px), (pointer: coarse) {
    .tl-item { padding: var(--sp-3) 0; }
    a.tl-title { display: inline-block; padding: 12px 0; margin: -12px 0; }
  }
</style>
