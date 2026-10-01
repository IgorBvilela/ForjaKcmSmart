<script lang="ts">
  import type { Quality } from '../../lib/api'
  import { isUsable } from '../../lib/api'
  import type { SeriesPoint } from '../../lib/live.svelte'
  import { fmtNumber } from '../../lib/format'
  import { TID } from '../../lib/testids'
  import AnimatedNumber from './AnimatedNumber.svelte'
  import Sparkline from './Sparkline.svelte'
  import QualityBadge from '../ui/QualityBadge.svelte'
  import Disclosure from '../ui/Disclosure.svelte'

  let {
    tag,
    label,
    unit = '',
    decimals = 1,
    value = null,
    quality = 'COMM_ERROR',
    qualityPt = null,
    ageS = null,
    reasonPt = null,
    explanation = '',
    points = [],
    refValue = null,
    caption = null,
    color = 'var(--s1)',
    index = 0,
    animate = true,
  }: {
    tag: string
    label: string
    unit?: string
    decimals?: number
    value?: number | null
    quality?: Quality
    qualityPt?: string | null
    ageS?: number | null
    reasonPt?: string | null
    explanation?: string
    points?: SeriesPoint[]
    refValue?: number | null
    caption?: string | null
    color?: string
    index?: number
    animate?: boolean
  } = $props()

  const usable = $derived(isUsable(quality))
  const showsValue = $derived(usable || quality === 'STALE')
  const staleValue = $derived(quality === 'STALE' ? fmtNumber(value, decimals) : null)
</script>

<article
  class="tile"
  data-testid={TID.kpi.tile(tag)}
  data-tag={tag}
  data-quality={quality}
  class:stale={quality === 'STALE'}
  class:comm={quality === 'COMM_ERROR' || quality === 'BAD'}
  style:--i={index}
>
  <header class="tile-head">
    <span class="label">{label}</span>
  </header>

  <div class="tile-row">
    <div class="tile-value" aria-live="off">
      {#if usable}
        <AnimatedNumber {value} {decimals} animate={animate && usable} testid={TID.kpi.value(tag)} />
      {:else if quality === 'STALE'}
        <span class="num value" data-testid={TID.kpi.value(tag)} data-value={value ?? ''}>{staleValue}</span>
      {:else}
        <span class="num value" data-testid={TID.kpi.value(tag)} data-value="">—</span>
      {/if}
      {#if unit && showsValue}<span class="unit">{unit}</span>{/if}
    </div>
    <QualityBadge {quality} {qualityPt} {ageS} {reasonPt} testid={TID.kpi.quality(tag)} />
  </div>

  <p class="tile-sub">
    {#if quality === 'COMM_ERROR'}
      <span class="sub comm-text">Sem comunicação{reasonPt ? ` · ${reasonPt}` : ''}</span>
    {:else if quality === 'STALE'}
      <span class="sub">Último valor conhecido. Não é o estado atual.</span>
    {:else if quality === 'BAD'}
      <span class="sub">Leitura inválida{reasonPt ? ` · ${reasonPt}` : ''}</span>
    {:else if caption}
      <span class="sub">{caption}</span>
    {:else}
      <span class="sub">&nbsp;</span>
    {/if}
  </p>

  <Sparkline {points} {refValue} faded={!usable} {color} label={`Mini-tendência de ${label}`} />

  {#if explanation}
    <div class="tile-foot">
      <Disclosure summary="Entender esta variável" size="sm" testid={TID.kpi.explain(tag)}>
        <p class="explain">{explanation}</p>
      </Disclosure>
    </div>
  {/if}
</article>

<style>
  .tile {
    display: flex;
    flex-direction: column;
    gap: var(--sp-2);
    min-width: 0;
    padding: var(--sp-4) var(--sp-5);
    background: var(--surf-1);
    border: 1px solid var(--border-1);
    border-radius: var(--r-4);
    animation: rise var(--dur-screen) var(--ease-out) both;
    animation-delay: calc(var(--i, 0) * var(--stagger));
    transition:
      opacity var(--dur-base) var(--ease-std),
      border-color var(--dur-base) var(--ease-std);
  }
  @keyframes rise {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: none; }
  }
  .tile.stale {
    border-style: dashed;
    border-color: var(--border-2);
  }
  .tile.stale .tile-value { opacity: 0.55; }
  .tile.comm .tile-value { color: var(--text-3); }

  .tile-head { min-width: 0; }
  .tile-head .label {
    display: block;
    min-height: var(--lh-label);
    overflow-wrap: anywhere;
  }
  .tile-row {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: var(--sp-1) var(--sp-3);
    min-width: 0;
  }
  .tile-row :global(.q) { margin-bottom: 6px; }
  .tile-value {
    display: flex;
    align-items: baseline;
    gap: var(--sp-2);
    font-size: var(--fs-num-xl);
    line-height: var(--lh-num-xl);
    color: var(--text-1);
    min-height: var(--lh-num-xl);
  }
  .value { font-weight: 500; letter-spacing: -0.01em; }
  .unit {
    font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui);
    color: var(--text-3);
  }
  .tile-sub {
    margin: 0;
    min-height: var(--lh-caption);
    font: var(--fs-caption) / var(--lh-caption) var(--font-ui);
    color: var(--text-3);
  }
  .comm-text { color: var(--st-info); }
  .tile-foot {
    margin-top: var(--sp-1);
    border-top: 1px solid var(--border-1);
    padding-top: var(--sp-1);
  }
  .explain {
    margin: 0;
    font: var(--fs-caption) / var(--lh-caption) var(--font-ui);
    color: var(--text-2);
  }
  @media (max-width: 767px) {
    .tile { padding: var(--sp-4); }
    .tile-value {
      font-size: var(--fs-num-lg);
      line-height: var(--lh-num-lg);
      min-height: var(--lh-num-lg);
    }
  }
</style>
