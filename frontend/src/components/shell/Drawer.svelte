<script lang="ts">
  /** Drawer lateral com scrim para < 1024 px. Escape fecha; foco entra no painel e volta ao sair. */
  import type { Snippet } from 'svelte'
  import { TID } from '../../lib/testids'

  let {
    open = false,
    onclose,
    children,
  }: { open?: boolean; onclose: () => void; children?: Snippet } = $props()

  let panel: HTMLElement | undefined = $state()
  let previous: Element | null = null

  $effect(() => {
    if (!open) return
    previous = document.activeElement
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onclose()
    }
    document.addEventListener('keydown', onKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    queueMicrotask(() => {
      const first = panel?.querySelector<HTMLElement>('a[href], button:not([disabled])')
      first?.focus()
    })
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
      if (previous instanceof HTMLElement) previous.focus()
    }
  })
</script>

{#if open}
  <div class="drawer-root">
    <div
      class="scrim"
      data-testid={TID.sidebar.scrim}
      onclick={onclose}
      role="presentation"
    ></div>
    <div
      class="panel"
      id="sidebar"
      role="dialog"
      aria-modal="true"
      aria-label="Menu de navegação"
      bind:this={panel}
    >
      {@render children?.()}
    </div>
  </div>
{/if}

<style>
  .drawer-root {
    position: fixed;
    inset: 0;
    z-index: 40;
  }
  .scrim {
    position: absolute;
    inset: 0;
    background: var(--scrim);
    animation: fade var(--dur-screen) var(--ease-out) both;
  }
  .panel {
    position: absolute;
    top: 0;
    bottom: 0;
    left: 0;
    width: min(var(--drawer-w), 86vw);
    background: var(--surf-1);
    box-shadow: var(--elev-3);
    animation: slide var(--dur-screen) var(--ease-out) both;
    display: flex;
    flex-direction: column;
  }
  @keyframes fade {
    from { opacity: 0; }
    to { opacity: 1; }
  }
  @keyframes slide {
    from { transform: translateX(-16px); opacity: 0; }
    to { transform: none; opacity: 1; }
  }
</style>
