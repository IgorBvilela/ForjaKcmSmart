<script lang="ts">
  /** Cartão da Planta: estado, nome, vazão em destaque, motivo e desde quando (fora do normal) e
   *  o desvio da vazão em relação ao setpoint. O link é uma camada sobre o cartão inteiro, com
   *  nome curto ("Nome: estado. Abrir dashboard"): os dados não entram no texto do link.
   *  Motivo e "desde quando" vêm da mesma situação da tela Agora. O desvio só aparece com a
   *  máquina em operação e as duas leituras utilizáveis; nunca é estimado. */
  import { isUsable, stateTone, type PlantCard } from '../../lib/api'
  import { ageSince, fmtNumber } from '../../lib/format'
  import { live } from '../../lib/live.svelte'
  import { href } from '../../lib/router'
  import { sinceText, type SituationEntry } from '../../lib/situation'
  import { app } from '../../lib/state.svelte'
  import { TID } from '../../lib/testids'
  import Badge from '../ui/Badge.svelte'
  import QualityBadge from '../ui/QualityBadge.svelte'
  import StatusDot from '../ui/StatusDot.svelte'

  let {
    card,
    entry,
    index = 0,
  }: { card: PlantCard; entry: SituationEntry | undefined; index?: number } = $props()

  /** Estados com a máquina em operação: só neles o desvio do setpoint quer dizer algo. */
  const RUNNING = new Set(['Normal', 'Atenção', 'Crítico'])
  /** Escala do desenho da barra (±10 %). É escala de desenho, não limite de processo. */
  const SCALE_PCT = 10

  const tone = $derived(stateTone(card.state_pt))
  const mf = $derived(card.mass_flow)
  const usable = $derived(mf ? isUsable(mf.quality) : false)
  const showValue = $derived(!!mf && (usable || mf.quality === 'STALE'))
  /** Qualidade só aparece quando a máquina opera e a leitura não é boa (velha, incerta...). */
  const showQuality = $derived(
    !!mf && RUNNING.has(card.state_pt) && mf.quality !== 'GOOD' && mf.quality !== 'SIMULATED',
  )

  /** Motivo e desde quando, só fora do normal e quando a situação concorda. */
  const extra = $derived.by(() => {
    if (card.state_pt === 'Normal' || !entry || entry.group === 'normal') return null
    let reason: string | null = entry.reason_pt
    if (entry.group === 'problem') {
      const kcm = entry.voices.kcm_alarm
      const kcmText = kcm
        ? `Alarme do KCM ${kcm.code ?? ''}`.trim() + (kcm.title_pt ? ` · ${kcm.title_pt}` : '')
        : null
      reason = entry.focus?.title_pt ?? kcmText
    }
    const since = sinceText(entry)
    if (!reason && !since) return null
    return { reason, since }
  })

  /** Desvio da vazão em relação ao setpoint, em %. Nulo quando não dá para afirmar. */
  const deviation = $derived.by(() => {
    if (!RUNNING.has(card.state_pt) || !mf || !usable || mf.value == null) return null
    const sp = live.tagOf(card.id, 'setpoint')
    if (!sp || !isUsable(sp.quality) || sp.value == null || sp.value <= 0) return null
    return ((mf.value - sp.value) / sp.value) * 100
  })

  const bar = $derived.by(() => {
    if (deviation == null) return null
    const clamped = Math.max(-SCALE_PCT, Math.min(SCALE_PCT, deviation))
    const half = (Math.abs(clamped) / SCALE_PCT) * 50
    return clamped < 0 ? { left: 50 - half, width: half } : { left: 50, width: half }
  })

  /** "+1,2%", "−2,3%" ou "0,0%" (uma casa; o sinal sai do valor arredondado). */
  function deviationPct(value: number): string {
    const rounded = Math.round(value * 10) / 10
    const sign = rounded > 0 ? '+' : rounded < 0 ? '−' : ''
    return `${sign}${fmtNumber(Math.abs(rounded), 1)}%`
  }
</script>

<article
  class="pcard"
  data-testid={TID.plant.card(card.id)}
  data-state={card.state_pt}
  data-conn={card.connection}
  data-quality={mf?.quality ?? ''}
  data-tone={tone}
  style:--i={index}
