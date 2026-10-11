<script lang="ts">
  /** Barra do tempo em três partes: dentro do normal (verde), fora do normal (âmbar) e sem dados
   *  (listrado: forma, não só cor). Valor novo anima por recorte, sem mexer no layout; com
   *  movimento reduzido troca na hora. As partes vêm em porcentagem do período. */
  interface Props {
    normal: number
    out: number
    noData: number
    /** Frase completa para leitor de tela (a barra é uma imagem). */
    label: string
    height?: number
    testid?: string
  }

  let { normal, out, noData, label, height = 8, testid }: Props = $props()

  function clamp(v: number): number {
    return Number.isFinite(v) ? Math.min(100, Math.max(0, v)) : 0
  }

  const n = $derived(clamp(normal))
  const o = $derived(Math.min(clamp(out), 100 - n))
</script>

<span
  class="bar"
  role="img"
  aria-label={label}
  style:height={`${height}px`}
  data-testid={testid}
  data-normal={n}
  data-out={o}
  data-no-data={clamp(noData)}
>
  <span class="part normal" style:clip-path={`inset(0 ${100 - n}% 0 0)`}></span>
  <span class="part out" style:clip-path={`inset(0 ${100 - n - o}% 0 ${n}%)`}></span>
  <span class="part none" style:clip-path={`inset(0 0 0 ${n + o}%)`}></span>
</span>

<style>
  .bar {
    position: relative;
    display: block;
    width: 100%;
    overflow: hidden;
    border-radius: var(--r-pill);
    background: var(--surf-2);
  }
  .part { position: absolute; inset: 0; transition: clip-path var(--dur-spring) var(--ease-spring); }
  .normal { background: var(--st-ok); }
  .out { background: var(--st-warn); }
  .none { background: repeating-linear-gradient(135deg, var(--text-3) 0 3px, transparent 3px 6px); }
</style>
