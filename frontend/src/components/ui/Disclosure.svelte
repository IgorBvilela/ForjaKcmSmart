<script lang="ts">
  import type { Snippet } from 'svelte'
  import ChevronRight from '@lucide/svelte/icons/chevron-right'

  let {
    summary,
    open = $bindable(false),
    size = 'md',
    testid,
    children,
  }: {
    summary: string
    open?: boolean
    size?: 'sm' | 'md'
    testid?: string
    children?: Snippet
  } = $props()

  const bodyId = $props.id()
</script>

<div class="disc" class:open data-size={size}>
  <button
    type="button"
    class="disc-btn"
    aria-expanded={open}
    aria-controls={bodyId}
    data-testid={testid}
    onclick={() => (open = !open)}
  >
    <span class="chev" aria-hidden="true"><ChevronRight size={size === 'sm' ? 14 : 16} /></span>
    <span class="disc-label">{summary}</span>
  </button>
  {#if open}
    <div class="disc-body" id={bodyId}>{@render children?.()}</div>
  {/if}
</div>

<style>
  .disc { min-width: 0; }
  .disc-btn {
    display: inline-flex;
    align-items: center;
    gap: var(--sp-1);
    min-height: 32px;
    padding: 0 var(--sp-2) 0 0;
    border: 0;
    background: transparent;
    color: var(--text-2);
    font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui);
    cursor: pointer;
    border-radius: var(--r-1);
    transition: color var(--dur-base) var(--ease-std);
  }
  .disc[data-size='md'] .disc-btn {
    font-size: var(--fs-body);
    line-height: var(--lh-body);
    min-height: 36px;
  }
  @media (max-width: 767px), (pointer: coarse) {
    .disc-btn { min-height: var(--touch); }
  }
  .disc-btn:hover { color: var(--text-1); }
  .chev {
    display: inline-grid;
    place-items: center;
    color: var(--text-3);
    transition: transform var(--dur-base) var(--ease-std);
  }
  .open .chev { transform: rotate(90deg); }
  .disc-body {
    padding: var(--sp-2) 0 var(--sp-1) var(--sp-5);
    color: var(--text-2);
    font: var(--fs-body) / var(--lh-body) var(--font-ui);
    animation: reveal var(--dur-base) var(--ease-out) both;
  }
  @keyframes reveal {
    from { opacity: 0; transform: translateY(-2px); }
    to { opacity: 1; transform: none; }
  }
</style>
