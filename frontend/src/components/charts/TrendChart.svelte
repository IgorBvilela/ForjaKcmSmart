<script lang="ts">
  /** Tendência de uma variável (uPlot).
   *
   *  - Linha em degrau: cada ponto vale até o próximo (é o que o historiador grava, com
   *    store-on-change). Nunca liga dois pontos por reta inventada.
   *  - Buraco (value null) quebra a linha e vira faixa sombreada até a próxima leitura.
   *  - Série resumida: faixa de mínimo e máximo do intervalo atrás da média.
   *  - Faixa de qualidade na base do gráfico, com a cor de cada qualidade.
   *  - Cursor sincronizado entre os gráficos da tela (mesmo instante em todas as variáveis).
   *  - Arrastar na horizontal pede zoom (a página busca o trecho com mais resolução). */
  import uPlot from 'uplot'
  import 'uplot/dist/uPlot.min.css'
  import { onMount } from 'svelte'
  import { QUALITY_PT, type HistoryPoint, type Quality, type TagMeta } from '../../lib/api'
  import { fmtNumber } from '../../lib/format'

  let {
    points,
    refPoints = null,
    refLabel = '',
    meta,
    color = '--s1',
    from,
    to,
    downsampled = false,
    syncKey = 'forja-trends',
    height = 168,
    onzoom,
    testid,
  }: {
    points: HistoryPoint[]
    refPoints?: HistoryPoint[] | null
    refLabel?: string
    meta: TagMeta
    color?: string
    from: number
    to: number
    downsampled?: boolean
    syncKey?: string
    height?: number
    onzoom?: (fromMs: number, toMs: number) => void
    testid?: string
  } = $props()

  let host: HTMLDivElement | undefined = $state()
  let plotEl: HTMLDivElement | undefined = $state()
  let width = $state(0)
  let themeTick = $state(0)
  let hover = $state<{ t: number; v: number | null | undefined; q: Quality | undefined } | null>(null)

  const QUALITY_VAR: Record<Quality, string> = {
    GOOD: '--q-good',
    SIMULATED: '--q-sim',
    UNCERTAIN: '--q-uncertain',
    STALE: '--q-stale',
    COMM_ERROR: '--q-comm',
    BAD: '--q-bad',
  }

  interface Aligned {
    xs: number[]
    main: (number | null | undefined)[]
    ref: (number | null | undefined)[] | null
    lo: (number | null | undefined)[] | null
    hi: (number | null | undefined)[] | null
    q: (Quality | undefined)[]
  }

  /** Une os instantes das duas séries. Instante sem ponto = undefined (a linha segura o valor
   *  anterior, como o historiador); null explícito = buraco. */
  function align(main: HistoryPoint[], ref: HistoryPoint[] | null, band: boolean): Aligned {
    const set = new Set<number>()
    for (const p of main) set.add(Date.parse(p.ts_utc) / 1000)
    if (ref) for (const p of ref) set.add(Date.parse(p.ts_utc) / 1000)
    const xs = [...set].filter(Number.isFinite).sort((a, b) => a - b)
    const index = new Map(xs.map((x, i) => [x, i]))
    const mk = <T,>() => new Array<T | undefined>(xs.length).fill(undefined)
    const out: Aligned = {
      xs,
      main: mk<number | null>(),
      ref: ref ? mk<number | null>() : null,
      lo: band ? mk<number | null>() : null,
      hi: band ? mk<number | null>() : null,
      q: mk<Quality>(),
    }
    for (const p of main) {
      const i = index.get(Date.parse(p.ts_utc) / 1000)
      if (i == null) continue
      out.main[i] = p.value
      out.q[i] = p.quality
      if (out.lo && out.hi) {
        out.lo[i] = p.value == null ? null : (p.min ?? p.value)
        out.hi[i] = p.value == null ? null : (p.max ?? p.value)
      }
    }
    if (ref && out.ref) {
      for (const p of ref) {
        const i = index.get(Date.parse(p.ts_utc) / 1000)
        if (i != null) out.ref[i] = p.value
      }
    }
    return out
  }

  const data = $derived(align(points, refPoints, downsampled))

  const stats = $derived.by(() => {
    const vals = points.map((p) => p.value).filter((v): v is number => v != null && Number.isFinite(v))
    const gaps = points.filter((p) => p.value == null).length
    return {
      n: vals.length,
      min: vals.length ? Math.min(...vals) : null,
      max: vals.length ? Math.max(...vals) : null,
      last: vals.length ? vals[vals.length - 1] : null,
      gaps,
    }
  })

  const lastPoint = $derived.by(() => {
    for (let i = points.length - 1; i >= 0; i -= 1) {
      if (points[i].value != null) return points[i]
    }
    return null
  })

  const ariaLabel = $derived(
    `Gráfico de ${meta.label_pt}: mínimo ${fmtNumber(stats.min, meta.decimals)}, máximo ${fmtNumber(
      stats.max,
      meta.decimals,
    )} ${meta.unit}; ${stats.gaps} trecho(s) sem leitura.`,
  )

  function cssVar(name: string, fallback: string): string {
    if (!host) return fallback
    const v = getComputedStyle(host).getPropertyValue(name).trim()
    return v || fallback
  }

  const timeFmt = {
    sec: new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
    min: new Intl.DateTimeFormat('pt-BR', { hour: '2-digit', minute: '2-digit' }),
    day: new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }),
  }

  function axisTime(sec: number, spanMs: number): string {
    const d = new Date(sec * 1000)
    if (spanMs <= 20 * 60_000) return timeFmt.sec.format(d)
    if (spanMs <= 36 * 3_600_000) return timeFmt.min.format(d)
    return timeFmt.day.format(d)
  }

  /** Último valor definido até o índice (o degrau segura o valor). */
  function heldAt(arr: (number | null | undefined)[], idx: number): { v: number | null | undefined; i: number } {
    for (let i = idx; i >= 0; i -= 1) {
      if (arr[i] !== undefined) return { v: arr[i], i }
    }
    return { v: undefined, i: -1 }
  }

  function build(target: HTMLDivElement, w: number): uPlot {
    const d = data
    const stroke = cssVar(color, '#E8E8E8')
    const ref = cssVar('--s-ref', '#8B9097')
    const grid = cssVar('--chart-grid', '#2C2F33')
    const axis = cssVar('--text-3', '#858B93')
    const gapFill = cssVar('--chart-gap', 'rgba(79,179,217,.12)')
    const bandFill = cssVar('--accent-soft', 'rgba(196,106,46,.14)')
    const mono = cssVar('--font-mono', 'monospace')
    const qColor = Object.fromEntries(
      (Object.keys(QUALITY_VAR) as Quality[]).map((q) => [q, cssVar(QUALITY_VAR[q], '#888')]),
    ) as Record<Quality, string>
    const stepped = uPlot.paths.stepped?.({ align: 1 })
    const spanMs = to - from
    const dec = Math.min(meta.decimals, 2)

    const series: uPlot.Series[] = [
      {},
      { label: meta.label_pt, stroke, width: 1.75, paths: stepped, points: { show: false }, spanGaps: false },
    ]
    const aligned: uPlot.AlignedData = [d.xs, d.main as (number | null)[]]
    if (d.ref) {
      series.push({ label: refLabel, stroke: ref, width: 1.25, dash: [6, 4], paths: stepped, points: { show: false } })
      aligned.push(d.ref as (number | null)[])
    }
    const bands: uPlot.Band[] = []
    if (d.lo && d.hi) {
      const hiIdx = series.length
      series.push({ label: 'máximo', stroke: 'transparent', width: 0, paths: stepped, points: { show: false } })
      aligned.push(d.hi as (number | null)[])
      const loIdx = series.length
      series.push({ label: 'mínimo', stroke: 'transparent', width: 0, paths: stepped, points: { show: false } })
      aligned.push(d.lo as (number | null)[])
      bands.push({ series: [hiIdx, loIdx], fill: bandFill })
    }

    const opts: uPlot.Options = {
      width: w,
      height,
      legend: { show: false },
      padding: [8, 32, 0, 0],
      scales: {
        x: { time: true, range: () => [from / 1000, to / 1000] },
        y: {
          range: (_u, lo, hi) => {
            if (lo == null || hi == null || !Number.isFinite(lo) || !Number.isFinite(hi)) return [0, 1]
            const pad = hi - lo < 1e-9 ? Math.abs(hi) * 0.05 || 1 : (hi - lo) * 0.08
            return [lo - pad, hi + pad]
          },
        },
      },
      series,
      bands,
      cursor: {
        sync: { key: syncKey },
        drag: { x: true, y: false, setScale: false },
        points: { size: 7, fill: stroke },
      },
      axes: [
        {
          stroke: axis,
          font: `13px ${mono}`,
          size: 30,
          gap: 4,
          grid: { stroke: grid, width: 1 },
          ticks: { stroke: grid, width: 1, size: 4 },
          space: 84,
          values: (_u, splits) => splits.map((s) => axisTime(s, spanMs)),
        },
        {
          stroke: axis,
          font: `13px ${mono}`,
          size: 60,
          grid: { stroke: grid, width: 1 },
          ticks: { show: false },
          values: (_u, splits) => {
            // casas que o passo entre as marcas pede: faixa estreita não repete o mesmo número
            const step = splits.length > 1 ? Math.abs(splits[1] - splits[0]) : 0
            const need = step > 0 ? Math.max(0, Math.ceil(-Math.log10(step) - 1e-9)) : 0
            const places = Math.min(Math.max(dec, need), 3)
            return splits.map((s) => fmtNumber(s, places))
          },
        },
      ],
      hooks: {
        drawClear: [
          (u) => {
            const ctx = u.ctx
            const { top, height: h, left, width: bw } = u.bbox
            const xs = u.data[0] as number[]
            ctx.save()
            ctx.fillStyle = gapFill
            for (let i = 0; i < xs.length; i += 1) {
              if (d.main[i] !== null) continue
              let j = i + 1
              while (j < xs.length && d.main[j] === undefined) j += 1
              const x0 = Math.max(left, u.valToPos(xs[i], 'x', true))
              const x1 = j < xs.length ? u.valToPos(xs[j], 'x', true) : left + bw
              if (x1 > x0) ctx.fillRect(x0, top, Math.max(2, x1 - x0), h)
            }
            ctx.restore()
          },
        ],
        draw: [
          (u) => {
            const ctx = u.ctx
            const { top, height: h, left, width: bw } = u.bbox
            const strip = Math.max(3, Math.round(4 * devicePixelRatio))
            const xs = u.data[0] as number[]
            ctx.save()
            let current: Quality | undefined
            for (let i = 0; i < xs.length; i += 1) {
              if (d.q[i] !== undefined) current = d.q[i]
              if (!current) continue
              let j = i + 1
              while (j < xs.length && d.q[j] === undefined) j += 1
              const x0 = Math.max(left, u.valToPos(xs[i], 'x', true))
              const x1 = Math.min(left + bw, j < xs.length ? u.valToPos(xs[j], 'x', true) : left + bw)
              if (x1 <= x0) continue
              ctx.fillStyle = qColor[current]
              ctx.fillRect(x0, top + h - strip, x1 - x0, strip)
            }
            ctx.restore()
          },
        ],
        setSelect: [
          (u) => {
            const sel = u.select
            if (sel.width > 6 && onzoom) {
              const a = u.posToVal(sel.left, 'x') * 1000
              const b = u.posToVal(sel.left + sel.width, 'x') * 1000
              if (b - a >= 10_000) onzoom(a, b)
            }
            u.setSelect({ left: 0, top: 0, width: 0, height: 0 }, false)
          },
        ],
        setCursor: [
          (u) => {
            const idx = u.cursor.idx
            if (idx == null) {
              hover = null
              return
            }
            const held = heldAt(d.main, idx)
            const qi = held.i >= 0 ? d.q[held.i] : undefined
            hover = { t: (u.data[0] as number[])[idx] * 1000, v: held.v, q: qi }
          },
        ],
      },
    }
    return new uPlot(opts, aligned, target)
  }

  let plot: uPlot | null = null

  $effect(() => {
    // reconstrói quando dados, janela, largura ou tema mudam
    void data
    void from
    void to
    void themeTick
    const w = width
    const el = plotEl
    if (!el || w < 40) return
    plot?.destroy()
    plot = build(el, w)
    return () => {
      plot?.destroy()
      plot = null
    }
  })

  onMount(() => {
    const ro = new ResizeObserver((entries) => {
      const w = Math.floor(entries[0]?.contentRect.width ?? 0)
      if (Math.abs(w - width) >= 2) width = w
    })
    if (host) ro.observe(host)
    const mo = new MutationObserver(() => (themeTick += 1))
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => {
      ro.disconnect()
      mo.disconnect()
    }
  })

  const readoutTime = new Intl.DateTimeFormat('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
</script>

<figure class="trend" data-testid={testid} data-tag={meta.code} data-points={points.length} data-gaps={stats.gaps}>
  <figcaption class="head">
    <span class="name">{meta.label_pt}{#if meta.unit}<span class="unit">{meta.unit}</span>{/if}</span>
    <span class="readout num" aria-live="off">
      {#if hover}
        <span class="when">{readoutTime.format(new Date(hover.t))}</span>
        <strong>{hover.v == null ? 'sem leitura' : fmtNumber(hover.v, meta.decimals)}</strong>
        {#if hover.q}<span class="q" data-quality={hover.q}>{QUALITY_PT[hover.q]}</span>{/if}
      {:else if lastPoint}
        <span class="when">último</span>
        <strong>{fmtNumber(lastPoint.value, meta.decimals)}</strong>
        <span class="q" data-quality={lastPoint.quality}>{QUALITY_PT[lastPoint.quality]}</span>
      {:else}
        <span class="when">sem leituras gravadas neste período</span>
      {/if}
    </span>
  </figcaption>
  <div class="plot" bind:this={host} role="img" aria-label={ariaLabel}>
    <div bind:this={plotEl}></div>
    {#if stats.n === 0}
      <p class="empty">Nenhuma leitura com valor neste período. Nada foi preenchido.</p>
    {/if}
  </div>
  <div class="foot num">
    <span>mín. <b>{fmtNumber(stats.min, meta.decimals)}</b></span>
    <span>máx. <b>{fmtNumber(stats.max, meta.decimals)}</b></span>
    {#if refPoints && refLabel}<span class="ref-key"><i aria-hidden="true"></i>{refLabel}</span>{/if}
    {#if downsampled}<span class="band-key"><i aria-hidden="true"></i>faixa mín.–máx. do intervalo</span>{/if}
    {#if stats.gaps > 0}<span class="gap-key"><i aria-hidden="true"></i>{stats.gaps} sem leitura</span>{/if}
  </div>
</figure>

<style>
  .trend {
    margin: 0;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: var(--sp-2);
  }
  .head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--sp-3);
    flex-wrap: wrap;
  }
  .name {
    font: 600 var(--fs-h3) / var(--lh-h3) var(--font-ui);
    color: var(--text-1);
  }
  .unit { margin-left: var(--sp-2); color: var(--text-3); font-weight: 400; }
  .unit::before { content: '·'; margin-right: var(--sp-2); }
  .readout {
    display: inline-flex;
    align-items: baseline;
    gap: var(--sp-2);
    font-size: var(--fs-mono-sm);
    color: var(--text-2);
    min-height: var(--lh-mono);
  }
  .readout strong { color: var(--text-1); font-size: var(--fs-mono); font-weight: 600; }
  .when { color: var(--text-3); }
  .q { color: var(--text-3); }
  .q[data-quality='SIMULATED'] { color: var(--q-sim); }
  .q[data-quality='UNCERTAIN'] { color: var(--q-uncertain); }
  .q[data-quality='COMM_ERROR'] { color: var(--q-comm); }
  .q[data-quality='BAD'] { color: var(--q-bad); }
  .plot {
    position: relative;
    min-width: 0;
    width: 100%;
  }
  .plot :global(.uplot) { font-family: var(--font-mono); }
  .plot :global(.u-select) { background: var(--accent-soft); }
  .empty {
    position: absolute;
    inset: 0;
    display: grid;
    place-items: center;
    margin: 0;
    padding: var(--sp-4);
    text-align: center;
    color: var(--text-3);
    font: var(--fs-caption) / var(--lh-caption) var(--font-ui);
    pointer-events: none;
  }
  .foot {
    display: flex;
    flex-wrap: wrap;
    gap: var(--sp-1) var(--sp-4);
    font-size: var(--fs-mono-sm);
    color: var(--text-3);
  }
  .foot b { color: var(--text-2); font-weight: 500; }
  .foot i {
    display: inline-block;
    width: 14px;
    height: 8px;
    margin-right: 6px;
    vertical-align: middle;
    border-radius: 2px;
  }
  .ref-key i { border-top: 2px dashed var(--s-ref); height: 0; }
  .band-key i { background: var(--accent-soft); }
  .gap-key i { background: var(--chart-gap); }
</style>
