<script lang="ts">
  /** Casos anteriores: "isso já aconteceu antes?". Ocorrências registradas pela Forja neste
   *  equipamento e casos de campo documentados, com o que foi observado, feito e confirmado. */
  import { untrack } from 'svelte'
  import { errorMessage, severityTone } from '../lib/api'
  import { fmtDate, fmtDuration, fmtWhen } from '../lib/format'
  import { intelligenceApi, type CasesResponse } from '../lib/intelligence'
  import { live } from '../lib/live.svelte'
  import { href } from '../lib/router'
  import { app } from '../lib/state.svelte'
  import FieldCaseCard from '../components/data/FieldCaseCard.svelte'
  import Badge from '../components/ui/Badge.svelte'
  import Card from '../components/ui/Card.svelte'
  import EmptyState from '../components/ui/EmptyState.svelte'

  let { equipmentId }: { equipmentId: string } = $props()

  let data = $state<CasesResponse | null>(null)
  let error = $state<string | null>(null)

  const name = $derived(data?.name ?? live.cardOf(equipmentId)?.name ?? equipmentId)

  async function load(id: string): Promise<void> {
    try {
      const r = await intelligenceApi.cases(id)
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
</script>

<section class="cases" data-testid="cases">
  <header class="head">
    <p class="label">{name}</p>
    <h1 class="title">Casos anteriores</h1>
    <p class="sub">
      Isso já aconteceu antes? Ocorrências registradas pela Forja neste equipamento e casos de campo
      documentados, com o que foi observado, o que foi feito e o que se confirmou.
    </p>
  </header>

  {#if error && !data}
    <EmptyState title="Não foi possível carregar os casos" text={error} />
  {:else if !data}
    <div class="skeleton" aria-busy="true" aria-label="Carregando casos"><div class="sk"></div><div class="sk"></div></div>
  {:else}
    <Card title="Ocorrências registradas pela Forja" kicker="neste equipamento" testid="cases-recurrence">
      {#if data.recurrence.length === 0}
        <EmptyState inline title="Nenhuma ocorrência registrada ainda" text="Quando uma regra ou um aviso antecipado abrir, a contagem aparece aqui." />
      {:else}
        <div class="groups">
          {#each data.recurrence as g, i (g.origin + g.type)}
            <article class="group" data-testid="recurrence-{g.type}" style:--i={i}>
              <div class="g-count">
                <span class="g-num num">{g.count}</span>
                <span class="g-unit">{g.count === 1 ? 'vez' : 'vezes'}</span>
              </div>
              <div class="g-body">
                <div class="badges">
                  <Badge tone={severityTone(g.severity)}>{g.origin_pt}</Badge>
                  {#if g.open_count}<Badge tone="warn">{g.open_count} em aberto</Badge>{/if}
                </div>
                <h3 class="g-title">{g.title_pt}</h3>
                {#each g.narrative_pt as line (line)}<p class="g-line">{line}</p>{/each}
                <p class="g-meta">
                  Última: <time class="num" datetime={g.last_start_utc}>{fmtWhen(g.last_start_utc, app.now)}</time>
                  {#if g.count > 1}· primeira em <time class="num" datetime={g.first_start_utc}>{fmtDate(g.first_start_utc)}</time>{/if}
                  {#if g.typical_duration_s != null}· duração típica {fmtDuration(g.typical_duration_s)}{/if}
                </p>
                <a class="link" href={href.event(equipmentId, g.last_event_id)}>Ver a última ocorrência</a>
              </div>
            </article>
          {/each}
        </div>
      {/if}
    </Card>

    <Card title="Casos de campo deste equipamento" kicker="knowledge/cases" testid="cases-field">
      {#if data.field_cases.length === 0}
        <EmptyState inline title="Nenhum caso de campo registrado para este equipamento" text="Casos de campo entram em knowledge/cases, com o que foi observado e a evidência de cada informação." />
      {:else}
        <div class="case-list">
          {#each data.field_cases as c (c.id)}<FieldCaseCard item={c} />{/each}
        </div>
      {/if}
    </Card>

    {#if data.same_application_cases.length}
      <Card title="Mesma aplicação em outros equipamentos" kicker="referência, não é histórico deste" testid="cases-same-application">
        <div class="case-list">
          {#each data.same_application_cases as c (c.id)}<FieldCaseCard item={c} other />{/each}
        </div>
      </Card>
    {/if}

    <p class="note">{data.note_pt}</p>
  {/if}
</section>

<style>
  .cases { display: flex; flex-direction: column; gap: var(--sp-5); }
  .head .label { margin: 0 0 var(--sp-1); }
  .title { margin: 0; color: var(--text-1); font: 600 var(--fs-h1) / var(--lh-h1) var(--font-ui); }
  @media (min-width: 1024px) {
    .title { font-size: var(--fs-display); line-height: var(--lh-display); }
  }
  .sub { margin: var(--sp-1) 0 0; max-width: 72ch; color: var(--text-2); font: var(--fs-body) / var(--lh-body) var(--font-ui); }

  .groups { display: grid; gap: var(--sp-3); grid-template-columns: 1fr; }
  @media (min-width: 1024px) { .groups { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
  .group {
    display: grid;
    grid-template-columns: 64px minmax(0, 1fr);
    gap: var(--sp-3);
    padding: var(--sp-3) var(--sp-4);
    border: 1px solid var(--border-1);
    border-radius: var(--r-3);
    background: var(--surf-2);
    animation: rise var(--dur-screen) var(--ease-out) backwards;
    animation-delay: calc(var(--i, 0) * var(--stagger));
  }
  @keyframes rise {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: none; }
  }
  .g-count { display: flex; flex-direction: column; align-items: center; justify-content: flex-start; padding-top: var(--sp-1); }
  .g-num { color: var(--accent-text); font: 600 var(--fs-num-lg) / var(--lh-num-lg) var(--font-mono); font-variant-numeric: tabular-nums; }
  .g-unit { color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .g-body { display: flex; flex-direction: column; gap: var(--sp-1); min-width: 0; }
  .g-title { margin: var(--sp-1) 0 0; color: var(--text-1); font: 600 var(--fs-body) / var(--lh-body) var(--font-ui); }
  .g-line { margin: 0; color: var(--text-1); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .g-meta { margin: 0; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .badges { display: flex; flex-wrap: wrap; gap: var(--sp-2); }

  .case-list { display: flex; flex-direction: column; gap: var(--sp-4); }
  .note { margin: 0; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); max-width: 90ch; }
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
  .skeleton { display: grid; gap: var(--sp-4); }
  .skeleton .sk { height: 160px; border-radius: var(--r-4); background: var(--surf-2); opacity: 0.6; }
</style>
