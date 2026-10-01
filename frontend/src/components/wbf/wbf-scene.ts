/**
 * Geometria e tempos do dosador de correia (WBF) desenhado em WbfMachine.svelte.
 *
 * Tudo em unidades do viewBox (640 × 300). Nada aqui é dado da GTEX: é desenho explicativo
 * (Documento Mestre §24: "representação explicativa, não gêmeo digital").
 * Funções puras, sem DOM, para dar para testar sem navegador.
 */

export const VIEW_W = 640
export const VIEW_H = 300

/** Correia: dois roletes ligados por um laço em "estádio". Topo anda da esquerda para a direita. */
export const BELT = {
  x1: 96,
  x2: 544,
  yTop: 200,
  yBottom: 232,
  r: 16,
  /** Perímetro real ≈ 996,5. Normalizado em 1008 = 42 × 24 para o laço das marcas fechar sem salto. */
  pathLength: 1008,
  /** Distância entre marcas transversais, em unidades de pathLength (≈ 24 px no viewBox). */
  markPeriod: 24,
} as const

/** Laço em "estádio" (dois trechos retos + duas meias-voltas) centrado no eixo dos roletes. */
export function stadiumPath(x1: number, x2: number, cy: number, r: number): string {
  return (
    `M ${x1} ${cy - r} H ${x2} A ${r} ${r} 0 0 1 ${x2} ${cy + r} H ${x1} ` +
    `A ${r} ${r} 0 0 1 ${x1} ${cy - r} Z`
  )
}

const BELT_CY = (BELT.yTop + BELT.yBottom) / 2
/** Linha média da correia: por aqui correm as marcas (stroke largo = espessura da banda). */
export const BELT_PATH = stadiumPath(BELT.x1, BELT.x2, BELT_CY, BELT.r)
/** Metade da espessura da banda da correia (unidades do viewBox). */
export const BELT_HALF = 3
/** Bordas externa e interna da banda: o que se vê como "correia" no desenho técnico. */
export const BELT_OUTER_PATH = stadiumPath(BELT.x1, BELT.x2, BELT_CY, BELT.r + BELT_HALF)
export const BELT_INNER_PATH = stadiumPath(BELT.x1, BELT.x2, BELT_CY, BELT.r - BELT_HALF)

/** Velocidade visual da correia quando rpm == rpmRef (px do viewBox por segundo). Só estética. */
export const REF_PX_PER_S = 60
/** Um período das marcas (24 px) na referência. */
export const MARK_PERIOD_MS = (BELT.markPeriod / REF_PX_PER_S) * 1000 // 400 ms
/** Uma volta do rolete na referência: circunferência / velocidade linear. */
export const ROLLER_REV_MS = MARK_PERIOD_MS * ((2 * Math.PI * BELT.r) / BELT.markPeriod) // ≈ 1676 ms

export const SILO = {
  top: 22,
  bottom: 112,
  xTopLeft: 150,
  xTopRight: 290,
  xBottomLeft: 202,
  xBottomRight: 238,
  /** Nível interno fixo (não é medido pelo KCM). */
  levelTop: 52,
} as const

export const CHUTE = {
  top: SILO.bottom,
  bottom: 162,
  xLeft: 200,
  xRight: 240,
  xOutLeft: 226,
  xOutRight: 250,
} as const

export const OUTLET = {
  xMouthLeft: 562,
  xMouthRight: 604,
  yMouth: 236,
  xBottomLeft: 574,
  xBottomRight: 592,
  yBottom: 292,
} as const

export const MOTOR = {
  x: 440,
  y: 248,
  w: 60,
  h: 40,
  gearX: 500,
  gearY: 256,
  gearW: 16,
  gearH: 24,
  arcCx: 470,
  arcCy: 268,
  arcR: 13,
} as const

/** Célula de pesagem (SFT) como abstração: ponte de pesagem sob o trecho superior da correia. */
export const SFT = { x: 320, y: 204, w: 60, cx: 350 } as const

export const ENCODER = {
  cx: BELT.x1,
  cy: (BELT.yTop + BELT.yBottom) / 2,
  r: 10,
  headX: 90,
  headY: 183,
  headW: 12,
  headH: 8,
  pulseY: 176,
} as const

/** Pool fixo de partículas: criadas uma vez, nunca mais que isto. */
export const PARTICLE_MAX = 60

export interface ParticleSpec {
  /** x de emissão na boca da calha. */
  x0: number
  /** altura sobre a correia (0 = encostada; até 6). */
  lane: number
  /** fase inicial 0..1 na linha do tempo (bem distribuída para qualquer prefixo visível). */
  phase: number
  /** opacidade base 0,7..1. */
  opacity: number
  /** deriva horizontal na queda de saída. */
  driftX: number
  /** raio 1,6..2,4 no viewBox (Shuri: 1..1,5 sumia em 470 px de largura). */
  r: number
}

/** PRNG determinístico (mulberry32). Mesmo desenho a cada carga; sem Math.random. */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const GOLDEN = 0.6180339887498949

