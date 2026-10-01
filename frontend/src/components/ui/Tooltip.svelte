<script lang="ts">
  /** Explicação sob demanda: abre no clique/teclado, nunca depende de hover. */
  import type { Snippet } from 'svelte'

  let {
    text,
    label,
    align = 'start',
    testid,
    children,
  }: {
    text: string
    label: string
    align?: 'start' | 'end'
    testid?: string
    children?: Snippet
  } = $props()

  let open = $state(false)
  let root: HTMLElement | undefined = $state()
  const popId = $props.id()

  $effect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (root && !root.contains(e.target as Node)) open = false
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') open = false
    }
    document.addEventListener('click', onClick, true)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('click', onClick, true)
      document.removeEventListener('keydown', onKey)
    }
  })
</script>

<span class="tip" bind:this={root} data-align={align}>
  <button
    type="button"
    class="tip-btn"
    aria-expanded={open}
    aria-controls={popId}
    aria-label={label}
    data-testid={testid}
    onclick={() => (open = !open)}
  >
    {@render children?.()}
  </button>
  {#if open}
    <span class="tip-pop" role="note" id={popId}>{text}</span>
  {/if}
</span>

<style>
  .tip { position: relative; display: inline-flex; }
  .tip-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-height: 32px;
    padding: 0 var(--sp-2);
    border: 0;
    border-radius: var(--r-2);
    background: transparent;
    color: inherit;
    font: inherit;
    cursor: pointer;
    transition: background-color var(--dur-base) var(--ease-std);
  }
  .tip-btn:hover { background: var(--surf-2); }
  @media (max-width: 767px), (pointer: coarse) {
    .tip-btn { min-height: var(--touch); }
  }
  .tip-pop {
    position: absolute;
    top: calc(100% + 6px);
    z-index: 30;
    min-width: 220px;
    max-width: min(320px, 80vw);
    padding: var(--sp-3) var(--sp-4);
    border: 1px solid var(--border-2);
    border-radius: var(--r-3);
    background: var(--surf-3);
    box-shadow: var(--elev-2);
    color: var(--text-1);
    font: var(--fs-caption) / var(--lh-caption) var(--font-ui);
    text-transform: none;
    letter-spacing: 0;
    white-space: normal;
    animation: pop var(--dur-base) var(--ease-out) both;
  }
  .tip[data-align='start'] .tip-pop { left: 0; }
  .tip[data-align='end'] .tip-pop { right: 0; }
  @keyframes pop {
    from { opacity: 0; transform: translateY(-4px); }
    to { opacity: 1; transform: none; }
  }
</style>
