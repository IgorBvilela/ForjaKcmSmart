<script lang="ts">
  /** Visão da planta: um cartão por dosador em grade quase quadrada (colunas = raiz de N,
   *  arredondada para cima e limitada pela largura: 4 ficam 2 × 2). Clique abre o Dashboard. */
  import { type PlantCard } from '../lib/api'
  import { fmtNumber, plural } from '../lib/format'
  import { live } from '../lib/live.svelte'
  import { situation } from '../lib/situationStore.svelte'
  import { TID } from '../lib/testids'
  import PlantCardView from '../components/plant/PlantCard.svelte'
  import EmptyState from '../components/ui/EmptyState.svelte'

  const cards = $derived(live.plant)
  /** Motivo e "desde quando" de cada dosador: a mesma situação da tela Agora. */
  const entries = $derived(new Map((situation.data?.equipments ?? []).map((e) => [e.id, e])))

  /** Cards agrupados por área e linha (o que o perfil informa; desconhecido vai para um grupo). */
  const groups = $derived.by(() => {
    const known = (v: string | undefined) => (v && v !== 'UNKNOWN' ? v : null)
    const map = new Map<string, { key: string; title: string; cards: PlantCard[] }>()
    for (const c of cards) {
      const area = known(c.area)
      const line = known(c.line)
      const key = `${area ?? '~'}|${line ?? ''}`
      const title = area ? (line ? `${area} · ${line}` : area) : 'Área não informada'
      if (!map.has(key)) map.set(key, { key, title, cards: [] })
      map.get(key)?.cards.push(c)
    }
    return [...map.values()].sort((a, b) => a.key.localeCompare(b.key, 'pt-BR'))
  })
  const grouped = $derived(groups.length > 1)

  const title = $derived.by(() => {
    const prefixes = new Set<string>()
    for (const c of cards) {
      const suffix = ` — ${c.name}`
      if (c.display_path.endsWith(suffix)) {
        const p = c.display_path.slice(0, -suffix.length)
        if (p) prefixes.add(p)
      }
    }
    return prefixes.size ? [...prefixes].join(' · ') : 'Planta'
  })

  /** Ordem do resumo. Estado fora da lista entra no fim: nada fora do normal fica sem contagem. */
  const SUMMARY_ORDER = [
    'Crítico',
    'Atenção',
    'Sem comunicação',
    'Coleta não iniciada',
    'Coleta pausada',
    'Parado',
    'Desconhecido',
  ]
  const SUMMARY_LABEL: Record<string, string> = {
    'Coleta não iniciada': 'com coleta não iniciada',
    'Coleta pausada': 'com coleta pausada',
  }

  const summary = $derived.by(() => {
    if (cards.length === 0) return ''
    const counts = new Map<string, number>()
    for (const c of cards) counts.set(c.state_pt, (counts.get(c.state_pt) ?? 0) + 1)
    const parts = [plural(cards.length, 'equipamento', 'equipamentos')]
    const others = [...counts.keys()].filter((k) => k !== 'Normal' && !SUMMARY_ORDER.includes(k))
    for (const k of [...SUMMARY_ORDER, ...others]) {
      const n = counts.get(k)
      if (n) parts.push(`${fmtNumber(n, 0)} ${SUMMARY_LABEL[k] ?? k.toLowerCase()}`)
    }
    if (counts.get('Normal') === cards.length) parts.push('todos em condição normal')
    return parts.join(' · ')
  })

  /** Colunas ideais da grade quase quadrada; a largura disponível pode reduzir (CSS). */
  function idealColumns(n: number): number {
    return Math.max(1, Math.ceil(Math.sqrt(n)))
  }
</script>

<section class="plant">
  <header class="plant-head">
    <div>
      <p class="label">Visão da planta</p>
      <h1 class="plant-title" data-testid={TID.plant.title}>{title}</h1>
    </div>
    {#if summary}
      <p class="plant-summary" data-testid={TID.plant.summary}>{summary}</p>
    {/if}
  </header>

  {#if cards.length === 0}
    {#if live.plantError}
      <EmptyState
        title="Sem resposta do Edge"
        text={`${live.plantError} A interface volta a tentar sozinha a cada 15 s.`}
      />
    {:else if live.edge === 'connecting'}
      <EmptyState title="Conectando ao serviço local" text="Aguardando o primeiro snapshot do Edge." />
    {:else}
      <EmptyState
        title="Nenhum equipamento configurado"
        text="Os perfis ficam em config/equipment. Sem perfil, não há o que observar."
      />
    {/if}
  {:else}
    <div class="groups" data-testid={TID.plant.grid}>
      {#each groups as g (g.key)}
      <section class="area" aria-label={g.title}>
      {#if grouped}
        <h2 class="area-title">{g.title}<span class="area-count">{plural(g.cards.length, 'equipamento', 'equipamentos')}</span></h2>
      {/if}
      <div class="grid" style:--ideal={idealColumns(g.cards.length)}>
      {#each g.cards as c, i (c.id)}
        <PlantCardView card={c} entry={entries.get(c.id)} index={i} />
      {/each}
      </div>
      </section>
      {/each}
    </div>
  {/if}
</section>

<style>
  .plant { display: flex; flex-direction: column; gap: var(--sp-6); }
  .plant-head {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: var(--sp-4);
    flex-wrap: wrap;
  }
  .plant-head .label { margin: 0 0 var(--sp-1); }
  .plant-title {
    margin: 0;
    font: 600 var(--fs-h1) / var(--lh-h1) var(--font-ui);
    color: var(--text-1);
  }
  @media (min-width: 1024px) {
    .plant-title { font-size: var(--fs-display); line-height: var(--lh-display); }
  }
  .plant-summary {
    margin: 0;
    color: var(--text-2);
    font: var(--fs-body) / var(--lh-body) var(--font-ui);
  }

  .groups { display: flex; flex-direction: column; gap: var(--sp-6); }
  .area { display: flex; flex-direction: column; gap: var(--sp-3); }
  .area-title {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: var(--sp-3);
    margin: 0;
    color: var(--text-1);
    font: 600 var(--fs-h2) / var(--lh-h2) var(--font-ui);
  }
  .area-count { color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  /* Grade quase quadrada: cada coluna tem no mínimo 1/ideal da largura (nunca mais que
     `ideal` colunas) e no mínimo 280 px (menos colunas quando não cabe). 4 → 2 × 2. */
  .grid {
    --gap: var(--sp-5);
    display: grid;
    grid-template-columns: repeat(
      auto-fill,
      minmax(max(280px, calc((100% - (var(--ideal) - 1) * var(--gap)) / var(--ideal))), 1fr)
    );
    gap: var(--gap);
    /* cartão com no máximo ~640 px: em tela larga a grade não estica até a borda */
    max-width: calc(var(--ideal) * 640px + (var(--ideal) - 1) * var(--gap));
  }
  @media (max-width: 767px) {
    .grid { --gap: var(--sp-4); }
  }
</style>
