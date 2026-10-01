/**
 * Controlador das animações do dosador (Web Animations API).
 *
 * Cria cada animação UMA vez e depois só ajusta `playbackRate`, pausa e retoma. Nada é recriado
 * por amostra: trocar rpm a 1 Hz custa um `updatePlaybackRate`, não um layout.
 *
 * Modos:
 *  - running(rate): tudo anda; rate 0 = correia parada mas "viva".
 *  - frozen: congela na última pose (sem comunicação / dado antigo).
 *  - static: quadro fixo com partículas espalhadas (prefers-reduced-motion).
 */

import {
  MARK_PERIOD_MS,
  ROLLER_REV_MS,
  BELT,
  particleTimeline,
  type ParticleSpec,
  type ParticleTimeline,
} from './wbf-scene'

export interface MotionTargets {
  beltMarks: SVGPathElement
  rollers: SVGGElement[]
  encoderPulse: SVGElement
  particles: SVGElement[]
  specs: ParticleSpec[]
}

export class WbfMotion {
  private anims: Animation[] = []
  private particleAnims: Animation[] = []
  private timelines: ParticleTimeline[] = []
  private rate = 1
  private mode: 'running' | 'frozen' | 'static' = 'running'
  private hidden = false
  private visible = Number.MAX_SAFE_INTEGER

  constructor(targets: MotionTargets) {
    const linear: KeyframeAnimationOptions = {
      duration: MARK_PERIOD_MS,
      iterations: Infinity,
      easing: 'linear',
    }
    this.anims.push(
      targets.beltMarks.animate(
        [{ strokeDashoffset: 0 }, { strokeDashoffset: -BELT.markPeriod }],
        linear,
      ),
    )
    for (const roller of targets.rollers) {
      this.anims.push(
        roller.animate([{ transform: 'rotate(0deg)' }, { transform: 'rotate(360deg)' }], {
          duration: ROLLER_REV_MS,
          iterations: Infinity,
          easing: 'linear',
        }),
      )
    }
    // Um pulso por volta do rolete onde o encoder está montado.
    this.anims.push(
      targets.encoderPulse.animate(
        [
          { opacity: 0, offset: 0 },
          { opacity: 1, offset: 0.04 },
          { opacity: 0, offset: 0.2 },
          { opacity: 0, offset: 1 },
        ],
        { duration: ROLLER_REV_MS, iterations: Infinity, easing: 'linear' },
      ),
    )
    targets.particles.forEach((el, i) => {
      const spec = targets.specs[i]
      if (!spec) return
      const tl = particleTimeline(spec)
      const anim = el.animate(tl.keyframes, {
        duration: tl.durationMs,
        iterations: Infinity,
        easing: 'linear',
      })
      // Fase inicial: espalha o pool pela correia já no primeiro quadro.
      anim.currentTime = spec.phase * tl.durationMs
      this.particleAnims.push(anim)
      this.timelines.push(tl)
    })
  }

  private all(): Animation[] {
    return this.anims.concat(this.particleAnims)
  }

  /**
   * Para cada partícula, se a pose atual está SOBRE a correia (nem caindo da calha, nem caindo
   * na saída). Usado em parada: o que está no ar some, o que está na correia fica no lugar.
   */
  onBeltMask(): boolean[] {
    return this.particleAnims.map((a, i) => {
      const tl = this.timelines[i]
      if (!tl) return true
      const t = Number(a.currentTime ?? 0)
      const phase = (((t / tl.durationMs) % 1) + 1) % 1
      return phase >= tl.rideStart && phase <= tl.rideEnd
    })
  }

  /** Velocidade relativa 0..2. Sem salto: usa updatePlaybackRate quando o navegador tem. */
  setRate(rate: number): void {
    this.rate = rate
    if (this.mode !== 'running' || this.hidden) return
    for (const a of this.all()) applyRate(a, rate)
  }

  /**
   * Quantas partículas estão visíveis (as primeiras N). As escondidas (opacidade 0) ficam
   * pausadas: não custam quadro. Ao voltar, retomam da própria fase, sem salto.
   */
  setVisibleCount(n: number): void {
    if (this.visible === n) return
    this.visible = n
    if (this.mode !== 'running' || this.hidden) return
    this.applyParticles()
  }

  private applyParticles(): void {
    this.particleAnims.forEach((a, i) => {
      applyRate(a, this.rate)
      if (i < this.visible) {
        if (a.playState !== 'running') a.play()
      } else if (a.playState === 'running') {
        a.pause()
      }
    })
  }

  setMode(mode: 'running' | 'frozen' | 'static'): void {
    if (this.mode === mode) return
    this.mode = mode
    this.apply()
  }

  /** Aba oculta: pausa tudo; visível de novo: retoma conforme o modo. */
  setHidden(hidden: boolean): void {
    if (this.hidden === hidden) return
    this.hidden = hidden
    this.apply()
  }

  private apply(): void {
    const anims = this.all()
    if (this.hidden || this.mode === 'frozen') {
      for (const a of anims) if (a.playState === 'running') a.pause()
      return
    }
    if (this.mode === 'static') {
      // Quadro fixo e bem distribuído: zera o tempo das marcas/roletes e espalha as partículas.
      for (const a of this.anims) {
        a.currentTime = 0
        a.pause()
      }
      this.particleAnims.forEach((a, i) => {
        const dur = Number((a.effect as KeyframeEffect).getTiming().duration ?? 0)
        a.currentTime = (((i + 1) * 0.6180339887498949) % 1) * dur
        a.pause()
      })
      return
    }
    for (const a of this.anims) {
      applyRate(a, this.rate)
      if (a.playState !== 'running') a.play()
    }
    this.applyParticles()
  }

  destroy(): void {
    for (const a of this.all()) a.cancel()
    this.anims = []
    this.particleAnims = []
  }
}

function applyRate(a: Animation, rate: number): void {
  if (a.playbackRate === rate) return
  if (typeof a.updatePlaybackRate === 'function') a.updatePlaybackRate(rate)
  else a.playbackRate = rate
}
