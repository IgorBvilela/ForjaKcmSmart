<script lang="ts">
  /** Aviso antecipado: regras de tendência e desvio do padrão, com o que cada sinal mediu agora e o
   *  limite configurado. Não é previsão de falha e não é alarme do KCM. */
  import { untrack } from 'svelte'
  import Info from '@lucide/svelte/icons/info'
  import { errorMessage, type StateTone } from '../lib/api'
  import { fmtTime } from '../lib/format'
  import {
    EW_STATE_TONE,
    VERDICT_TONE,
    intelligenceApi,
    type EarlyWarningResponse,
    type EwRule,
    type EwSignal,
  } from '../lib/intelligence'
  import type { SeriesPoint } from '../lib/live.svelte'
  import { live } from '../lib/live.svelte'
  import { href } from '../lib/router'
  import EventRow from '../components/data/EventRow.svelte'
  import Sparkline from '../components/data/Sparkline.svelte'
  import Badge from '../components/ui/Badge.svelte'
  import Card from '../components/ui/Card.svelte'
  import EmptyState from '../components/ui/EmptyState.svelte'
  import PageHeader from '../components/ui/PageHeader.svelte'
  import StatusDot from '../components/ui/StatusDot.svelte'

  let { equipmentId }: { equipmentId: string } = $props()

  const REFRESH_MS = 15000
  let data = $state<EarlyWarningResponse | null>(null)
  let error = $state<string | null>(null)

  const name = $derived(data?.name ?? live.cardOf(equipmentId)?.name ?? equipmentId)

  async function load(id: string): Promise<void> {
    try {
      const r = await intelligenceApi.earlyWarning(id)
      if (id !== equipmentId) return
      data = r
      error = null
    } catch (err) {
      if (id === equipmentId) error = errorMessage(err)
    }
  }

  $effect(() => {
    const id = equipmentId
    void live.eventsVersion
    untrack(() => void load(id))
  })

  $effect(() => {
    const id = equipmentId
    const timer = setInterval(() => void load(id), REFRESH_MS)
    return () => clearInterval(timer)
  })

  function points(signal: EwSignal): SeriesPoint[] {
    return signal.spark.map((v, i) => ({ t: i, v, q: 'GOOD' }))
  }

  function hasSpark(signal: EwSignal): boolean {
    return signal.spark.filter((v) => v != null).length >= 2
  }

  function sparkColor(signal: EwSignal): string {
    if (signal.tag === 'drive_command') return 'var(--s2)'
    return 'var(--s3)'
  }

  /** Condição presente só pinta de atenção quando a regra inteira está ativa ou confirmando. */
  function isAlerting(rule: EwRule): boolean {
    return rule.state === 'ACTIVE' || rule.state === 'CONFIRMING'
  }

  function verdictTone(rule: EwRule, signal: EwSignal): StateTone {
    if (signal.verdict === 'MET') return isAlerting(rule) ? 'warn' : 'info'
    return signal.verdict ? VERDICT_TONE[signal.verdict] : 'neutral'
  }

  function metCount(rule: EwRule): number {
    return rule.signals.filter((s) => s.verdict === 'MET').length
  }
</script>

