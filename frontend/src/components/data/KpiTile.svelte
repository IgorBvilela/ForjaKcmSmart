<script lang="ts">
  /** Indicador do dashboard e do simulador.
   *  `compact` (6 numa linha, ≥ 1280 px): número 24 px, mini-tendência 32 px, qualidade na linha da
   *  legenda e "Entender esta variável" como botão de info ao lado do rótulo.
   *  `explainQuality`: a pill de qualidade vira alvo de toque que abre a explicação (nada fica só em title).
   *  `textValue`: valor em texto (ex.: estado da máquina) no lugar do número.
   *  `sparkline={false}`: sem mini-tendência (simulador). */
  import Info from '@lucide/svelte/icons/info'
  import type { Quality } from '../../lib/api'
  import { isUsable } from '../../lib/api'
  import type { SeriesPoint } from '../../lib/live.svelte'
  import { fmtNumber } from '../../lib/format'
  import { TID } from '../../lib/testids'
  import AnimatedNumber from './AnimatedNumber.svelte'
  import Sparkline from './Sparkline.svelte'
  import QualityBadge from '../ui/QualityBadge.svelte'
  import Disclosure from '../ui/Disclosure.svelte'
  import Tooltip from '../ui/Tooltip.svelte'

  let {
    tag,
    label,
    unit = '',
    decimals = 1,
    value = null,
    textValue = null,
    quality = 'COMM_ERROR',
    qualityPt = null,
    ageS = null,
    reasonPt = null,
    explanation = '',
    points = [],
    refValue = null,
    caption = null,
    captionTitle = null,
    color = 'var(--s1)',
    index = 0,
    animate = true,
    compact = false,
    sparkline = true,
    explainQuality = false,
    popoverAlign = 'start',
  }: {
    tag: string
    label: string
    unit?: string
    decimals?: number
    value?: number | null
    textValue?: string | null
    quality?: Quality
    qualityPt?: string | null
    ageS?: number | null
    reasonPt?: string | null
    explanation?: string
    points?: SeriesPoint[]
    refValue?: number | null
    caption?: string | null
    /** Texto completo da legenda quando a visível é encurtada (vira title). */
    captionTitle?: string | null
    color?: string
    index?: number
    animate?: boolean
    compact?: boolean
    sparkline?: boolean
    explainQuality?: boolean
    popoverAlign?: 'start' | 'end'
  } = $props()

  const usable = $derived(isUsable(quality))
  const showsValue = $derived(usable || quality === 'STALE')
  const staleValue = $derived(quality === 'STALE' ? fmtNumber(value, decimals) : null)
  /** Legenda de estado da leitura. No compacto ela NÃO aparece: a pill de qualidade já diz
   *  "Sem comunicação" / "Valor antigo" / "Inválido" e a explicação abre no toque; repetir ao lado
   *  só truncava ("S..."). */
  const statusText = $derived(
    quality === 'COMM_ERROR'
      ? 'Sem comunicação'
      : quality === 'STALE'
        ? 'Último valor conhecido. Não é o estado atual.'
        : quality === 'BAD'
          ? 'Leitura inválida'
          : null,
  )

  /** Explicação da qualidade para o popover de toque (a razão do backend tem prioridade). */
  const qualityText = $derived(
    reasonPt ??
      (quality === 'STALE'
        ? 'Último valor conhecido. Não representa o estado atual.'
        : quality === 'SIMULATED'
          ? 'Dado gerado pelo simulador. Nenhum valor representa um KCM real.'
          : quality === 'COMM_ERROR'
            ? 'A tentativa de leitura falhou. O KCM pode estar operando normalmente; a Forja só não conseguiu ler.'
            : quality === 'BAD'
              ? 'Leitura inválida: valor fora do esperado ou não decodificável.'
              : quality === 'UNCERTAIN'
                ? 'Valor lido, mas ainda não validado em campo.'
                : 'Leitura validada.'),
  )
</script>

