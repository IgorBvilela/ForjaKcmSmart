<script lang="ts">
  import type { Snippet } from 'svelte'

  let {
    title,
    kicker,
    actions,
    children,
    padded = true,
    testid,
    as = 'section',
    class: className = '',
    ...rest
  }: {
    title?: string
    kicker?: string
    actions?: Snippet
    children?: Snippet
    padded?: boolean
    testid?: string
    as?: 'section' | 'article' | 'div' | 'aside'
    class?: string
    [key: string]: unknown
  } = $props()

  const headingId = $props.id()
</script>

<svelte:element
  this={as}
  class={`card ${className}`}
  class:padded
  data-testid={testid}
  aria-labelledby={title ? headingId : undefined}
  {...rest}
>
  {#if title || kicker || actions}
    <header class="card-head">
      <div class="card-titles">
        {#if kicker}<span class="label">{kicker}</span>{/if}
        {#if title}<h2 class="card-title" id={headingId}>{title}</h2>{/if}
      </div>
      {#if actions}<div class="card-actions">{@render actions()}</div>{/if}
    </header>
  {/if}
  {@render children?.()}
</svelte:element>

<style>
  .card {
    background: var(--surf-1);
    border: 1px solid var(--border-1);
    border-radius: var(--r-4);
    box-shadow: var(--elev-1);
    min-width: 0;
  }
  .padded { padding: var(--sp-5); }
  @media (max-width: 767px) {
    .padded { padding: var(--sp-4); }
  }
  .card-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--sp-3);
    margin-bottom: var(--sp-4);
  }
  .card-titles {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }
  .card-title {
    margin: 0;
    font: 600 var(--fs-h2) / var(--lh-h2) var(--font-ui);
    color: var(--text-1);
  }
  .card-actions {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    flex: none;
  }
</style>
