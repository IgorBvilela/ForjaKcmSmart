<script lang="ts">
  // Dosador de correia (WBF) em corte lateral: desenho técnico 2D animado (bloco D).
  // Props e data-*: docs/contracts/CONTRATOS_B.md, seção "Bloco D". Nada aqui comanda nada.
  // Geometria e tempos: ./wbf-scene.ts · animações (WAAPI): ./wbf-motion.ts
  import { onMount, untrack } from 'svelte'
  import {
    BELT,
    BELT_HALF,
    BELT_INNER_PATH,
    BELT_OUTER_PATH,
    BELT_PATH,
    CHUTE,
    ENCODER,
    MOTOR,
    OUTLET,
    PARTICLE_MAX,
    SFT,
    SILO,
    VIEW_H,
    VIEW_W,
    buildParticles,
    clamp,
    encoderNoSignal,
    materialLevel,
    speedRatio,
    visibleParticleCount,
    visualState,
  } from './wbf-scene'
  import { WbfMotion } from './wbf-motion'

  export type MachineState = 0 | 1 | 2 | null
  export type Quality = 'GOOD' | 'SIMULATED' | 'UNCERTAIN' | 'STALE' | 'COMM_ERROR' | 'BAD'

  let {
    rpm = null,
    beltLoad = null,
    driveCommand = null,
    massFlow = null,
    machineState = null,
    quality = 'SIMULATED',
    connection = 'CONNECTED',
    rpmRef = null,
    beltLoadRef = null,
    scenario = undefined,
    reducedMotion = false,
    frameless = false,
  }: {
    rpm?: number | null
    beltLoad?: number | null
    driveCommand?: number | null
    massFlow?: number | null
    machineState?: MachineState
    quality?: Quality
    connection?: string
    rpmRef?: number | null
    beltLoadRef?: number | null
    scenario?: string
    reducedMotion?: boolean
    /** true: sem moldura própria (borda, fundo, padding) para encaixar dentro de um Card. */
    frameless?: boolean
  } = $props()

  // ---- referências observadas (só usadas quando a prop *Ref vem nula) ------------------------
  let maxRpm = $state(0)
  let maxBeltLoad = $state(0)
  $effect(() => {
    const r = rpm
    const b = beltLoad
    untrack(() => {
      if (r != null && r > maxRpm) maxRpm = r
      if (b != null && b > maxBeltLoad) maxBeltLoad = b
    })
  })
  const usesObservedRef = $derived(
    (rpmRef == null || rpmRef <= 0) || (beltLoadRef == null || beltLoadRef <= 0),
  )

  // ---- estado derivado ----------------------------------------------------------------------
  const vstate = $derived(visualState(machineState, quality, connection))
  const level = $derived(materialLevel(beltLoad, beltLoadRef, maxBeltLoad))
  const noSignal = $derived(encoderNoSignal(rpm, driveCommand))
  /** A Forja não mede movimento: sem velocidade indicada, só dá para inferir pelo comando. */
  const inferred = $derived(vstate === 'run' && (noSignal || rpm == null))
  const measuredRate = $derived(speedRatio(rpm, rpmRef, maxRpm))

  let lastGoodRate = $state<number | null>(null)
  $effect(() => {
    const ok = vstate === 'run' && !inferred && measuredRate > 0
    const r = measuredRate
    untrack(() => {
      if (ok) lastGoodRate = r
    })
  })
  const rate = $derived(vstate !== 'run' ? 0 : inferred ? (lastGoodRate ?? 1) : measuredRate)
  /** Vale também em parada: o material fica na correia quando ela para. */
  const visibleCount = $derived(visibleParticleCount(level))
  const hasMaterial = $derived(beltLoad != null && beltLoad > 0)
  const drive = $derived(clamp(driveCommand ?? 0, 0, 100))
  const driveHigh = $derived(drive > 85)

  // ---- movimento reduzido: prop OU preferência do sistema -----------------------------------
  let prefersReduced = $state(false)
  const reduced = $derived(reducedMotion || prefersReduced)

  // ---- animações ----------------------------------------------------------------------------
  const specs = buildParticles(PARTICLE_MAX)
  let beltMarksEl = $state<SVGPathElement | null>(null)
  let pulseEl = $state<SVGCircleElement | null>(null)
  let rollerEls = $state<SVGGElement[]>([])
  let particleEls = $state<SVGCircleElement[]>([])
  let motion = $state.raw<WbfMotion | null>(null)

  onMount(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    prefersReduced = mq.matches
    const onMq = (e: MediaQueryListEvent) => (prefersReduced = e.matches)
    mq.addEventListener('change', onMq)

    const onVis = () => motion?.setHidden(document.hidden)
    document.addEventListener('visibilitychange', onVis)

    let m: WbfMotion | null = null
    if (beltMarksEl && pulseEl && rollerEls.length === 2 && particleEls.length === PARTICLE_MAX) {
      m = new WbfMotion({
        beltMarks: beltMarksEl,
        rollers: rollerEls,
        encoderPulse: pulseEl,
        particles: particleEls,
        specs,
      })
      m.setHidden(document.hidden)
      motion = m
    }
    return () => {
      mq.removeEventListener('change', onMq)
      document.removeEventListener('visibilitychange', onVis)
      m?.destroy()
      motion = null
    }
  })

  // Parada e sem comunicação congelam no lugar (sem custo de quadro); só "run" anima.
  $effect(() => {
    motion?.setMode(reduced ? 'static' : vstate === 'run' ? 'running' : 'frozen')
  })
  $effect(() => {
    motion?.setRate(rate)
  })
  $effect(() => {
    motion?.setVisibleCount(visibleCount)
  })
  /** Em parada: quem estava no ar (calha ou saída) some; quem está sobre a correia fica. */
  let stopMask = $state<boolean[]>([])
  $effect(() => {
    stopMask = vstate === 'stop' && motion ? motion.onBeltMask() : []
  })
  const isShown = (i: number) =>
    i < visibleCount && (vstate !== 'stop' || stopMask[i] !== false)

  // ---- textos -------------------------------------------------------------------------------
  const nf0 = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 })
  const rpmText = $derived(rpm == null ? '—' : nf0.format(rpm))
  const driveText = $derived(driveCommand == null ? '—' : nf0.format(drive))
  const levelPct = $derived(nf0.format(level * 100))
  const refNote = $derived(usesObservedRef ? ' · referência: máximo observado' : '')

  const caption = $derived.by(() => {
    if (vstate === 'unknown') {
      return 'SEM COMUNICAÇÃO · últimos dados antigos · estado da máquina: DESCONHECIDO'
    }
    if (vstate === 'stop') {
      return hasMaterial
        ? 'Parada · correia sem movimento · material parado na correia'
        : 'Parada · correia vazia'
    }
    if (inferred) {
      return (
        `Velocidade indicada ${rpmText} rpm com comando de ${driveText} % · ` +
        'movimento inferido do comando (a Forja não mede movimento)' + refNote
      )
    }
    if (reduced) return `Correia em movimento · ${rpmText} rpm${refNote}`
    return `Em operação · ${rpmText} rpm · material na correia em ${levelPct} % da referência${refNote}`
  })

  const ariaLabel = $derived(
    `Desenho do dosador de correia. ${caption}` +
      (massFlow != null && vstate === 'run' ? ` Vazão ${nf0.format(massFlow)} quilos por hora.` : ''),
  )

  // ---- rótulos em HTML, ancorados em x do viewBox -------------------------------------------
  const pct = (x: number) => `${((x / VIEW_W) * 100).toFixed(3)}%`
  const pctY = (y: number) => `${((y / VIEW_H) * 100).toFixed(3)}%`
  const align = (x: number) => (x < VIEW_W * 0.12 ? 'start' : x > VIEW_W * 0.88 ? 'end' : 'mid')

  /** Rótulos numerados: em container estreito viram marcadores ①…⑦ + legenda embaixo. */
  interface Callout { n: number; x: number; band: 'top' | 'bottom'; text: string; short?: string; warn?: boolean }
  // Só nomes de peça: valor vivo em rótulo muda de largura e faz a página pular (Mística F7).
  // rpm e esforço estão na legenda de estado (figcaption) e nos tiles da página.
  const callouts = $derived<Callout[]>([
    { n: 1, x: 200, band: 'top', text: 'Silo' },
    { n: 2, x: 300, band: 'top', text: 'Entrada' },
    { n: 3, x: 460, band: 'top', text: 'Correia' },
    { n: 4, x: ENCODER.cx, band: 'bottom', text: 'Encoder', warn: noSignal },
    { n: 5, x: SFT.cx, band: 'bottom', text: 'Célula de pesagem · SFT', short: 'Célula · SFT' },
    { n: 6, x: MOTOR.arcCx, band: 'bottom', text: 'Motor', warn: driveHigh },
    { n: 7, x: 583, band: 'bottom', text: 'Saída' },
  ])
