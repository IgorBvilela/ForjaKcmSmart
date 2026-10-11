<script lang="ts">
  /** Modo TV (/app/tv): a tela Agora e a Planta juntas, para ler de longe, sem menu e sem nenhum
   *  controle. A tela Agora nunca sai de vista; quando a Planta não cabe, as páginas dela trocam
   *  sozinhas (20 s por padrão; `?troca=N` muda, de 5 a 120 s). Dosador que entra em atenção ganha
   *  brilho suave por 1 min. Edge sem resposta e dado parado aparecem em destaque, e o conteúdo se
   *  desloca de leve, de tempos em tempos, para a imagem não marcar a TV. */
  import { onMount, untrack } from 'svelte'
  import Check from '@lucide/svelte/icons/check'
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert'
  import WifiOff from '@lucide/svelte/icons/wifi-off'
  import { isUsable, stateTone, type PlantCard } from '../lib/api'
  import { fmtAge, fmtClock, fmtDate, fmtNumber } from '../lib/format'
  import { live } from '../lib/live.svelte'
  import { plantTitle } from '../lib/plant'
  import { sinceText, type SituationEntry } from '../lib/situation'
  import { situation } from '../lib/situationStore.svelte'
  import { app } from '../lib/state.svelte'

  const GAP = 20
  const CARD_MIN_W = 300
  /** Quanto tempo o dosador que acabou de entrar em atenção fica com brilho. */
  const FRESH_MS = 60_000
  /** Deslocamento contra marca na TV: um passo a cada 2 min, por estes pontos (px). */
  const DRIFT: Array<[number, number]> = [[0, 0], [3, 2], [6, 4], [3, 6], [0, 4], [-3, 2], [-6, 0], [-3, -2]]
  const DRIFT_STEP_MS = 120_000

  function swapSeconds(): number {
    const raw = Number(new URLSearchParams(window.location.search).get('troca'))
    return Number.isFinite(raw) && raw > 0 ? Math.min(120, Math.max(5, raw)) : 20
  }
  const swapMs = swapSeconds() * 1000

  let panelW = $state(0)
  let panelH = $state(0)
  let viewportH = $state(1080)
  let viewportW = $state(1920)
  let page = $state(0)
  /** Tela estreita não é o uso da TV: tudo numa coluna, sem páginas (a altura cresce com o conteúdo). */
  const narrow = $derived(viewportW < 900)

  const data = $derived(situation.data)
  const summary = $derived(data?.summary)
  const entries = $derived(new Map((data?.equipments ?? []).map((e) => [e.id, e])))
  const problems = $derived(data?.equipments.filter((e) => e.group === 'problem') ?? [])
  const noData = $derived(data?.equipments.filter((e) => e.group === 'no_data') ?? [])
  const cards = $derived(live.plant)
  const title = $derived(plantTitle(cards, 'Forja KCM'))
  const offline = $derived(live.edge === 'offline')
  /** Segundos desde a última mensagem do Edge (pulso ou dado). */
  const heartbeatAge = $derived(
    live.lastHeartbeatAt == null ? null : Math.max(0, (app.now - live.lastHeartbeatAt) / 1000),
  )

  // ---- páginas da Planta: quantos cartões cabem no painel da direita ----
  const cardH = $derived(Math.round(Math.min(260, Math.max(150, viewportH * 0.19))))
  const cols = $derived(
    Math.max(1, Math.min(Math.ceil(Math.sqrt(Math.max(1, cards.length))), Math.floor((panelW + GAP) / (CARD_MIN_W + GAP)) || 1)),
  )
  const rows = $derived(Math.max(1, Math.floor((panelH + GAP) / (cardH + GAP)) || 1))
  const pageSize = $derived(narrow ? Math.max(1, cards.length) : cols * rows)
  const pages = $derived(Math.max(1, Math.ceil(cards.length / pageSize)))
  const shown = $derived(cards.slice((page % pages) * pageSize, (page % pages) * pageSize + pageSize))

  $effect(() => {
    if (pages <= 1) {
      page = 0
      return
    }
    const id = window.setInterval(() => (page = (page + 1) % pages), swapMs)
    return () => window.clearInterval(id)
  })

  // ---- brilho de quem acabou de entrar em atenção (só depois da primeira leitura) ----
  let known: Set<string> | null = null
  let fresh = $state<Record<string, number>>({})
  $effect(() => {
    const ids = problems.map((e) => e.id)
    const ready = data != null
    untrack(() => {
      if (!ready) return
      if (known == null) {
        known = new Set(ids)
        return
      }
      const now = Date.now()
      const next = { ...fresh }
      let changed = false
      for (const id of ids) {
        if (!known.has(id)) {
          next[id] = now
          changed = true
        }
      }
      known = new Set(ids)
      if (changed) fresh = next
    })
  })
  const isFresh = (id: string): boolean => fresh[id] != null && app.now - fresh[id] < FRESH_MS

  // ---- deslocamento contra marca ----
  const drift = $derived(DRIFT[Math.floor(app.now / DRIFT_STEP_MS) % DRIFT.length])

  onMount(() => {
    document.documentElement.classList.add('tv-mode')
    return () => document.documentElement.classList.remove('tv-mode')
  })

  function flowText(c: PlantCard): string {
    const mf = c.mass_flow
    if (!mf || mf.value == null || !(isUsable(mf.quality) || mf.quality === 'STALE')) return '—'
    return fmtNumber(mf.value, mf.decimals)
  }

  function problemLine(e: SituationEntry): string | null {
    if (e.focus) return e.focus.title_pt
    const kcm = e.voices.kcm_alarm
    if (kcm) return `Alarme do KCM ${kcm.code ?? ''}`.trim() + (kcm.title_pt ? ` · ${kcm.title_pt}` : '')
    return e.reason_pt
  }

  function cardLine(c: PlantCard): string | null {
    const e = entries.get(c.id)
    if (c.state_pt === 'Normal' || !e || e.group === 'normal') return null
    const parts = [e.group === 'problem' ? problemLine(e) : e.reason_pt, sinceText(e)].filter(Boolean)
    return parts.length ? parts.join(' · ') : null
  }

  function stale(c: PlantCard): boolean {
    return c.is_stale || c.mass_flow?.quality === 'STALE'
  }