<section class="ew" data-testid="early-warning">
  <PageHeader kicker={name} title="Aviso antecipado" lead="Sinais fracos antes do alarme, com a evidência de cada um.">
    {#snippet more()}
      <p>Tendência, desvio do padrão do próprio equipamento e combinação de variáveis, com limites configurados.</p>
    {/snippet}
  </PageHeader>

  {#if error && !data}
    <EmptyState title="Não foi possível carregar o aviso antecipado" text={error} />
  {:else if !data}
    <div class="skeleton" aria-busy="true" aria-label="Carregando aviso antecipado"><div class="sk"></div><div class="sk"></div></div>
  {:else}
    <aside class="disclaimer" data-testid="ew-disclaimer">
      <span class="d-icon" aria-hidden="true"><Info size={18} /></span>
      <p>{data.disclaimer_pt}</p>
    </aside>

    {#if !data.available || data.rules.length === 0}
      <EmptyState
        title="Nenhuma regra de aviso antecipado vale para este equipamento"
        text="As regras ficam em config/early_warning e podem se limitar a uma aplicação (por exemplo, WBF)."
      />
    {:else}
      <div class="rules">
        {#each data.rules as rule, i (rule.id)}
          <article class="rule" data-state={rule.state} data-testid="ew-rule-{rule.id}" style:--i={i}>
            <header class="rule-head">
              <p class="state" data-tone={EW_STATE_TONE[rule.state]}>
                <StatusDot state={EW_STATE_TONE[rule.state]} size={10} pulse={rule.state === 'ACTIVE'} />
                <span>{rule.state_pt}</span>
              </p>
              <h2 class="rule-title">{rule.title_pt}</h2>
              <p class="rule-meta">
                Janela de {rule.window_pt} · avaliada a cada {rule.evaluate_every_pt} · abre após
                {rule.persist_evaluations} avaliações seguidas · {rule.severity_pt}
              </p>
            </header>
            {#if rule.description_pt}<p class="desc">{rule.description_pt}</p>{/if}

            <p class="count">
              <span class="num">{metCount(rule)}</span> de <span class="num">{rule.signals.length}</span>
              condições presentes agora
            </p>
            <ol class="signals">
              {#each rule.signals as s (s.tag + s.kind)}
                <li class="signal" data-verdict={s.verdict ?? 'NONE'} data-alert={isAlerting(rule) && s.verdict === 'MET'} data-testid="ew-signal-{rule.id}-{s.tag}">
                  <div class="sig-head">
                    <span class="sig-name">{s.label_pt}</span>
                    <span class="sig-kind">{s.kind_pt}</span>
                    {#if s.verdict}
                      <Badge tone={verdictTone(rule, s)}>{s.verdict_pt}</Badge>
                    {:else}
                      <Badge tone="neutral">{s.verdict_pt}</Badge>
                    {/if}
                  </div>
                  {#if hasSpark(s)}
                    <div class="spark">
                      <Sparkline points={points(s)} height={34} color={sparkColor(s)} showWindow={false} label={`${s.label_pt} na janela de ${rule.window_pt}`} />
                    </div>
                  {/if}
                  <p class="sig-line"><span class="k">Agora</span><span>{s.text_pt || 'ainda não avaliado'}</span></p>
                  {#if s.limit_pt}<p class="sig-line"><span class="k">Limite configurado</span><span>{s.limit_pt}</span></p>{/if}
                </li>
              {/each}
            </ol>

            <footer class="rule-foot">
              <p class="evidence"><Badge tone="ghost">Regra Forja</Badge> {rule.threshold_note_pt}</p>
              <p class="last">
                {#if rule.last_evaluated_utc}
                  Última avaliação às <span class="num">{fmtTime(rule.last_evaluated_utc)}</span>{#if rule.preview}&nbsp;(leitura avulsa desta tela; não conta para a confirmação){/if}
                {:else}
                  Aguardando a primeira avaliação.
                {/if}
              </p>
              {#if rule.open_event_id}
                <a class="link" href={href.event(equipmentId, rule.open_event_id)}>Ver aviso aberto</a>
              {/if}
            </footer>
          </article>
        {/each}
      </div>
    {/if}

    <Card title="Avisos anteriores" kicker="registrados pela Forja" padded={false} testid="ew-recent">
      {#if data.recent.length === 0}
        <div class="pad">
          <EmptyState inline title="Nenhum aviso antecipado registrado" text="Quando uma regra se confirmar, o aviso fica guardado aqui com o resumo dos sinais." />
        </div>
      {:else}
        <div class="recent">
          {#each data.recent as e, i (e.id)}
            <EventRow event={e} href={href.event(equipmentId, e.id)} index={i} />
          {/each}
        </div>
      {/if}
    </Card>
  {/if}
</section>

<style>
  .ew { display: flex; flex-direction: column; gap: var(--sp-5); }

  .disclaimer {
    display: flex;
    gap: var(--sp-3);
    align-items: flex-start;
    padding: var(--sp-3) var(--sp-4);
    border: 1px solid var(--st-info);
    border-radius: var(--r-4);
    background: var(--st-info-bg);
    color: var(--text-1);
  }
  .disclaimer p { margin: 0; font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  .d-icon { color: var(--st-info); display: grid; place-items: center; height: var(--lh-body); }

  .rules { display: grid; gap: var(--sp-4); grid-template-columns: 1fr; }
  @media (min-width: 1280px) { .rules { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
  .rule {
    display: flex;
    flex-direction: column;
    gap: var(--sp-3);
    padding: var(--sp-4);
    border: 1px solid var(--border-1);
    border-radius: var(--r-4);
    background: var(--surf-1);
    min-width: 0;
    animation: rise var(--dur-screen) var(--ease-out) backwards;
    animation-delay: calc(var(--i, 0) * var(--stagger));
    transition: border-color var(--dur-base) var(--ease-std);
  }
  .rule[data-state='ACTIVE'] { border-color: var(--st-warn); box-shadow: inset 3px 0 0 var(--st-warn); }
  .rule[data-state='CONFIRMING'] { box-shadow: inset 3px 0 0 var(--st-info); }
  @keyframes rise {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: none; }
  }
  .rule-head { display: flex; flex-direction: column; gap: var(--sp-1); }
  .state { display: inline-flex; align-items: center; gap: var(--sp-2); margin: 0; font: 600 var(--fs-caption) / var(--lh-caption) var(--font-ui); color: var(--text-2); }
  .state[data-tone='warn'] { color: var(--st-warn); }
  .state[data-tone='info'] { color: var(--st-info); }
  .state[data-tone='ok'] { color: var(--st-ok); }
  .rule-title { margin: 0; color: var(--text-1); font: 600 var(--fs-h2) / var(--lh-h2) var(--font-ui); }
  .rule-meta, .desc, .count { margin: 0; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .desc { font-size: var(--fs-body); line-height: var(--lh-body); }
  .count .num { color: var(--text-1); font-family: var(--font-mono); font-weight: 600; }

  .signals { display: flex; flex-direction: column; gap: var(--sp-2); margin: 0; padding: 0; list-style: none; }
  .signal {
    display: flex;
    flex-direction: column;
    gap: var(--sp-1);
    padding: var(--sp-3);
    border: 1px solid var(--border-1);
    border-radius: var(--r-3);
    background: var(--surf-2);
    min-width: 0;
    transition: border-color var(--dur-base) var(--ease-std);
  }
  .signal[data-verdict='MET'] { border-color: var(--st-info); }
  .signal[data-alert='true'] { border-color: var(--st-warn); }
  .sig-head { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-2); }
  .sig-name { color: var(--text-1); font: 600 var(--fs-body) / var(--lh-body) var(--font-ui); }
  .sig-kind { color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); margin-right: auto; }
  .spark { padding: var(--sp-1) 0; }
  .sig-line {
    display: grid;
    grid-template-columns: 9.5em minmax(0, 1fr);
    gap: var(--sp-2);
    margin: 0;
    color: var(--text-1);
    font: var(--fs-caption) / var(--lh-caption) var(--font-ui);
    overflow-wrap: anywhere;
  }
  .k { color: var(--text-2); font-weight: 500; }
  @media (max-width: 479px) {
    .sig-line { grid-template-columns: 1fr; gap: 0; }
  }

  .rule-foot { display: flex; flex-direction: column; gap: var(--sp-2); padding-top: var(--sp-2); border-top: 1px solid var(--border-1); }
  .evidence, .last { margin: 0; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .last .num { color: var(--text-1); font-family: var(--font-mono); }
  .link {
    display: inline-flex;
    align-items: center;
    align-self: flex-start;
    min-height: var(--touch);
    color: var(--accent-text);
    font: 600 var(--fs-body) / 1.2 var(--font-ui);
    text-decoration: underline;
    text-underline-offset: 3px;
  }
  .link:focus-visible { outline: none; box-shadow: var(--focus); border-radius: var(--r-1); }
  .recent { display: flex; flex-direction: column; }
  .pad { padding: var(--sp-4); }
  .skeleton { display: grid; gap: var(--sp-4); }
  .skeleton .sk { height: 220px; border-radius: var(--r-4); background: var(--surf-2); opacity: 0.6; }
</style>
