<script lang="ts">
  /** Mini-tendência SVG. Buraco (value null) quebra a linha e ganha marca de GAP; nunca interpola. */
  import type { SeriesPoint } from '../../lib/live.svelte'

  let {
    points = [],
    height = 36,
    color = 'var(--s1)',
    refValue = null,
    faded = false,
    label = 'Mini-tendência dos últimos pontos',
  }: {
    points?: SeriesPoint[]
    height?: number
    color?: string
    refValue?: number | null
    faded?: boolean
    label?: string
  } = $props()

  let width = $state(0)
  const PAD_Y = 3

  const geo = $derived.by(() => {
    const w = Math.max(width, 10)
    const h = height
    const vals = points.map((p) => p.v).filter((v): v is number => v != null && Number.isFinite(v))
    if (vals.length < 2) return null
    let min = Math.min(...vals)
    let max = Math.max(...vals)
    if (refValue != null && Number.isFinite(refValue)) {
      min = Math.min(min, refValue)
      max = Math.max(max, refValue)
    }
    if (max - min < 1e-9) {
      const bump = Math.abs(max) * 0.02 || 1
      max += bump
      min -= bump
    }
    const n = points.length
    const x = (i: number) => (n === 1 ? w / 2 : (i / (n - 1)) * w)
    const y = (v: number) => PAD_Y + (h - PAD_Y * 2) * (1 - (v - min) / (max - min))
    let d = ''
    let pen = false
    const gaps: number[] = []
    let lastX = 0
    let lastY = 0
    points.forEach((p, i) => {
      if (p.v == null || !Number.isFinite(p.v)) {
        pen = false
        gaps.push(x(i))
        return
      }
      lastX = x(i)
      lastY = y(p.v)
      d += `${pen ? 'L' : 'M'}${lastX.toFixed(1)},${lastY.toFixed(1)}`
      pen = true
    })
    return {
      d,
      w,
      h,
      gaps,
      lastX,
      lastY,
      refY: refValue != null && Number.isFinite(refValue) ? y(refValue) : null,
    }
  })
</script>

<div class="spark-wrap" bind:clientWidth={width} style:height={`${height}px`}>
  {#if geo}
    <svg
      class="spark"
      class:faded
      viewBox={`0 0 ${geo.w} ${geo.h}`}
      width={geo.w}
      height={geo.h}
      role="img"
      aria-label={label}
    >
      {#each geo.gaps as gx (gx)}
        <rect x={gx - 1} y="0" width="2" height={geo.h} fill="var(--chart-gap)" />
      {/each}
      {#if geo.refY != null}
        <line
          x1="0"
          x2={geo.w}
          y1={geo.refY}
          y2={geo.refY}
          stroke="var(--s-ref)"
          stroke-width="1"
          stroke-dasharray="3 4"
          vector-effect="non-scaling-stroke"
        />
      {/if}
      <path
        class="line draw"
        d={geo.d}
        fill="none"
        stroke={color}
        stroke-width="1.5"
        stroke-linejoin="round"
        stroke-linecap="round"
        pathLength="1"
        vector-effect="non-scaling-stroke"
      />
      <circle cx={geo.lastX} cy={geo.lastY} r="2" fill={color} />
    </svg>
  {:else}
    <div class="spark-empty" aria-hidden="true"></div>
  {/if}
</div>

<style>
  .spark-wrap {
    width: 100%;
    min-width: 0;
    overflow: hidden;
  }
  .spark {
    display: block;
    width: 100%;
    height: 100%;
    transition: opacity var(--dur-base) var(--ease-std);
  }
  .spark.faded { opacity: 0.35; filter: saturate(0); }
  .line {
    stroke-dasharray: 1;
    stroke-dashoffset: 0;
    animation: draw var(--dur-draw) var(--ease-out) both;
  }
  @keyframes draw {
    from { stroke-dashoffset: 1; }
    to { stroke-dashoffset: 0; }
  }
  .spark-empty {
    width: 100%;
    height: 100%;
    background: repeating-linear-gradient(
      90deg,
      var(--border-1) 0 4px,
      transparent 4px 10px
    );
    background-size: 100% 1px;
    background-position: center;
    background-repeat: no-repeat;
  }
</style>
