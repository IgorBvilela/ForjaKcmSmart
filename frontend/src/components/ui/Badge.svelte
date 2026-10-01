<script lang="ts">
  import type { Snippet } from 'svelte'

  export type BadgeTone =
    | 'neutral'
    | 'ok'
    | 'warn'
    | 'crit'
    | 'info'
    | 'sim'
    | 'accent'
    | 'ghost'
    | 'unknown'

  let {
    tone = 'neutral',
    hatch = false,
    dashed = false,
    uppercase = true,
    size = 'sm',
    title,
    testid,
    children,
    ...rest
  }: {
    tone?: BadgeTone
    hatch?: boolean
    dashed?: boolean
    uppercase?: boolean
    size?: 'sm' | 'md'
    title?: string
    testid?: string
    children?: Snippet
    [key: string]: unknown
  } = $props()
</script>

<span
  class="badge"
  class:hatch
  class:dashed
  class:upper={uppercase}
  data-tone={tone}
  data-size={size}
  data-testid={testid}
  {title}
  {...rest}
>
  {@render children?.()}
</span>

<style>
  .badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 2px 8px;
    border-radius: var(--r-pill);
    border: 1px solid var(--badge-border, var(--border-2));
    background: var(--badge-bg, transparent);
    color: var(--badge-fg, var(--text-2));
    font: 500 var(--fs-label) / var(--lh-label) var(--font-ui);
    white-space: nowrap;
    max-width: 100%;
  }
  .badge[data-size='md'] {
    padding: 4px 10px;
    font-size: var(--fs-caption);
    line-height: var(--lh-caption);
  }
  .upper {
    text-transform: uppercase;
    letter-spacing: var(--ls-label);
  }
  .dashed { border-style: dashed; }
  .hatch { background-image: var(--q-sim-hatch); }

  .badge[data-tone='ok'] { --badge-fg: var(--st-ok); --badge-bg: var(--st-ok-bg); --badge-border: transparent; }
  .badge[data-tone='warn'] { --badge-fg: var(--st-warn); --badge-bg: var(--st-warn-bg); --badge-border: transparent; }
  .badge[data-tone='crit'] { --badge-fg: var(--st-crit); --badge-bg: var(--st-crit-bg); --badge-border: transparent; }
  .badge[data-tone='info'] { --badge-fg: var(--st-info); --badge-bg: var(--st-info-bg); --badge-border: transparent; }
  .badge[data-tone='sim'] { --badge-fg: var(--q-sim); --badge-bg: transparent; --badge-border: color-mix(in srgb, var(--q-sim) 45%, transparent); }
  .badge[data-tone='accent'] { --badge-fg: var(--accent-text); --badge-bg: var(--accent-soft); --badge-border: transparent; }
  .badge[data-tone='ghost'] { --badge-fg: var(--text-3); --badge-bg: transparent; --badge-border: var(--border-1); }
  .badge[data-tone='unknown'] { --badge-fg: var(--text-3); --badge-bg: transparent; --badge-border: var(--chumbo); border-style: dashed; }
</style>
