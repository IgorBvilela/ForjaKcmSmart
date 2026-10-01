<script lang="ts">
  import type { Snippet } from 'svelte'
  import Inbox from '@lucide/svelte/icons/inbox'
  import { TID } from '../../lib/testids'

  let {
    title,
    text,
    phase,
    icon,
    children,
    compact = false,
    inline = false,
    testid = TID.emptyState,
  }: {
    title: string
    text?: string
    phase?: string
    icon?: Snippet
    children?: Snippet
    compact?: boolean
    /** Dentro de um card: sem glifo, alinhado à esquerda, texto corrido. */
    inline?: boolean
    testid?: string
  } = $props()
</script>

<div class="empty" class:compact class:inline data-testid={testid} data-phase={phase ?? ''}>
  {#if !inline}
    <div class="glyph" aria-hidden="true">
      {#if icon}{@render icon()}{:else}<Inbox size={compact ? 20 : 28} strokeWidth={1.5} />{/if}
    </div>
  {/if}
  <h2 class="title">{title}</h2>
  {#if phase}<p class="phase label">Disponível na fase {phase}</p>{/if}
  {#if text}<p class="text">{text}</p>{/if}
  {@render children?.()}
</div>

<style>
  .empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    gap: var(--sp-2);
    padding: var(--sp-12) var(--sp-6);
    border: 1px dashed var(--border-2);
    border-radius: var(--r-4);
    background: var(--surf-1);
    color: var(--text-2);
  }
  .compact {
    padding: var(--sp-6) var(--sp-4);
    border-style: solid;
    border-color: var(--border-1);
  }
  .glyph {
    display: grid;
    place-items: center;
    width: 56px;
    height: 56px;
    border-radius: 50%;
    background: var(--surf-2);
    color: var(--text-3);
    margin-bottom: var(--sp-2);
  }
  .compact .glyph { width: 40px; height: 40px; margin-bottom: 0; }
  .title {
    margin: 0;
    font: 600 var(--fs-h3) / var(--lh-h3) var(--font-ui);
    color: var(--text-1);
  }
  .phase { margin: 0; color: var(--text-3); }
  .inline {
    align-items: flex-start;
    text-align: left;
    gap: var(--sp-1);
    padding: var(--sp-3) 0;
    border: 0;
    background: transparent;
  }
  .inline .title {
    font: 500 var(--fs-body) / var(--lh-body) var(--font-ui);
    color: var(--text-2);
  }
  .inline .text { color: var(--text-3); max-width: 60ch; }
  .text {
    margin: 0;
    max-width: 48ch;
    font: var(--fs-body) / var(--lh-body) var(--font-ui);
    color: var(--text-2);
  }
</style>
