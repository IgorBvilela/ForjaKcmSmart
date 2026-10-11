<script lang="ts">
  /** Eventos do equipamento (mais recentes primeiro). Modo "diagnostics" lista só os que têm diagnóstico. */
  import { untrack } from 'svelte'
  import { api, errorMessage, type EventView } from '../lib/api'
  import { live } from '../lib/live.svelte'
  import { href } from '../lib/router'
  import { TID } from '../lib/testids'
  import EventRow from '../components/data/EventRow.svelte'
  import Button from '../components/ui/Button.svelte'
  import EmptyState from '../components/ui/EmptyState.svelte'
  import PageHeader from '../components/ui/PageHeader.svelte'

  let { equipmentId, mode = 'events' }: { equipmentId: string; mode?: 'events' | 'diagnostics' } =
    $props()

  let events = $state<EventView[]>([])
  let loading = $state(true)
  let error = $state<string | null>(null)
  let filter = $state<'all' | 'open'>('all')
  /** id → tem diagnóstico? (null = ainda consultando) */
  let hasDiagnosis = $state<Record<string, boolean | null>>({})

  const card = $derived(live.cardOf(equipmentId))
  const name = $derived(card?.name ?? equipmentId)

  const visible = $derived.by(() => {
    let list = events
    if (filter === 'open') list = list.filter((e) => e.is_open)
    if (mode === 'diagnostics') {
      list = list.filter((e) => e.severity !== 'INFO' && hasDiagnosis[e.id] !== false)
    }
    return list
  })
  const openCount = $derived(events.filter((e) => e.is_open).length)

  async function load(id: string): Promise<void> {
    try {
      const r = await api.events(id, { limit: 100 })
      if (id !== equipmentId) return
      events = r.events
      error = null
      void probeDiagnoses(r.events)
    } catch (err) {
      if (id === equipmentId) error = errorMessage(err)
    } finally {
      if (id === equipmentId) loading = false
    }
  }

  async function probeDiagnoses(list: EventView[]): Promise<void> {
    const pending = list.filter((e) => e.severity !== 'INFO' && hasDiagnosis[e.id] == null)
    for (const e of pending) hasDiagnosis[e.id] = null
    await Promise.all(
      pending.map(async (e) => {
        try {
          const d = await api.diagnosis(e.id)
          hasDiagnosis[e.id] = d != null
        } catch {
          hasDiagnosis[e.id] = false
        }
      }),
    )
  }

  $effect(() => {
    const id = equipmentId
    void live.eventsVersion
    void live.diagnosisVersion
    untrack(() => {
      if (events.length === 0) loading = true
      void load(id)
    })
  })
</script>

<section class="events" data-mode={mode}>
  <PageHeader
    kicker={name}
    title={mode === 'diagnostics' ? 'Diagnósticos' : 'Eventos'}
    lead={mode === 'diagnostics'
      ? 'Eventos que já têm o diagnóstico da Forja.'
      : 'O que as regras da Forja detectaram, com o que mudou primeiro.'}
  >
    {#snippet more()}
      {#if mode === 'diagnostics'}
        <p>Cada diagnóstico tem sete seções, do resumo às ressalvas. Hipótese é "comportamento compatível com", nunca causa.</p>
      {:else}
        <p>Cada evento guarda a janela anterior à detecção, para responder o que mudou primeiro.</p>
      {/if}
    {/snippet}
    {#snippet actions()}
      <div class="events-filters" role="group" aria-label="Filtro de eventos">
        <Button variant="ghost" size="sm" pressed={filter === 'all'} onclick={() => (filter = 'all')}>
          Todos <span class="count num">{events.length}</span>
        </Button>
        <Button variant="ghost" size="sm" pressed={filter === 'open'} onclick={() => (filter = 'open')}>
          Em aberto <span class="count num">{openCount}</span>
        </Button>
      </div>
    {/snippet}
  </PageHeader>

  {#if error}
    <EmptyState title="Não foi possível carregar os eventos" text={error} />
  {:else if loading && events.length === 0}
    <div class="list skeleton" aria-busy="true" aria-label="Carregando eventos">
      <div class="sk-row"></div><div class="sk-row"></div><div class="sk-row"></div>
    </div>
  {:else if visible.length === 0}
    <EmptyState
      title={mode === 'diagnostics' ? 'Nenhum diagnóstico para mostrar' : filter === 'open' ? 'Nenhum evento em aberto' : 'Nenhum evento registrado'}
      text={mode === 'diagnostics'
        ? 'Quando uma regra abrir um evento de atenção ou crítico, o diagnóstico aparece aqui.'
        : 'Enquanto as leituras ficarem dentro do padrão, esta lista fica vazia. Isso é bom.'}
    />
  {:else}
    <div class="list" data-testid={TID.events.list} data-count={visible.length}>
      {#each visible as e, i (e.id)}
        <EventRow event={e} href={href.event(equipmentId, e.id)} hasDiagnosis={hasDiagnosis[e.id] ?? null} index={i} />
      {/each}
    </div>
  {/if}
</section>

<style>
  .events { display: flex; flex-direction: column; gap: var(--sp-5); }
  .events-filters { display: flex; gap: var(--sp-2); }
  .count { color: var(--text-3); font-size: var(--fs-mono-sm); }

  .list {
    display: flex;
    flex-direction: column;
    border: 1px solid var(--border-1);
    border-radius: var(--r-4);
    overflow: hidden;
    background: var(--surf-1);
  }
  .skeleton { padding: var(--sp-2); gap: var(--sp-2); }
  .sk-row {
    height: 64px;
    border-radius: var(--r-3);
    background: var(--surf-2);
    opacity: 0.6;
  }
</style>