</script>

<figure
  class="wbf"
  class:frameless
  data-testid="wbf-root"
  data-state={vstate}
  data-speed={rpm ?? ''}
  data-material-level={level.toFixed(2)}
  data-encoder={noSignal ? 'no-signal' : 'ok'}
  data-scenario={scenario ?? ''}
  data-rate={rate.toFixed(2)}
  data-particles={visibleCount}
  data-reduced={reduced ? 'true' : 'false'}
  aria-label={ariaLabel}
>
  <div class="scene" class:unknown={vstate === 'unknown'}>
   <div class="drawing">
    <div class="band" aria-hidden="true">
      {#each callouts.filter((c) => c.band === 'top') as c (c.n)}
        <span class="lbl {align(c.x)}" class:warn={c.warn} style:left={pct(c.x)}>
          <span class="idx">{c.n}</span><span class="txt">{c.text}</span>
        </span>
      {/each}
    </div>

    <div class="stage">
      <!-- Camada estática: só repinta quando o arco do motor muda. -->
      <svg class="layer" viewBox="0 0 {VIEW_W} {VIEW_H}" aria-hidden="true" focusable="false">
        <!-- linhas-guia dos rótulos -->
        <g class="guide">
          <line x1="200" y1={SILO.top} x2="200" y2="0" />
          <polyline points="{CHUTE.xOutRight},148 300,148 300,0" />
          <line x1="460" y1={BELT.yTop - BELT_HALF - 1} x2="460" y2="0" />
          <line x1={ENCODER.cx} y1={BELT.yBottom + 4} x2={ENCODER.cx} y2={VIEW_H} />
          <line x1={SFT.cx} y1="229" x2={SFT.cx} y2={VIEW_H} />
          <line x1={MOTOR.arcCx} y1={MOTOR.y + MOTOR.h} x2={MOTOR.arcCx} y2={VIEW_H} />
          <line x1="583" y1={OUTLET.yBottom} x2="583" y2={VIEW_H} />
        </g>

        <!-- base / estrutura -->
        <g class="frame">
          <line x1="60" y1="292" x2="620" y2="292" />
          <line x1="160" y1={BELT.yBottom + 3} x2="160" y2="292" />
          <line x1="400" y1={BELT.yBottom + 3} x2="400" y2="292" />
        </g>

        <!-- silo -->
        <g data-part="silo">
          <polygon
            class="shell"
            points="{SILO.xTopLeft},{SILO.top} {SILO.xTopRight},{SILO.top} {SILO.xBottomRight},{SILO.bottom} {SILO.xBottomLeft},{SILO.bottom}"
          />
          <polygon
            class="material"
            points="164,{SILO.levelTop} 276,{SILO.levelTop} {SILO.xBottomRight - 2},{SILO.bottom - 3} {SILO.xBottomLeft + 2},{SILO.bottom - 3}"
          />
          <line class="hl" x1={SILO.xTopLeft + 2} y1={SILO.top + 2} x2={SILO.xTopRight - 2} y2={SILO.top + 2} />
        </g>

        <!-- entrada (calha) -->
        <g data-part="entrada">
          <polygon
            class="shell"
            points="{CHUTE.xLeft},{CHUTE.top} {CHUTE.xRight},{CHUTE.top} {CHUTE.xOutRight},{CHUTE.bottom} {CHUTE.xOutLeft},{CHUTE.bottom}"
          />
          <line class="hl" x1={CHUTE.xLeft + 2} y1={CHUTE.top + 2} x2={CHUTE.xRight - 2} y2={CHUTE.top + 2} />
        </g>

        <!-- correia: as duas bordas da banda (as marcas em movimento ficam na outra camada) -->
        <g class="belt-body" class:inferred data-part="correia">
          <path d={BELT_OUTER_PATH} />
          <path d={BELT_INNER_PATH} />
        </g>

        <!-- célula de pesagem (SFT): ponte de pesagem sob o trecho superior -->
        <g data-part="celula-sft" class="sft">
          <rect class="shell" x={SFT.x} y={SFT.y} width={SFT.w} height="4" />
          <rect class="shell" x={SFT.cx - 18} y={SFT.y + 4} width="10" height="12" />
          <rect class="shell" x={SFT.cx + 8} y={SFT.y + 4} width="10" height="12" />
          <line x1={SFT.cx} y1={SFT.y + 16} x2={SFT.cx} y2={SFT.y + 21} />
          <polygon class="arrow" points="{SFT.cx - 4},{SFT.y + 20} {SFT.cx + 4},{SFT.y + 20} {SFT.cx},{SFT.y + 25}" />
        </g>

        <!-- encoder: cabeça do sensor (o disco dentado gira com o rolete, na outra camada) -->
        <g data-part="encoder" class="encoder" class:nosignal={noSignal}>
          <rect class="shell" x={ENCODER.headX} y={ENCODER.headY} width={ENCODER.headW} height={ENCODER.headH} />
          <line x1={ENCODER.cx} y1={ENCODER.headY + ENCODER.headH} x2={ENCODER.cx} y2={BELT.yTop - 2} />
        </g>

        <!-- motor + redutor + arco de esforço -->
        <g data-part="motor" class="motor" class:high={driveHigh}>
          <rect class="shell body" x={MOTOR.x} y={MOTOR.y} width={MOTOR.w} height={MOTOR.h} rx="2" />
          <line class="hl" x1={MOTOR.x + 2} y1={MOTOR.y + 2} x2={MOTOR.x + MOTOR.w - 2} y2={MOTOR.y + 2} />
          <g class="fins">
            <line x1="488" y1="254" x2="488" y2="282" />
            <line x1="492" y1="254" x2="492" y2="282" />
            <line x1="496" y1="254" x2="496" y2="282" />
          </g>
          <rect class="shell" x={MOTOR.gearX} y={MOTOR.gearY} width={MOTOR.gearW} height={MOTOR.gearH} />
          <line class="link" x1={MOTOR.gearX + MOTOR.gearW} y1={MOTOR.gearY + 6} x2={BELT.x2 - 8} y2={BELT.yBottom - 2} />
          <circle class="arc-track" cx={MOTOR.arcCx} cy={MOTOR.arcCy} r={MOTOR.arcR} />
          <circle
            class="arc"
            cx={MOTOR.arcCx}
            cy={MOTOR.arcCy}
            r={MOTOR.arcR}
            pathLength="100"
            style:stroke-dasharray="{drive.toFixed(1)} 100"
            transform="rotate(-90 {MOTOR.arcCx} {MOTOR.arcCy})"
          />
        </g>

        <!-- saída -->
        <g data-part="saida" class="outlet">
          <line x1={OUTLET.xMouthLeft} y1={OUTLET.yMouth} x2={OUTLET.xBottomLeft} y2={OUTLET.yBottom} />
          <line x1={OUTLET.xMouthRight} y1={OUTLET.yMouth} x2={OUTLET.xBottomRight} y2={OUTLET.yBottom} />
          <line class="hl" x1={OUTLET.xMouthRight - 1} y1={OUTLET.yMouth + 1} x2={OUTLET.xMouthRight + 10} y2={OUTLET.yMouth + 1} />
        </g>
      </svg>

      <!-- Camada de movimento: marcas da correia, roletes, encoder, pulso e partículas. -->
      <svg class="layer motion" viewBox="0 0 {VIEW_W} {VIEW_H}" aria-hidden="true" focusable="false">
        <path
          class="belt-marks"
          class:inferred
          bind:this={beltMarksEl}
          d={BELT_PATH}
          pathLength={BELT.pathLength}
        />

        <g class="roller" data-part="rolete" bind:this={rollerEls[0]}>
          <circle class="metal" cx={BELT.x1} cy={ENCODER.cy} r={BELT.r} />
          <circle class="enc-disc" class:nosignal={noSignal} cx={ENCODER.cx} cy={ENCODER.cy} r={ENCODER.r} />
          <circle class="hub" cx={BELT.x1} cy={ENCODER.cy} r="3.5" />
        </g>
        <g class="roller" data-part="rolete" bind:this={rollerEls[1]}>
          <circle class="metal" cx={BELT.x2} cy={ENCODER.cy} r={BELT.r} />
          <line class="spoke" x1={BELT.x2} y1={ENCODER.cy - 12} x2={BELT.x2} y2={ENCODER.cy + 12} />
          <line class="spoke" x1={BELT.x2 - 10.4} y1={ENCODER.cy - 6} x2={BELT.x2 + 10.4} y2={ENCODER.cy + 6} />
          <line class="spoke" x1={BELT.x2 - 10.4} y1={ENCODER.cy + 6} x2={BELT.x2 + 10.4} y2={ENCODER.cy - 6} />
          <circle class="hub" cx={BELT.x2} cy={ENCODER.cy} r="3.5" />
        </g>

        <circle class="enc-pulse" bind:this={pulseEl} cx={ENCODER.cx} cy={ENCODER.pulseY} r="3" />

        <g class="particles" data-part="particulas">
          {#each specs as p, i (i)}
            <circle
              class="particle"
              bind:this={particleEls[i]}
              r={p.r}
              style:opacity={isShown(i) ? p.opacity : 0}
            />
          {/each}
        </g>
      </svg>

      {#if noSignal}
        <span class="chip" style:left={pct(ENCODER.cx)} style:top={pctY(ENCODER.pulseY - 10)}>Sem sinal</span>
      {/if}
    </div>

    <div class="band" aria-hidden="true">
      {#each callouts.filter((c) => c.band === 'bottom') as c (c.n)}
        <span class="lbl {align(c.x)}" class:warn={c.warn} style:left={pct(c.x)}>
          <span class="idx">{c.n}</span>
          <span class="txt">
            {#if c.short}<span class="long">{c.text}</span><span class="short">{c.short}</span>{:else}{c.text}{/if}
          </span>
        </span>
      {/each}
    </div>

   </div>

    <!-- Legenda numerada: só em container estreito. Só nomes: altura fixa, a página não pula. -->
    <ol class="legend">
      {#each callouts as c (c.n)}
        <li class:warn={c.warn}><span class="idx">{c.n}</span>{c.short ?? c.text}</li>
      {/each}
    </ol>
  </div>

  <figcaption
    class="caption"
    class:is-unknown={vstate === 'unknown'}
    class:is-warn={vstate === 'run' && inferred}
    role={vstate === 'unknown' ? 'status' : undefined}
  >
    {caption}
  </figcaption>
</figure>

<style>
  .wbf {
    margin: 0;
    container-type: inline-size;
    color: var(--text-2);
    background: var(--surf-1);
    border: 1px solid var(--border-1);
    border-radius: var(--r-3);
    padding: var(--sp-3) var(--sp-3) 0;
    display: grid;
    gap: var(--sp-2);
  }
  /* Dentro de um Card do dashboard: o Card já é a moldura. */
  .wbf.frameless {
    border: 0;
    background: transparent;
    padding: 0;
    border-radius: 0;
  }
  .wbf.frameless .caption {
    margin: 0;
    border-top: 0;
    border-radius: var(--r-2);
  }
  .scene {
    display: grid;
    gap: 0;
    transition: filter var(--dur-scenario) var(--ease-std), opacity var(--dur-scenario) var(--ease-std);
  }
  .scene.unknown {
    filter: saturate(0.2);
    opacity: 0.8;
  }
  /* Desenho (faixas + palco): largura limitada para o palco nunca passar de 40vh.
     Limitar pela LARGURA mantém os rótulos em HTML alinhados às linhas-guia do SVG. */
  .drawing {
    --bands-h: calc(2 * (var(--lh-label) + var(--sp-1)));
    width: min(100%, calc((40vh - var(--bands-h)) * 640 / 300));
    margin-inline: auto;
    display: grid;
  }
  .stage {
    position: relative;
    aspect-ratio: 640 / 300;
    width: 100%;
    max-height: 40vh;
  }
  .layer {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    display: block;
    overflow: visible;
  }
  .layer.motion {
    will-change: transform;
  }

  /* ---- traços técnicos: três níveis (Shuri) ----
     1. estrutura e guias: --border-2, 1 px
     2. carcaças (silo, calha, SFT, motor, saída): --text-3, 1,25 px, fill --surf-2
     3. o que se move (correia, marcas, roletes, material): --text-1/--text-2, 1,5 a 2 px */
  .guide line,
  .guide polyline {
    fill: none;
    stroke: var(--border-2);
    stroke-width: 1;
    vector-effect: non-scaling-stroke;
    stroke-dasharray: 3 3;
  }
  .frame line,
  .hl {
    stroke: var(--border-2);
    stroke-width: 1;
    vector-effect: non-scaling-stroke;
  }
  .shell {
    fill: var(--surf-2);
    stroke: var(--text-3);
    stroke-width: 1.25;
    vector-effect: non-scaling-stroke;
    stroke-linejoin: round;
  }
  .sft line,
  .encoder line,
  .outlet line,
  .motor .fins line,
  .motor .link {
    fill: none;
    stroke: var(--text-3);
    stroke-width: 1.25;
    vector-effect: non-scaling-stroke;
  }
  .motor .link {
    stroke-dasharray: 2 2;
  }
  .sft .arrow {
    fill: var(--text-3);
  }
  .material {
    fill: var(--text-3);
    opacity: 0.35;
  }
  .metal {
    fill: var(--surf-3);
    stroke: var(--text-2);
    stroke-width: 1.5;
    vector-effect: non-scaling-stroke;
    stroke-linejoin: round;
  }
  .motor.high .body {
    stroke: var(--st-warn);
    stroke-width: 2;
  }
  .arc-track {
    fill: none;
    stroke: var(--border-2);
    stroke-width: 3;
  }
  .arc {
    fill: none;
    stroke: var(--s2);
    stroke-width: 3;
    stroke-linecap: butt;
    transition: stroke-dasharray var(--dur-num) var(--ease-std);
  }
  .motor.high .arc {
    stroke: var(--st-warn);
  }

  /* ---- correia: duas bordas da banda + marcas transversais entre elas ---- */
  .belt-body path {
    fill: none;
    stroke: var(--text-2);
    stroke-width: 1.5;
    vector-effect: non-scaling-stroke;
    transition: stroke var(--dur-scenario) var(--ease-std);
  }
  .belt-body.inferred path {
    stroke: var(--st-warn);
    stroke-dasharray: 10 6;
  }
  .belt-marks {
    fill: none;
    stroke: var(--text-2);
    stroke-width: 6;
    stroke-dasharray: 2 22;
    opacity: 0.85;
  }
  .belt-marks.inferred {
    stroke: var(--text-3);
  }

  /* ---- roletes / encoder ---- */
  .roller {
    transform-box: fill-box;
    transform-origin: center;
  }
  .hub {
    fill: var(--text-2);
  }
  .spoke {
    stroke: var(--text-2);
    stroke-width: 1.5;
    vector-effect: non-scaling-stroke;
  }
  .enc-disc {
    fill: none;
    stroke: var(--text-2);
    stroke-width: 4;
    /* 12 "dentes": circunferência 62,83 / 12 */
    stroke-dasharray: 2.6 2.636;
    transition: stroke var(--dur-scenario) var(--ease-std);
  }
  .enc-disc.nosignal {
    stroke: var(--st-warn);
    stroke-dasharray: 1 4.236;
  }
  .encoder.nosignal .shell {
    stroke: var(--st-warn);
    stroke-dasharray: 3 2;
  }
  .enc-pulse {
    fill: var(--st-info);
    opacity: 0;
  }

  /* ---- partículas: nunca coloridas ---- */
  .particle {
    fill: var(--text-1);
    transition: opacity var(--dur-scenario) var(--ease-std);
  }

  /* ---- rótulos em HTML ---- */
  .band {
    position: relative;
    height: calc(var(--lh-label) + var(--sp-1));
  }
  .lbl {
    position: absolute;
    top: 0;
    white-space: nowrap;
    font: 500 var(--fs-label) / var(--lh-label) var(--font-ui);
    letter-spacing: var(--ls-label);
    text-transform: uppercase;
    color: var(--text-3);
    transition: color var(--dur-base) var(--ease-std);
  }
  .lbl.mid {
    transform: translateX(-50%);
  }
  .lbl.end {
    transform: translateX(-100%);
  }
  .lbl.warn {
    color: var(--st-warn);
  }
  .lbl .short {
    display: none;
  }
  .idx {
    display: none;
    width: 16px;
    height: 16px;
    place-items: center;
    border-radius: var(--r-pill);
    border: 1px solid currentColor;
    font: 500 var(--fs-label) / 1 var(--font-mono);
    letter-spacing: 0;
  }
  .legend {
    display: none;
    grid-template-columns: 1fr 1fr;
    gap: var(--sp-1) var(--sp-3);
    margin: 0;
    padding: var(--sp-2) 0 0;
    list-style: none;
    font: 500 var(--fs-label) / var(--lh-label) var(--font-ui);
    letter-spacing: var(--ls-label);
    text-transform: uppercase;
    color: var(--text-3);
  }
  .legend li {
    display: inline-flex;
    align-items: center;
    gap: var(--sp-1);
    white-space: nowrap;
  }
  .legend li.warn {
    color: var(--st-warn);
  }
  .legend .idx {
    display: inline-grid;
  }
  /* 440–600 px de container: nome curto da célula para não encostar no motor */
  @container (max-width: 600px) {
    .lbl .long {
      display: none;
    }
    .lbl .short {
      display: inline;
    }
  }
  /* < 440 px (celular): marcadores numerados nas âncoras + legenda em 2 colunas (altura fixa).
     Em 454 px os rótulos curtos inline cabem (menor vão 10 px, medido no Edge).
     O desenho encolhe para figura + legenda caberem em 40vh (4 linhas × --lh-label + vãos). */
  @container (max-width: 439px) {
    .drawing {
      --legend-h: calc(4 * var(--lh-label) + 3 * var(--sp-1) + var(--sp-2));
      width: min(100%, calc((40vh - var(--bands-h) - var(--legend-h)) * 640 / 300));
    }
    .lbl .txt {
      display: none;
    }
    .lbl .idx {
      display: inline-grid;
    }
    .lbl.start,
    .lbl.end,
    .lbl.mid {
      transform: translateX(-50%);
    }
    .legend {
      display: grid;
    }
  }

  .chip {
    position: absolute;
    transform: translate(-50%, -100%);
    font: 500 var(--fs-label) / var(--lh-label) var(--font-ui);
    letter-spacing: var(--ls-label);
    text-transform: uppercase;
    color: var(--st-warn);
    background: var(--st-warn-bg);
    border: 1px dashed var(--st-warn);
    border-radius: var(--r-1);
    padding: 0 var(--sp-2);
    white-space: nowrap;
  }

  /* ---- legenda de estado ---- */
  .caption {
    margin: 0 calc(-1 * var(--sp-3));
    padding: var(--sp-2) var(--sp-3);
    border-top: 1px solid var(--border-1);
    border-radius: 0 0 var(--r-3) var(--r-3);
    font: 400 var(--fs-caption) / var(--lh-caption) var(--font-ui);
    color: var(--text-2);
    font-variant-numeric: tabular-nums;
    transition: background var(--dur-scenario) var(--ease-std), color var(--dur-scenario) var(--ease-std);
  }
  .caption.is-warn {
    color: var(--st-warn);
    background: var(--st-warn-bg);
  }
  .caption.is-unknown {
    color: var(--st-info);
    background: var(--st-info-bg);
    font-weight: 500;
    letter-spacing: 0.02em;
  }

  @media print {
    .scene {
      filter: none;
    }
  }
</style>