{#snippet qbadge()}
  {#if explainQuality}
    <span class="tile-q">
      <Tooltip label={`Qualidade do dado: ${qualityPt ?? quality}`} text={qualityText} align={popoverAlign}>
        <QualityBadge {quality} {qualityPt} {ageS} {reasonPt} testid={TID.kpi.quality(tag)} />
      </Tooltip>
    </span>
  {:else}
    <QualityBadge {quality} {qualityPt} {ageS} {reasonPt} testid={TID.kpi.quality(tag)} />
  {/if}
{/snippet}

<article
  class="tile"
  class:compact
  data-testid={TID.kpi.tile(tag)}
  data-tag={tag}
  data-quality={quality}
  data-variant={compact ? 'compact' : 'full'}
  class:stale={quality === 'STALE'}
  class:comm={quality === 'COMM_ERROR' || quality === 'BAD'}
  style:--i={index}
>
  <header class="tile-head">
    <span class="label">{label}</span>
    {#if compact && explanation}
      <span class="tile-info">
        <Tooltip
          label={`Entender esta variável: ${label}`}
          text={explanation}
          align={popoverAlign}
          testid={TID.kpi.explain(tag)}
        >
          <Info size={16} strokeWidth={1.75} aria-hidden="true" />
        </Tooltip>
      </span>
    {/if}
  </header>

  <div class="tile-row">
    <div class="tile-value" aria-live="off">
      {#if textValue != null}
        <span class="value text" data-testid={TID.kpi.value(tag)} data-value={textValue}>{textValue}</span>
      {:else if usable}
        <AnimatedNumber {value} {decimals} animate={animate && usable} testid={TID.kpi.value(tag)} />
      {:else if quality === 'STALE'}
        <span class="num value" data-testid={TID.kpi.value(tag)} data-value={value ?? ''}>{staleValue}</span>
      {:else}
        <span class="num value" data-testid={TID.kpi.value(tag)} data-value="">—</span>
      {/if}
      {#if unit && showsValue && textValue == null}<span class="unit">{unit}</span>{/if}
    </div>
    {#if !compact}{@render qbadge()}{/if}
  </div>

  <p class="tile-sub" class:status={statusText != null}>
    {#if compact}{@render qbadge()}{/if}
    {#if statusText}
      {#if !compact}<span class="sub">{statusText}</span>{/if}
    {:else if caption}
      <span class="sub" title={captionTitle ?? undefined}>{caption}</span>
    {:else}
      <span class="sub">&nbsp;</span>
    {/if}
  </p>

  {#if sparkline}
    <Sparkline {points} {refValue} faded={!usable} {color} height={compact ? 32 : 36} label={`Mini-tendência de ${label}`} />
  {/if}

  {#if explanation && !compact}
    <div class="tile-foot">
      <Disclosure summary="Entender esta variável" size="sm" testid={TID.kpi.explain(tag)}>
        <p class="explain">{explanation}</p>
      </Disclosure>
    </div>
  {/if}
</article>

<style>
  .tile {
    position: relative;
    display: flex;
    flex-direction: column;
    gap: var(--sp-2);
    min-width: 0;
    padding: var(--sp-4) var(--sp-5);
    background: var(--surf-1);
    border: 1px solid var(--border-1);
    border-radius: var(--r-4);
    /* `backwards`, não `both`: animação preenchida mantém o tile como contexto de empilhamento
       e o tile seguinte cobriria o popover "Entender esta variável" deste. */
    animation: rise var(--dur-screen) var(--ease-out) backwards;
    animation-delay: calc(var(--i, 0) * var(--stagger));
    transition:
      opacity var(--dur-base) var(--ease-std),
      border-color var(--dur-base) var(--ease-std);
  }
  @keyframes rise {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: none; }
  }
  /* popover aberto: este tile por cima dos vizinhos */
  .tile:focus-within,
  .tile:has(:global(.tip-pop)) { z-index: 2; }
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
    align-items: baseline;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: var(--sp-1) var(--sp-2);
    min-width: 0;
  }
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
  .value.text {
    font: 600 var(--fs-h2) / var(--lh-h2) var(--font-ui);
    letter-spacing: 0;
    overflow-wrap: anywhere;
  }
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
  /* pill de qualidade como alvo de toque: visual igual, caixa do botão sem padding extra */
  .tile-q { display: inline-flex; }
  .tile-q :global(.tip-btn) {
    min-height: 0;
    padding: 0;
    border-radius: var(--r-pill);
    background: transparent;
  }
  .tile-q :global(.tip-btn:hover) { background: transparent; }
  .tile-q :global(.tip-btn:hover .q) { border-color: var(--border-2); }
  @media (max-width: 767px) {
    .tile { padding: var(--sp-4); }
    .tile-value {
      font-size: var(--fs-num-lg);
      line-height: var(--lh-num-lg);
      min-height: var(--lh-num-lg);
    }
  }
  @media (max-width: 767px), (pointer: coarse) {
    .tile-q :global(.tip-btn) { min-height: var(--touch); }
  }

  /* ---- variante compacta ---- */
  .tile.compact {
    container-type: inline-size;
    gap: var(--sp-1);
    padding: var(--sp-3);
  }
  .compact .tile-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: var(--sp-1);
    /* duas linhas reservadas: rótulos longos ("Esforço do acionamento") não desalinham a linha */
    min-height: calc(2 * var(--lh-label));
  }
  .compact .tile-head .label { flex: 1 1 auto; min-height: 0; }
  .tile-info {
    flex: none;
    display: inline-flex;
    margin: -4px -4px 0 0;
  }
  .tile-info :global(.tip-btn) {
    position: relative;
    width: 24px;
    min-height: 24px;
    padding: 0;
    justify-content: center;
    border-radius: var(--r-2);
    color: var(--text-3);
  }
  .tile-info :global(.tip-btn:hover),
  .tile-info :global(.tip-btn[aria-expanded='true']) {
    color: var(--accent-text);
    background: var(--accent-soft);
  }
  @media (pointer: coarse) {
    /* alvo real de 44 px; margem negativa segura o rótulo no lugar */
    .tile-info { margin: -10px -10px 0 0; }
    .tile-info :global(.tip-btn) { width: var(--touch); min-height: var(--touch); }
  }
  .compact .tile-value {
    font-size: var(--fs-num-lg);
    line-height: var(--lh-num-lg);
    min-height: var(--lh-num-lg);
  }
  .compact .tile-sub {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--sp-2);
    min-height: 20px;
  }
  /* só a pill: ela pode ocupar a linha inteira sem nada cortado ao lado */
  .compact .tile-sub.status { justify-content: flex-start; }
  .compact .tile-sub .sub {
    flex: 1 1 auto;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    text-align: right;
  }
  /* tile largo (1920): rótulo numa linha, número 32 px. A consulta mede a caixa de conteúdo
     (sem padding/borda): 196 px de tile em 1366 → 170 px; 245 px em 1920 → 219 px. */
  @container (min-width: 205px) {
    .compact .tile-head { min-height: var(--lh-label); }
    .compact .tile-value {
      font-size: var(--fs-num-xl);
      line-height: var(--lh-num-xl);
      min-height: var(--lh-num-xl);
    }
  }
</style>