</script>

<svelte:window bind:innerHeight={viewportH} bind:innerWidth={viewportW} />

<div class="tv" data-testid="tv">
  <div class="stage">
  <!-- o deslocamento contra marca fica dentro da margem da tela: nada sai da área visível -->
  <div class="drift" style:transform={narrow ? undefined : `translate(${drift[0]}px, ${drift[1]}px)`}>
    <header class="head">
      <span class="brand" aria-hidden="true">
        <svg viewBox="0 0 32 32" width="40" height="40">
          <rect width="32" height="32" rx="7" fill="var(--accent)" />
          <rect x="8" y="7" width="3.2" height="18" fill="var(--on-accent)" />
          <rect x="8" y="7" width="10" height="3" fill="var(--on-accent)" />
          <rect x="8" y="14" width="7.5" height="3" fill="var(--on-accent)" />
          <rect x="20.5" y="7" width="3.2" height="18" fill="var(--on-accent)" />
          <rect x="20.5" y="22" width="4.5" height="3" fill="var(--on-accent)" />
        </svg>
      </span>
      <h1 class="title">{title}</h1>
      {#if live.dataSource === 'SIMULATED'}
        <span class="sim" data-testid="tv-simulated">Dados simulados</span>
      {/if}
      <span class="updated" data-testid="tv-updated" data-offline={offline}>
        {heartbeatAge == null ? 'aguardando o Edge' : `atualizado ${fmtAge(heartbeatAge)}`}
      </span>
      <time class="clock" data-testid="tv-clock" datetime={new Date(app.now).toISOString()}>
        <span class="clock-time num">{fmtClock(new Date(app.now), false)}</span>
        <span class="clock-date">{fmtDate(app.now)}</span>
      </time>
    </header>

    {#if offline}
      <p class="offline" role="alert" data-testid="tv-offline">
        <WifiOff size={28} aria-hidden="true" />
        Edge sem resposta{heartbeatAge != null ? ` ${fmtAge(heartbeatAge)}` : ''}: os valores na tela são os últimos recebidos.
      </p>
    {/if}

    <div class="body" class:stale-all={offline}>
      <section class="now" data-testid="tv-now" aria-label="Agora">
        {#if !summary}
          <p class="waiting">Lendo a situação da planta…</p>
        {:else}
          <div class="headline" data-tone={summary.tone}>
            <span class="ico" aria-hidden="true">
              {#if summary.tone === 'ok'}<Check size={40} />{:else}<TriangleAlert size={40} />{/if}
            </span>
            <p class="headline-text" data-testid="tv-headline">{summary.headline_pt}</p>
          </div>
          <dl class="counts">
            <div><dd class="n ok">{summary.normal + summary.stopped}</dd><dt>{summary.normal + summary.stopped === 1 ? 'normal' : 'normais'}</dt></div>
            <div><dd class="n" class:warn={summary.attention > 0}>{summary.attention}</dd><dt>em atenção</dt></div>
            <div><dd class="n muted">{summary.no_data}</dd><dt>sem dados</dt></div>
          </dl>
          {#each problems as e (e.id)}
            <article class="problem" class:fresh={isFresh(e.id)} data-testid={`tv-problem-${e.id}`}>
              <p class="p-head">
                <span class="p-name">{e.name}</span>
                {#if sinceText(e)}<span class="p-since">{sinceText(e)}</span>{/if}
              </p>
              {#if problemLine(e)}<p class="p-what">{problemLine(e)}</p>{/if}
              {#if e.focus?.next_check}
                <p class="p-check"><span class="p-label">Verificar primeiro</span> {e.focus.next_check.text_pt}</p>
              {/if}
            </article>
          {/each}
          {#each noData as e (e.id)}
            <p class="nodata" data-testid={`tv-nodata-${e.id}`}>
              <span class="p-name">{e.name}</span>
              <span>{[e.state_pt, sinceText(e)].filter(Boolean).join(' · ')}</span>
            </p>
          {/each}
        {/if}
      </section>

      <section class="plant" aria-label="Planta" bind:clientWidth={panelW} bind:clientHeight={panelH}>
        {#key page % pages}
          <div class="grid" data-testid="tv-plant" style:--cols={cols} style:--card-h={`${cardH}px`}>
            {#each shown as c (c.id)}
              {@const tone = stateTone(c.state_pt)}
              <article class="card" data-tone={tone} data-testid={`tv-card-${c.id}`} data-state={c.state_pt} class:stale={stale(c)}>
                <p class="c-state">{c.state_pt}</p>
                <p class="c-name">{c.name}</p>
                <p class="c-flow">
                  <span class="num">{flowText(c)}</span>
                  {#if flowText(c) !== '—' && c.mass_flow}<span class="unit">{c.mass_flow.unit}</span>{/if}
                </p>
                {#if stale(c)}
                  <p class="c-stale" data-testid={`tv-stale-${c.id}`}>Dado parado</p>
                {:else if cardLine(c)}
                  <p class="c-line">{cardLine(c)}</p>
                {/if}
              </article>
            {/each}
          </div>
        {/key}
        {#if pages > 1}
          <p class="pages" data-testid="tv-pages">
            <span class="num">Página {(page % pages) + 1} de {pages}</span>
            {#key page}<span class="bar" style:--swap={`${swapMs}ms`} aria-hidden="true"></span>{/key}
          </p>
        {/if}
      </section>
    </div>
  </div>
  </div>
</div>

<style>
  /* TV: uma tela só, sem barra de rolagem (o deslocamento contra marca não pode criar uma) */
  @media (min-width: 900px) {
    :global(html.tv-mode), :global(html.tv-mode body) { overflow: hidden; }
  }
  .tv {
    min-height: 100vh;
    min-height: 100dvh;
    background: var(--bg-0);
    color: var(--text-1);
    overflow: hidden;
  }
  .stage {
    height: 100vh;
    height: 100dvh;
    padding: 3vh 2.6vw;
  }
  .drift {
    display: flex;
    flex-direction: column;
    gap: 2.2vh;
    height: 100%;
    transition: transform 4s ease-in-out;
  }
  .head { display: flex; align-items: center; gap: 1.4vw; flex-wrap: wrap; }
  .brand { display: grid; flex: none; }
  .title { margin: 0; font: 600 clamp(22px, 2vw, 46px) / 1.15 var(--font-ui); }
  .sim {
    padding: 4px 14px;
    border: 1px solid var(--q-sim);
    border-radius: var(--r-pill);
    background: var(--q-sim-hatch);
    color: var(--q-sim);
    font: 600 clamp(13px, 1vw, 22px) / 1.3 var(--font-ui);
    letter-spacing: var(--ls-label);
    text-transform: uppercase;
  }
  .updated { margin-left: auto; color: var(--text-2); font: clamp(14px, 1.15vw, 26px) / 1.2 var(--font-ui); }
  .updated[data-offline='true'] { color: var(--st-crit); font-weight: 600; }
  .clock { display: flex; flex-direction: column; align-items: flex-end; }
  .clock-time { font: 500 clamp(32px, 3.4vw, 80px) / 1 var(--font-mono); }
  .clock-date { color: var(--text-2); font: clamp(13px, 0.95vw, 22px) / 1.3 var(--font-ui); }

  .offline {
    display: flex;
    align-items: center;
    gap: 1vw;
    margin: 0;
    padding: 1.4vh 1.4vw;
    border: 2px solid var(--st-crit);
    border-radius: var(--r-4);
    background: var(--st-crit-bg);
    color: var(--st-crit);
    font: 600 clamp(18px, 1.6vw, 38px) / 1.25 var(--font-ui);
  }

  .body { flex: 1; display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 3fr); gap: 2vw; min-height: 0; }
  .stale-all .card, .stale-all .now { opacity: 0.55; }

  .now { display: flex; flex-direction: column; gap: 2vh; min-height: 0; padding-top: 6px; overflow: hidden; }
  .waiting { margin: 0; color: var(--text-2); font-size: clamp(18px, 1.6vw, 36px); }
  .headline { display: flex; align-items: center; gap: 1.2vw; color: var(--st-warn); }
  .headline[data-tone='ok'] { color: var(--st-ok); }
  .headline[data-tone='crit'] { color: var(--st-crit); }
  .headline[data-tone='info'] { color: var(--st-info); }
  .ico { display: grid; place-items: center; flex: none; width: clamp(56px, 4.6vw, 110px); height: clamp(56px, 4.6vw, 110px); border-radius: var(--r-pill); background: currentColor; }
  .ico :global(svg) { color: var(--on-accent); width: 55%; height: 55%; }
  .headline-text { margin: 0; color: var(--text-1); font: 600 clamp(28px, 2.9vw, 68px) / 1.2 var(--font-ui); }
  .counts { display: flex; gap: 2.4vw; margin: 0; }
  .counts div { display: flex; flex-direction: column; }
  .counts dd { order: 1; margin: 0; }
  .counts dt { order: 2; color: var(--text-2); font: clamp(14px, 1.1vw, 26px) / 1.2 var(--font-ui); }
  .n { color: var(--text-1); font: 500 clamp(36px, 3.6vw, 84px) / 1 var(--font-mono); }
  .n.ok { color: var(--st-ok); }
  .n.warn { color: var(--st-warn); }
  .n.muted { color: var(--text-2); }
  .problem {
    display: flex;
    flex-direction: column;
    gap: 0.6vh;
    padding: 1.6vh 1.2vw;
    border-left: 6px solid var(--st-warn);
    border-radius: var(--r-3);
    background: var(--surf-1);
  }
  .problem.fresh { animation: glow 2.4s ease-in-out infinite; }
  .p-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.4vh 1vw; margin: 0; }
  .p-name { color: var(--text-1); font: 600 clamp(20px, 1.7vw, 40px) / 1.2 var(--font-ui); }
  .p-since { color: var(--text-2); font: clamp(16px, 1.25vw, 30px) / 1.2 var(--font-ui); }
  .p-what { margin: 0; color: var(--text-1); font: clamp(17px, 1.35vw, 32px) / 1.3 var(--font-ui); }
  .p-check { margin: 0; color: var(--text-2); font: clamp(15px, 1.15vw, 28px) / 1.35 var(--font-ui); }
  .p-label { color: var(--accent-text); font-weight: 600; }
  .nodata { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.4vh 1vw; margin: 0; padding: 1vh 1.2vw; border-left: 6px solid var(--st-info); border-radius: var(--r-3); background: var(--surf-1); color: var(--text-2); font: clamp(15px, 1.15vw, 28px) / 1.3 var(--font-ui); }

  .plant { display: flex; flex-direction: column; gap: 1.4vh; min-height: 0; overflow: hidden; }
  .grid {
    flex: 1;
    display: grid;
    grid-template-columns: repeat(var(--cols), minmax(0, 1fr));
    grid-auto-rows: var(--card-h);
    gap: 20px;
    align-content: start;
    animation: enter var(--dur-screen) var(--ease-out) both;
  }
  .card {
    display: flex;
    flex-direction: column;
    gap: 0.5vh;
    min-width: 0;
    padding: 1.6vh 1.2vw;
    border-left: 6px solid var(--st-ok);
    border-radius: var(--r-4);
    background: var(--surf-1);
    overflow: hidden;
  }
  .card[data-tone='warn'] { border-left-color: var(--st-warn); }
  .card[data-tone='crit'] { border-left-color: var(--st-crit-fill); }
  .card[data-tone='info'] { border-left-color: var(--st-info); }
  .card[data-tone='neutral'] { border-left-color: var(--chumbo); }
  .c-state { margin: 0; color: var(--st-ok); font: 600 clamp(13px, 1vw, 24px) / 1.2 var(--font-ui); letter-spacing: var(--ls-label); text-transform: uppercase; }
  .card[data-tone='warn'] .c-state { color: var(--st-warn); }
  .card[data-tone='crit'] .c-state { color: var(--st-crit); }
  .card[data-tone='info'] .c-state { color: var(--st-info); }
  .card[data-tone='neutral'] .c-state { color: var(--text-2); }
  .c-name { margin: 0; color: var(--text-1); font: 600 clamp(18px, 1.5vw, 36px) / 1.2 var(--font-ui); }
  .c-flow { display: flex; align-items: baseline; gap: 0.5vw; margin: 0; }
  .c-flow .num { color: var(--text-1); font: 500 clamp(30px, 2.8vw, 66px) / 1 var(--font-mono); }
  .unit { color: var(--text-2); font: clamp(14px, 1vw, 24px) / 1 var(--font-ui); }
  .c-line { margin: 0; color: var(--text-2); font: clamp(14px, 1.05vw, 25px) / 1.3 var(--font-ui); }
  .c-stale {
    align-self: flex-start;
    margin: 0;
    padding: 2px 12px;
    border: 2px dashed var(--st-warn);
    border-radius: var(--r-pill);
    color: var(--st-warn);
    font: 600 clamp(14px, 1.05vw, 25px) / 1.3 var(--font-ui);
  }
  .card.stale .c-flow .num { color: var(--text-3); }
  .pages { display: flex; align-items: center; gap: 1vw; margin: 0; color: var(--text-2); font: clamp(13px, 0.95vw, 22px) / 1.2 var(--font-ui); }
  .bar { flex: 1; height: 4px; border-radius: var(--r-pill); background: var(--accent); transform-origin: left; animation: fill var(--swap) linear both; }

  @keyframes enter { from { opacity: 0; } to { opacity: 1; } }
  @keyframes fill { from { transform: scaleX(0); } to { transform: scaleX(1); } }
  @keyframes glow {
    0%, 100% { box-shadow: 0 0 0 0 rgba(227, 174, 47, 0); }
    50% { box-shadow: 0 0 0 10px rgba(227, 174, 47, 0.22); }
  }
  @media (prefers-reduced-motion: reduce) {
    .problem.fresh { animation: none; box-shadow: 0 0 0 4px rgba(227, 174, 47, 0.45); }
    .bar { animation: none; transform: none; opacity: 0.4; }
  }
  /* tela estreita (não é o uso da TV, mas a rota precisa caber): uma coluna, rola */
  @media (max-width: 899px) {
    .tv, .stage, .drift { height: auto; min-height: 100vh; overflow: visible; }
    .body { grid-template-columns: minmax(0, 1fr); }
    .now, .plant { overflow: visible; }
  }
</style>
