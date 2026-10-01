<script lang="ts">
  /** Grade do app: sidebar (rail ou drawer) + header fixo + faixa de fonte + conteúdo. */
  import type { Snippet } from 'svelte'
  import { app } from '../../lib/state.svelte'
  import { TID } from '../../lib/testids'
  import DataSourceBanner from './DataSourceBanner.svelte'
  import Drawer from './Drawer.svelte'
  import Header from './Header.svelte'
  import Sidebar from './Sidebar.svelte'

  let { children }: { children?: Snippet } = $props()
</script>

<a class="skip" href="#conteudo" data-testid={TID.skipLink}>Ir para o conteúdo</a>

<div
  class="shell"
  data-sidebar={app.isNarrow ? 'drawer' : app.sidebarCollapsed ? 'collapsed' : 'open'}
>
  {#if app.isNarrow}
    <Drawer open={app.drawerOpen} onclose={() => app.closeDrawer()}>
      <Sidebar mode="drawer" />
    </Drawer>
  {:else}
    <aside class="rail" id="sidebar">
      <Sidebar mode="rail" />
    </aside>
  {/if}

  <!-- com o drawer aberto o resto da tela fica inerte: sem foco, sem clique, fora da árvore acessível -->
  <div class="main" inert={app.drawerOpen}>
    <Header />
    <DataSourceBanner />
    <main id="conteudo" class="content" tabindex="-1">
      {@render children?.()}
    </main>
  </div>
</div>

<style>
  .skip {
    position: absolute;
    left: var(--sp-4);
    top: -100px;
    z-index: 100;
    display: inline-flex;
    align-items: center;
    min-height: var(--touch);
    padding: 0 var(--sp-4);
    border-radius: var(--r-3);
    background: var(--accent);
    color: var(--on-accent);
    font: 500 var(--fs-body) / var(--lh-body) var(--font-ui);
    text-decoration: none;
    transition: top var(--dur-micro) var(--ease-out);
  }
  .skip:focus { top: var(--sp-2); }

  .shell {
    display: grid;
    grid-template-columns: var(--rail-w, var(--sidebar-w)) minmax(0, 1fr);
    min-height: 100%;
    transition: grid-template-columns var(--dur-screen) var(--ease-std);
  }
  .shell[data-sidebar='collapsed'] { --rail-w: var(--sidebar-w-collapsed); }
  .shell[data-sidebar='drawer'] { grid-template-columns: minmax(0, 1fr); }

  .rail {
    position: sticky;
    top: 0;
    /* acima do conteúdo: o tooltip do rail recolhido (position: fixed) nasce dentro deste contexto */
    z-index: 30;
    height: 100vh;
    height: 100dvh;
    min-width: 0;
    overflow: hidden;
  }

  .main {
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 100%;
  }
  .content {
    flex: 1 1 auto;
    width: 100%;
    max-width: var(--content-max);
    margin: 0 auto;
    padding: var(--sp-6);
    min-width: 0;
    outline: none;
  }
  @media (max-width: 1023px) {
    .content { padding: var(--sp-5); }
  }
  @media (max-width: 767px) {
    .content { padding: var(--sp-4); }
  }
</style>
