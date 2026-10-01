<script lang="ts">
  import type { StateTone } from '../../lib/api'

  let {
    state = 'neutral',
    pulse = false,
    hollow = false,
    size = 8,
    label = '',
  }: { state?: StateTone | 'sim'; pulse?: boolean; hollow?: boolean; size?: number; label?: string } =
    $props()

  const px = $derived(`${size}px`)
</script>

<span
  class="dot"
  class:hollow
  data-state={state}
  style:--dot-size={px}
  role={label ? 'img' : undefined}
  aria-label={label || undefined}
  aria-hidden={label ? undefined : 'true'}
>
  {#if pulse}<span class="ring pulse"></span>{/if}
</span>

<style>
  .dot {
    position: relative;
    display: inline-block;
    width: var(--dot-size, 8px);
    height: var(--dot-size, 8px);
    border-radius: 50%;
    background: var(--dot-color);
    flex: none;
    vertical-align: middle;
  }
  .dot[data-state='ok'] { --dot-color: var(--st-ok); }
  .dot[data-state='warn'] { --dot-color: var(--st-warn); }
  .dot[data-state='crit'] { --dot-color: var(--st-crit); }
  .dot[data-state='info'] { --dot-color: var(--st-info); }
  .dot[data-state='sim'] { --dot-color: var(--q-sim); }
  .dot[data-state='neutral'] { --dot-color: var(--text-3); }
  .dot[data-state='unknown'] { --dot-color: var(--chumbo); }
  .dot.hollow {
    background: transparent;
    box-shadow: inset 0 0 0 1.5px var(--dot-color);
  }
  .ring {
    position: absolute;
    inset: 0;
    border-radius: 50%;
    background: var(--dot-color);
    opacity: 0.45;
    animation: pulse var(--pulse-cycle) var(--ease-out) infinite;
  }
  @keyframes pulse {
    0% { transform: scale(1); opacity: 0.45; }
    70% { transform: scale(2.6); opacity: 0; }
    100% { transform: scale(2.6); opacity: 0; }
  }
</style>
