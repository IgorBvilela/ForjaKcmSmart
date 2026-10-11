<script lang="ts">
  /** Abas do dosador: cada aba leva a uma rota que já existe. Fica fora da página para o
   *  indicador deslizar entre uma aba e outra em vez de renascer a cada navegação. */
  import { activeTab, EQ_SUBTABS, EQ_TABS } from '../../lib/eqtabs'
  import { href, type EqScreen } from '../../lib/router'

  let { equipmentId, screen }: { equipmentId: string; screen: EqScreen } = $props()

  const TABS = EQ_TABS
  const active = $derived(activeTab(screen))
  const subtabs = $derived(EQ_SUBTABS[active] ?? null)

  let links: HTMLAnchorElement[] = $state([])
  let scroller: HTMLDivElement | undefined = $state()
  let width = $state(0)
  let marker = $state({ x: 0, w: 0 })

  /** No celular a faixa rola: a aba ativa entra inteira na vista, sem rolar a página. */
  function reveal(link: HTMLAnchorElement): void {
    if (!scroller) return
    const margin = 16
    const left = link.offsetLeft - margin
    const right = link.offsetLeft + link.offsetWidth + margin - scroller.clientWidth
    const target = left < scroller.scrollLeft ? left : right > scroller.scrollLeft ? right : null
    if (target == null) return
    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches
    scroller.scrollTo({ left: Math.max(0, target), behavior: reduced ? 'auto' : 'smooth' })
  }

  $effect(() => {
    void width
    const index = TABS.findIndex((t) => t.id === active)
    const link = links[index]
    if (!link) return
    marker = { x: link.offsetLeft, w: link.offsetWidth }
    reveal(link)
  })
</script>

<nav class="eqtabs" aria-label="Telas do dosador" data-testid="eq-tabs">
  <div class="scroller" bind:this={scroller} bind:clientWidth={width}>
    <ul class="tabs">
      {#each TABS as tab, i (tab.id)}
        <li>
          <a
            bind:this={links[i]}
            class="tab"
            href={href.eq(equipmentId, tab.home)}
            aria-current={active === tab.id ? 'page' : undefined}
            data-testid={`eq-tab-${tab.id}`}
          >
            {tab.label}
          </a>
        </li>
      {/each}
      <li class="marker" aria-hidden="true" style:transform={`translateX(${marker.x}px)`} style:width={`${marker.w}px`}></li>
    </ul>
  </div>
  {#if subtabs}
    <ul class="subtabs" aria-label={TABS.find((t) => t.id === active)?.label}>
      {#each subtabs as sub (sub.screen)}
        <li>
          <a
            class="subtab"
            href={href.eq(equipmentId, sub.screen)}
            aria-current={screen === sub.screen ? 'page' : undefined}
            data-testid={`eq-subtab-${sub.screen}`}
          >
            {sub.label}
          </a>
        </li>
      {/each}
    </ul>
  {/if}
</nav>

<style>
  .eqtabs {
    display: flex;
    flex-direction: column;
    gap: var(--sp-3);
    margin: calc(-1 * var(--sp-2)) 0 var(--sp-5);
  }
  .scroller {
    overflow-x: auto;
    border-bottom: 1px solid var(--border-1);
    scroll-padding-inline: var(--sp-4);
    scrollbar-width: none;
  }
  .tabs {
    position: relative;
    display: flex;
    gap: var(--sp-1);
    width: max-content;
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .tab {
    display: inline-flex;
    align-items: center;
    min-height: var(--touch);
    padding: 0 var(--sp-4);
    border-radius: var(--r-2) var(--r-2) 0 0;
    color: var(--text-2);
    font: 600 var(--fs-body-lg) / 1.2 var(--font-ui);
    text-decoration: none;
    white-space: nowrap;
    transition: color var(--dur-base) var(--ease-std), background-color var(--dur-base) var(--ease-std);
  }
  .tab:hover { color: var(--text-1); background: var(--surf-1); }
  .tab[aria-current='page'] { color: var(--text-1); }
  /* dentro da faixa que rola, o contorno de foco fica por dentro para não ser cortado */
  .tab:focus-visible { box-shadow: inset 0 0 0 2px var(--accent); }
  .marker {
    position: absolute;
    bottom: 0;
    left: 0;
    height: 3px;
    border-radius: 3px 3px 0 0;
    background: var(--accent);
    transition: transform var(--dur-spring) var(--ease-spring), width var(--dur-spring) var(--ease-spring);
  }
  .subtabs {
    display: flex;
    flex-wrap: wrap;
    gap: var(--sp-2);
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .subtab {
    display: inline-flex;
    align-items: center;
    min-height: 36px;
    padding: 0 var(--sp-3);
    border: 1px solid var(--border-2);
    border-radius: var(--r-pill);
    color: var(--text-2);
    font: 500 var(--fs-body) / 1.2 var(--font-ui);
    text-decoration: none;
    white-space: nowrap;
    transition: color var(--dur-base) var(--ease-std), border-color var(--dur-base) var(--ease-std),
      background-color var(--dur-base) var(--ease-std);
  }
  .subtab:hover { color: var(--text-1); border-color: var(--border-input); }
  .subtab[aria-current='page'] { border-color: var(--accent); background: var(--accent-soft); color: var(--text-1); }
  @media (max-width: 1023px), (pointer: coarse) {
    .subtab { min-height: var(--touch); }
  }
</style>
