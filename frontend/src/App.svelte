<script lang="ts">
  /** Shell + roteador. Cada rota do contrato tem página real ou estado vazio honesto. */
  import { onMount } from 'svelte'
  import AppShell from './components/shell/AppShell.svelte'
  import EmptyState from './components/ui/EmptyState.svelte'
  import { live } from './lib/live.svelte'
  import { knowledgeItem, navItemForEqScreen, systemItem, toolsItem } from './lib/nav'
  import { href, installLinkInterceptor, routeSlug } from './lib/router'
  import { app } from './lib/state.svelte'
  import { TID } from './lib/testids'
  import AboutPage from './routes/AboutPage.svelte'
  import ComingSoonPage from './routes/ComingSoonPage.svelte'
  import DashboardPage from './routes/DashboardPage.svelte'
  import DiagnosisPage from './routes/DiagnosisPage.svelte'
  import EventsPage from './routes/EventsPage.svelte'
  import PlantPage from './routes/PlantPage.svelte'
  import SimulatorPage from './routes/SimulatorPage.svelte'

  const PRODUCT = 'Forja KCM Intelligence'

  onMount(() => {
    app.start()
    live.start()
    const off = installLinkInterceptor(document.body)
    return () => {
      off()
      live.stop()
      app.stop()
    }
  })

  const route = $derived(app.route)

  const title = $derived.by(() => {
    const r = route
    switch (r.name) {
      case 'plant':
        return `Planta · ${PRODUCT}`
      case 'eq': {
        const name = live.cardOf(r.id)?.name ?? r.id
        if (r.eventId) return `Evento · ${name} · ${PRODUCT}`
        const item = navItemForEqScreen(r.screen)
        return `${item?.label ?? r.screen} · ${name} · ${PRODUCT}`
      }
      case 'knowledge':
        return `${knowledgeItem(r.sub)?.label ?? r.sub} · ${PRODUCT}`
      case 'tools':
        return `${toolsItem(r.sub)?.label ?? r.sub} · ${PRODUCT}`
      case 'system':
        return `${systemItem(r.sub)?.label ?? r.sub} · ${PRODUCT}`
      default:
        return PRODUCT
    }
  })

  $effect(() => {
    document.title = title
  })
</script>

<AppShell>
  {#key app.path}
    <div class="page" data-testid={TID.page} data-route={routeSlug(route)}>
      {#if route.name === 'plant'}
        <PlantPage />
      {:else if route.name === 'eq'}
        {#if route.eventId}
          <DiagnosisPage equipmentId={route.id} eventId={route.eventId} />
        {:else if route.screen === 'dashboard'}
          <DashboardPage equipmentId={route.id} />
        {:else if route.screen === 'events'}
          <EventsPage equipmentId={route.id} mode="events" />
        {:else if route.screen === 'diagnostics'}
          <EventsPage equipmentId={route.id} mode="diagnostics" />
        {:else if route.screen === 'simulator'}
          <SimulatorPage equipmentId={route.id} />
        {:else}
          <ComingSoonPage item={navItemForEqScreen(route.screen)} equipmentId={route.id} />
        {/if}
      {:else if route.name === 'knowledge'}
        <ComingSoonPage item={knowledgeItem(route.sub)} />
      {:else if route.name === 'tools'}
        <ComingSoonPage item={toolsItem(route.sub)} />
      {:else if route.name === 'system'}
        {#if route.sub === 'about'}
          <AboutPage />
        {:else}
          <ComingSoonPage item={systemItem(route.sub)} />
        {/if}
      {:else if route.name === 'dev' && import.meta.env.DEV && route.sub === 'wbf'}
        {#await import('./routes/DevWbfPage.svelte') then mod}
          <mod.default />
        {/await}
      {:else}
        <EmptyState
          title="Página não encontrada"
          text="O endereço não corresponde a nenhuma tela desta versão."
        >
          <a class="home" href={href.plant()}>Ir para a planta</a>
        </EmptyState>
      {/if}
    </div>
  {/key}
</AppShell>

<style>
  .page {
    min-width: 0;
    animation: enter var(--dur-screen) var(--ease-out) both;
  }
  @keyframes enter {
    from { opacity: 0; transform: translateY(4px); }
    to { opacity: 1; transform: none; }
  }
  .home {
    display: inline-flex;
    align-items: center;
    min-height: var(--touch);
    padding: 0 var(--sp-4);
    margin-top: var(--sp-2);
    border-radius: var(--r-3);
    background: var(--accent);
    color: var(--on-accent);
    font: 500 var(--fs-body) / var(--lh-body) var(--font-ui);
    text-decoration: none;
  }
</style>
