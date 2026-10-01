<script lang="ts">
  import type { Snippet } from 'svelte'

  let {
    variant = 'ghost',
    size = 'md',
    href,
    type = 'button',
    disabled = false,
    pressed,
    testid,
    children,
    class: className = '',
    ...rest
  }: {
    variant?: 'primary' | 'ghost' | 'subtle' | 'link'
    size?: 'sm' | 'md'
    href?: string
    type?: 'button' | 'submit'
    disabled?: boolean
    pressed?: boolean
    testid?: string
    children?: Snippet
    class?: string
    [key: string]: unknown
  } = $props()
</script>

{#if href}
  <a
    class={`btn ${className}`}
    data-variant={variant}
    data-size={size}
    data-testid={testid}
    {href}
    aria-disabled={disabled || undefined}
    {...rest}
  >
    {@render children?.()}
  </a>
{:else}
  <button
    class={`btn ${className}`}
    data-variant={variant}
    data-size={size}
    data-testid={testid}
    {type}
    {disabled}
    aria-pressed={pressed}
    {...rest}
  >
    {@render children?.()}
  </button>
{/if}

<style>
  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--sp-2);
    min-height: 36px;
    padding: 0 var(--sp-4);
    border-radius: var(--r-3);
    border: 1px solid transparent;
    font: 500 var(--fs-body) / var(--lh-body) var(--font-ui);
    color: var(--text-1);
    background: transparent;
    cursor: pointer;
    text-decoration: none;
    white-space: nowrap;
    transition:
      background-color var(--dur-base) var(--ease-std),
      border-color var(--dur-base) var(--ease-std),
      color var(--dur-base) var(--ease-std);
  }
  .btn[data-size='sm'] {
    min-height: 32px;
    padding: 0 var(--sp-3);
    font-size: var(--fs-caption);
    line-height: var(--lh-caption);
  }
  .btn[data-variant='primary'] {
    background: var(--accent);
    color: var(--on-accent);
    border-color: var(--accent);
  }
  .btn[data-variant='primary']:hover { filter: brightness(1.08); }
  .btn[data-variant='ghost'] {
    border-color: var(--border-2);
    color: var(--text-1);
  }
  .btn[data-variant='ghost']:hover { background: var(--surf-2); }
  .btn[data-variant='ghost'][aria-pressed='true'] {
    background: var(--surf-2);
    border-color: var(--accent);
    color: var(--text-1);
  }
  .btn[data-variant='subtle'] { color: var(--text-2); }
  .btn[data-variant='subtle']:hover { background: var(--surf-2); color: var(--text-1); }
  .btn[data-variant='link'] {
    padding: 0;
    min-height: 0;
    color: var(--accent-text);
    border-radius: var(--r-1);
  }
  .btn[data-variant='link']:hover { text-decoration: underline; }
  .btn:disabled,
  .btn[aria-disabled='true'] {
    color: var(--text-disabled);
    cursor: not-allowed;
    border-color: var(--border-1);
    background: transparent;
    filter: none;
  }
  /* toque e celular: tudo com 44 px; o link ganha área por padding e devolve o espaço com margem negativa */
  @media (max-width: 767px), (pointer: coarse) {
    .btn { min-height: var(--touch); }
    .btn[data-size='sm'] { min-height: var(--touch); }
    .btn[data-variant='link'] {
      min-height: var(--touch);
      padding: 12px var(--sp-2);
      margin: -12px calc(-1 * var(--sp-2));
    }
  }
</style>
