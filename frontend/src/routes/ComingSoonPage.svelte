<script lang="ts">
  /** Rota prevista no contrato mas sem backend nesta fase. Estado vazio honesto, sem botão falso. */
  import Inbox from '@lucide/svelte/icons/inbox'
  import type { NavItem } from '../lib/nav'
  import { live } from '../lib/live.svelte'
  import EmptyState from '../components/ui/EmptyState.svelte'

  let { item, equipmentId = null }: { item: NavItem | undefined; equipmentId?: string | null } = $props()

  const Icon = $derived(item?.icon ?? Inbox)
  const name = $derived(equipmentId ? (live.cardOf(equipmentId)?.name ?? equipmentId) : null)
  const title = $derived(item?.label ?? 'Página')
  const phase = $derived(item?.phase ?? undefined)
  const reason = $derived(item?.reason ?? 'Esta tela depende de uma fase posterior do plano.')
</script>

<section class="soon">
  <header class="soon-head">
    {#if name}<p class="label">{name}</p>{/if}
    <h1 class="soon-title">{title}</h1>
  </header>
  <EmptyState
    title={phase ? `${title} ainda não está disponível` : `${title} não está configurado`}
    {phase}
    text={`${reason} Nenhuma função desta tela comanda o KCM: a Forja só lê.`}
  >
    {#snippet icon()}
      <Icon size={26} strokeWidth={1.5} />
    {/snippet}
  </EmptyState>
</section>

<style>
  .soon { display: flex; flex-direction: column; gap: var(--sp-5); }
  .soon-head .label { margin: 0 0 var(--sp-1); }
  .soon-title {
    margin: 0;
    font: 600 var(--fs-h1) / var(--lh-h1) var(--font-ui);
    color: var(--text-1);
  }
  @media (min-width: 1024px) {
    .soon-title { font-size: var(--fs-display); line-height: var(--lh-display); }
  }
</style>
