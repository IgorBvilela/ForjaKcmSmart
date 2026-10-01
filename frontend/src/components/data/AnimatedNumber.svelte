<script lang="ts">
  /** Número que desliza até o novo valor em --dur-num. Com `animate=false` (STALE, COMM_ERROR,
   *  prefers-reduced-motion) o valor troca na hora. Nulo vira travessão. */
  import { untrack } from 'svelte'
  import { fmtNumber } from '../../lib/format'

  let {
    value,
    decimals = 1,
    animate = true,
    testid,
  }: { value: number | null | undefined; decimals?: number; animate?: boolean; testid?: string } =
    $props()

  let shown = $state<number | null>(null)
  let raf = 0

  function durationMs(): number {
    const raw = getComputedStyle(document.documentElement).getPropertyValue('--dur-num').trim()
    const n = parseFloat(raw)
    if (!Number.isFinite(n)) return 350
    return raw.endsWith('ms') ? n : n * 1000
  }

  $effect(() => {
    const target = value
    const shouldAnimate = animate
    cancelAnimationFrame(raf)
    if (target == null || !Number.isFinite(target)) {
      shown = null
      return
    }
    const from = untrack(() => shown)
    const dur = shouldAnimate ? durationMs() : 0
    const epsilon = Math.pow(10, -decimals) / 2
    if (from == null || dur <= 0 || Math.abs(target - from) < epsilon) {
      shown = target
      return
    }
    const t0 = performance.now()
    const step = (t: number) => {
      const k = Math.min(1, (t - t0) / dur)
      const eased = 1 - Math.pow(1 - k, 3)
      shown = from + (target - from) * eased
      if (k < 1) raf = requestAnimationFrame(step)
      else shown = target
    }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  })
</script>

<span class="num value" data-testid={testid} data-value={value ?? ''}>{fmtNumber(shown, decimals)}</span>

<style>
  .value { font-weight: 500; }
</style>