export function buildParticles(n: number = PARTICLE_MAX, seed = 7): ParticleSpec[] {
  const rnd = mulberry32(seed)
  const out: ParticleSpec[] = []
  for (let i = 0; i < n; i++) {
    out.push({
      x0: CHUTE.xOutLeft + 2 + rnd() * (CHUTE.xOutRight - CHUTE.xOutLeft - 4),
      lane: rnd() * 6,
      // Sequência áurea: os primeiros K índices ficam espalhados pela correia inteira,
      // então "esconder os últimos" não abre buraco num trecho só.
      phase: ((i + 1) * GOLDEN) % 1,
      opacity: 0.7 + rnd() * 0.3,
      driftX: rnd() * 14,
      r: 1.6 + rnd() * 0.8,
    })
  }
  return out
}

export interface ParticleTimeline {
  keyframes: Keyframe[]
  /** duração total na referência (ms). */
  durationMs: number
  /** fração 0..1 em que a partícula pousa na correia (fim da queda da calha). */
  rideStart: number
  /** fração 0..1 em que a partícula deixa a correia (início da queda na saída). */
  rideEnd: number
}

/**
 * Linha do tempo de uma partícula: cai da calha, anda na correia na mesma velocidade das marcas,
 * cai na saída. Uma só animação por partícula, então `playbackRate` escala tudo junto.
 */
export function particleTimeline(p: ParticleSpec): ParticleTimeline {
  const yEmit = CHUTE.bottom + 2
  // pousa sobre a borda externa da banda (yTop - BELT_HALF), com camadas acima
  const yBelt = BELT.yTop - BELT_HALF - 1 - p.lane
  const xRideEnd = BELT.x2 + 8
  const xDrop = OUTLET.xBottomLeft + 2 + p.driftX
  const yDrop = OUTLET.yBottom - 2

  const fallPx = yBelt - yEmit
  const ridePx = xRideEnd - p.x0
  const dropPx = Math.hypot(xDrop - xRideEnd, yDrop - yBelt)

  const fallMs = (fallPx / (REF_PX_PER_S * 2)) * 1000
  const rideMs = (ridePx / REF_PX_PER_S) * 1000
  const dropMs = (dropPx / (REF_PX_PER_S * 2.6)) * 1000
  const total = fallMs + rideMs + dropMs

  const keyframes: Keyframe[] = [
    { transform: `translate(${p.x0}px, ${yEmit}px)`, easing: 'ease-in', offset: 0 },
    { transform: `translate(${p.x0}px, ${yBelt}px)`, easing: 'linear', offset: fallMs / total },
    {
      transform: `translate(${xRideEnd}px, ${yBelt}px)`,
      easing: 'ease-in',
      offset: (fallMs + rideMs) / total,
    },
    { transform: `translate(${xDrop}px, ${yDrop}px)`, offset: 1 },
  ]
  return {
    keyframes,
    durationMs: total,
    rideStart: fallMs / total,
    rideEnd: (fallMs + rideMs) / total,
  }
}

/** Quantas partículas mostrar para um nível 0..1,2 (1,0 = referência → 50 de 60). */
export function visibleParticleCount(level: number, max: number = PARTICLE_MAX): number {
  const l = Math.max(0, Math.min(1.2, level))
  return Math.round((l / 1.2) * max)
}

export function clamp(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v))
}

/** Nível de material 0..1,2 (duas casas). beltLoadRef nulo → usa o máximo observado. */
export function materialLevel(
  beltLoad: number | null,
  beltLoadRef: number | null,
  observedMax: number,
): number {
  if (beltLoad == null) return 0
  const ref = beltLoadRef != null && beltLoadRef > 0 ? beltLoadRef : observedMax
  if (!(ref > 0)) return beltLoad > 0 ? 1 : 0
  return clamp(beltLoad / ref, 0, 1.2)
}

/** Razão de velocidade 0..2 (playbackRate). rpmRef nulo → usa o máximo observado. */
export function speedRatio(rpm: number | null, rpmRef: number | null, observedMax: number): number {
  if (rpm == null) return 0
  const ref = rpmRef != null && rpmRef > 0 ? rpmRef : observedMax
  if (!(ref > 0)) return rpm > 0 ? 1 : 0
  return clamp(rpm / ref, 0, 2)
}

/** Convenção da Forja (R-SPEED-001): comando acima de 5 % com velocidade zero = sem sinal. */
export function encoderNoSignal(rpm: number | null, driveCommand: number | null): boolean {
  return rpm === 0 && (driveCommand ?? 0) > 5
}

export type MachineVisualState = 'run' | 'stop' | 'unknown'

export function visualState(
  machineState: 0 | 1 | 2 | null,
  quality: string,
  connection: string,
): MachineVisualState {
  if (connection !== 'CONNECTED' || quality === 'COMM_ERROR' || quality === 'STALE') return 'unknown'
  return machineState === 1 ? 'run' : 'stop'
}