>
  <a class="go" href={href.eq(card.id)} aria-label={`${card.name}: ${card.state_pt}. Abrir dashboard`}></a>
  <span class="head">
    <span class="state" data-tone={tone}>
      <StatusDot state={tone} hollow={tone === 'info'} size={9} />
      <span>{card.state_pt}</span>
    </span>
    {#if card.data_source === 'SIMULATED'}
      <Badge tone="sim" hatch>Simulado</Badge>
    {/if}
  </span>

  <h2 class="name">{card.name}</h2>

  <span class="value" class:faded={!usable}>
    <span class="num big">{showValue ? fmtNumber(mf?.value, mf?.decimals) : '—'}</span>
    {#if showValue && mf}<span class="unit">{mf.unit}</span>{/if}
    {#if showQuality && mf}
      <span class="quality">
        <QualityBadge
          quality={mf.quality}
          qualityPt={mf.quality_pt}
          ageS={mf.quality === 'STALE' ? ageSince(mf.ts_utc, app.now) : null}
          reasonPt={mf.reason_pt}
        />
      </span>
    {/if}
  </span>

  {#if extra}
    <span class="extra" data-testid="plant-extra">
      {#if extra.reason}<span class="reason">{extra.reason}</span>{/if}
      {#if extra.reason && extra.since}<span class="sep" aria-hidden="true">·</span>{/if}
      {#if extra.since}<span class="since">{extra.since}</span>{/if}
    </span>
  {/if}

  {#if bar && deviation != null}
    <span class="dev" data-testid="plant-deviation">
      <span class="track" aria-hidden="true">
        <span class="zero"></span>
        <span class="fill" data-tone={tone} style:left={`${bar.left}%`} style:width={`${bar.width}%`}></span>
      </span>
      <span class="dev-text"><span class="num">{deviationPct(deviation)}</span> do setpoint</span>
    </span>
  {/if}
</article>

<style>
  .pcard {
    position: relative;
    display: flex;
    flex-direction: column;
    gap: var(--sp-3);
    min-width: 0;
    height: 100%;
    padding: var(--sp-5);
    border: 1px solid var(--border-1);
    border-radius: var(--r-4);
    background: var(--surf-1);
    color: inherit;
    text-decoration: none;
    box-shadow: var(--edge, 0 0 #0000);
    animation: rise var(--dur-screen) var(--ease-out) backwards;
    animation-delay: calc(var(--i, 0) * var(--stagger));
    transition:
      border-color var(--dur-base) var(--ease-std),
      background-color var(--dur-base) var(--ease-std),
      transform var(--dur-base) var(--ease-out);
  }
  /* faixa à esquerda só fora do normal: chama o olho sem pintar o cartão inteiro */
  .pcard[data-tone='warn'] { --edge: inset 3px 0 0 var(--st-warn); }
  .pcard[data-tone='crit'] { --edge: inset 3px 0 0 var(--st-crit-fill); }
  .pcard[data-tone='info'] { --edge: inset 3px 0 0 var(--st-info); }
  .pcard:hover { border-color: var(--border-2); background: var(--surf-2); transform: translateY(-2px); }
  .pcard:active { transform: none; }
  /* o link cobre o cartão inteiro (alvo = cartão); o contorno de foco também */
  .go { position: absolute; inset: -1px; z-index: 1; border-radius: var(--r-4); }
  .go:focus-visible { outline: none; box-shadow: var(--focus); }
  @keyframes rise {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: none; }
  }

  .head { display: flex; align-items: center; justify-content: space-between; gap: var(--sp-2); flex-wrap: wrap; }
  .state {
    display: inline-flex;
    align-items: center;
    gap: var(--sp-2);
    color: var(--text-2);
    font: 600 var(--fs-label) / var(--lh-label) var(--font-ui);
    letter-spacing: var(--ls-label);
    text-transform: uppercase;
    white-space: nowrap;
  }
  .state[data-tone='ok'] { color: var(--st-ok); }
  .state[data-tone='warn'] { color: var(--st-warn); }
  .state[data-tone='crit'] { color: var(--st-crit); }
  .state[data-tone='info'] { color: var(--st-info); }

  .name { margin: 0; color: var(--text-1); font: 600 var(--fs-h2) / var(--lh-h2) var(--font-ui); }

  .value { display: flex; align-items: baseline; flex-wrap: wrap; gap: var(--sp-1) var(--sp-2); color: var(--text-1); }
  .value.faded .big { color: var(--text-3); }
  .big { font-size: var(--fs-num-xl); line-height: var(--lh-num-xl); font-weight: 500; }
  .unit { color: var(--text-2); font: 500 var(--fs-body) / 1 var(--font-ui); }
  .quality { align-self: center; }

  .extra {
    display: flex;
    flex-wrap: wrap;
    gap: 0 var(--sp-2);
    color: var(--text-2);
    font: var(--fs-body) / var(--lh-body) var(--font-ui);
  }
  .reason { color: var(--text-1); }
  .sep { color: var(--text-3); }

  .dev { display: flex; flex-direction: column; gap: var(--sp-1); margin-top: auto; }
  .track { position: relative; height: 8px; border-radius: var(--r-pill); background: var(--surf-2); }
  .pcard:hover .track { background: var(--surf-3); }
  .zero {
    position: absolute;
    top: -3px;
    bottom: -3px;
    left: 50%;
    width: 2px;
    margin-left: -1px;
    border-radius: 1px;
    background: var(--text-3);
  }
  .fill {
    position: absolute;
    top: 0;
    bottom: 0;
    border-radius: var(--r-pill);
    background: var(--text-3);
    transition: left var(--dur-spring) var(--ease-spring), width var(--dur-spring) var(--ease-spring);
  }
  .fill[data-tone='ok'] { background: var(--st-ok); }
  .fill[data-tone='warn'] { background: var(--st-warn); }
  .fill[data-tone='crit'] { background: var(--st-crit-fill); }
  .dev-text { color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .dev-text .num { color: var(--text-1); }

  @media (prefers-reduced-motion: reduce) {
    .pcard:hover { transform: none; }
  }
</style>
