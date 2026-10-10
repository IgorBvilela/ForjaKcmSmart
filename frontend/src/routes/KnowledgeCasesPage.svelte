<script lang="ts">
  /** Biblioteca de casos de campo de todos os equipamentos (knowledge/cases). */
  import { onMount } from 'svelte'
  import { errorMessage } from '../lib/api'
  import { intelligenceApi, type FieldCase } from '../lib/intelligence'
  import FieldCaseCard from '../components/data/FieldCaseCard.svelte'
  import EmptyState from '../components/ui/EmptyState.svelte'

  let cases = $state<FieldCase[] | null>(null)
  let note = $state('')
  let error = $state<string | null>(null)
  let query = $state('')

  const visible = $derived.by(() => {
    const list = cases ?? []
    const q = query.trim().toLocaleLowerCase('pt-BR')
    if (!q) return list
    return list.filter((c) =>
      [c.title_pt, c.equipment, c.application, ...c.observed_facts_pt, c.learned_rule_pt]
        .join(' ')
        .toLocaleLowerCase('pt-BR')
        .includes(q),
    )
  })

  onMount(async () => {
    try {
      const r = await intelligenceApi.knowledgeCases()
      cases = r.cases
      note = r.note_pt
    } catch (err) {
      error = errorMessage(err)
    }
  })
</script>

<section class="lib" data-testid="knowledge-cases">
  <header class="head">
    <p class="label">Conhecimento</p>
    <h1 class="title">Casos de campo</h1>
    <p class="sub">
      Todos os casos registrados, de todos os equipamentos. Cada informação traz a sua evidência; a
      causa só aparece como confirmada quando há prova que feche a cadeia.
    </p>
  </header>

  {#if error}
    <EmptyState title="Não foi possível carregar os casos" text={error} />
  {:else if cases === null}
    <div class="sk" aria-busy="true" aria-label="Carregando casos"></div>
  {:else if cases.length === 0}
    <EmptyState title="Nenhum caso de campo registrado" text="Casos entram em knowledge/cases, com o que foi observado e a evidência de cada informação." />
  {:else}
    <label class="search">
      <span class="label">Procurar</span>
      <input type="search" bind:value={query} placeholder="equipamento, sintoma, aplicação" data-testid="knowledge-cases-search" />
    </label>
    <p class="count"><span class="num">{visible.length}</span> de <span class="num">{cases.length}</span> caso(s)</p>
    <div class="list">
      {#each visible as c (c.id)}<FieldCaseCard item={c} />{/each}
    </div>
    {#if note}<p class="note">{note}</p>{/if}
  {/if}
</section>

<style>
  .lib { display: flex; flex-direction: column; gap: var(--sp-4); }
  .head .label { margin: 0 0 var(--sp-1); }
  .title { margin: 0; color: var(--text-1); font: 600 var(--fs-h1) / var(--lh-h1) var(--font-ui); }
  @media (min-width: 1024px) {
    .title { font-size: var(--fs-display); line-height: var(--lh-display); }
  }
  .sub { margin: var(--sp-1) 0 0; max-width: 72ch; color: var(--text-2); font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  .search { display: flex; flex-direction: column; gap: var(--sp-1); max-width: 480px; }
  .search input {
    width: 100%;
    min-height: var(--touch);
    padding: var(--sp-2) var(--sp-3);
    border: 1px solid var(--border-input);
    border-radius: var(--r-2);
    background: var(--surf-2);
    color: var(--text-1);
    font: 16px / 1.3 var(--font-ui);
  }
  .search input:focus-visible { outline: none; box-shadow: var(--focus); }
  .count, .note { margin: 0; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .count .num { color: var(--text-1); font-family: var(--font-mono); }
  .list { display: flex; flex-direction: column; gap: var(--sp-4); }
  .sk { height: 200px; border-radius: var(--r-4); background: var(--surf-2); opacity: 0.6; }
</style>
