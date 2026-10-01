<script lang="ts">
  /** Navegação em 7 grupos. Recolhida mostra só ícones (rótulo acessível continua). */
  import ChevronRight from '@lucide/svelte/icons/chevron-right'
  import X from '@lucide/svelte/icons/x'
  import { NAV_GROUPS, type NavItem } from '../../lib/nav'
  import { live } from '../../lib/live.svelte'
  import { routeSlug } from '../../lib/router'
  import { app } from '../../lib/state.svelte'
  import { TID } from '../../lib/testids'

  let { mode = 'rail' }: { mode?: 'rail' | 'drawer' } = $props()

  const collapsed = $derived(mode === 'rail' && app.sidebarCollapsed)
  const currentSlug = $derived(routeSlug(app.route))
  const eqId = $derived(app.equipmentId ?? live.plant[0]?.id ?? null)

  function isActive(item: NavItem): boolean {
    return item.slug === currentSlug
  }
</script>

<nav
  class="sb"
  class:collapsed
  data-mode={mode}
  data-testid={TID.sidebar.root}
  data-state={collapsed ? 'collapsed' : 'open'}
  aria-label="Navegação principal"
>
  <div class="sb-top">
    {#if mode === 'drawer'}
      <span class="sb-title">Menu</span>
      <button
        type="button"
        class="sb-btn"
        aria-label="Fechar menu"
        data-testid={TID.sidebar.toggle}
        onclick={() => app.closeDrawer()}
      >
        <X size={20} aria-hidden="true" />
      </button>
    {:else}
      <button
        type="button"
        class="sb-btn sb-collapse"
        aria-label={collapsed ? 'Expandir menu' : 'Recolher menu'}
        aria-expanded={!collapsed}
        data-testid={TID.sidebar.toggle}
        onclick={() => app.toggleSidebar()}
      >
        <span class="sb-collapse-icon" aria-hidden="true"><ChevronRight size={18} /></span>
      </button>
    {/if}
  </div>

  <div class="sb-scroll">
    {#each NAV_GROUPS as group (group.id)}
      <section class="group" aria-labelledby={`sb-g-${group.id}`}>
        <h2 class="group-label label" id={`sb-g-${group.id}`}>{group.label}</h2>
        <ul class="items">
          {#each group.items as item (item.slug)}
            {@const target = item.to(eqId)}
            {@const active = isActive(item)}
            <li>
              {#if target}
                <a
                  class="item"
                  class:active
                  class:soon={Boolean(item.phase)}
                  href={target}
                  aria-current={active ? 'page' : undefined}
                  data-testid={TID.sidebar.link(item.slug)}
                  data-phase={item.phase ?? ''}
                  title={collapsed ? item.label : undefined}
                >
                  <span class="item-icon" aria-hidden="true">
                    <item.icon size={18} strokeWidth={1.75} />
                  </span>
                  <span class="item-label">{item.label}</span>
                  {#if item.phase}<span class="item-phase" aria-label={`Disponível na fase ${item.phase}`}>{item.phase}</span>{/if}
                </a>
              {:else}
                <span class="item disabled" aria-disabled="true" title="Selecione um equipamento">
                  <span class="item-icon" aria-hidden="true"><item.icon size={18} strokeWidth={1.75} /></span>
                  <span class="item-label">{item.label}</span>
                </span>
              {/if}
            </li>
          {/each}
        </ul>
      </section>
    {/each}
  </div>

  <div class="sb-foot">
    <span class="foot-line">Edge local · 127.0.0.1</span>
    <span class="foot-line">Observa. Não comanda.</span>
  </div>
</nav>

<style>
  .sb {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    background: var(--surf-1);
    border-right: 1px solid var(--border-1);
    color: var(--text-2);
    overflow: hidden;
  }
  .sb[data-mode='drawer'] { border-right: 0; }

  .sb-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: var(--header-h);
    padding: 0 var(--sp-3);
    border-bottom: 1px solid var(--border-1);
    flex: none;
  }
  .collapsed .sb-top { justify-content: center; padding: 0; }
  .sb-title {
    font: 600 var(--fs-h3) / var(--lh-h3) var(--font-ui);
    color: var(--text-1);
    padding-left: var(--sp-2);
  }
  .sb-btn {
    display: grid;
    place-items: center;
    width: 40px;
    height: 40px;
    border: 0;
    border-radius: var(--r-3);
    background: transparent;
    color: var(--text-3);
    cursor: pointer;
    transition:
      background-color var(--dur-base) var(--ease-std),
      color var(--dur-base) var(--ease-std);
  }
  .sb-btn:hover { background: var(--surf-2); color: var(--text-1); }
  .sb-collapse { margin-left: auto; }
  .collapsed .sb-collapse { margin-left: 0; }
  .sb-collapse-icon {
    display: grid;
    place-items: center;
    transition: transform var(--dur-base) var(--ease-std);
    transform: rotate(180deg);
  }
  .collapsed .sb-collapse-icon { transform: rotate(0deg); }
  @media (max-width: 1023px) {
    .sb-btn { width: var(--touch); height: var(--touch); }
  }

  .sb-scroll {
    flex: 1 1 auto;
    min-height: 0;
    overflow-y: auto;
    overflow-x: hidden;
    padding: var(--sp-3) var(--sp-2);
    display: flex;
    flex-direction: column;
    gap: var(--sp-2);
    scrollbar-width: thin;
  }
  .group { display: flex; flex-direction: column; }
  .group-label {
    margin: 0;
    padding: var(--sp-3) var(--sp-3) var(--sp-1);
    white-space: nowrap;
    transition: opacity var(--dur-base) var(--ease-std);
  }
  .collapsed .group-label {
    height: 1px;
    padding: 0;
    margin: var(--sp-2) var(--sp-2);
    overflow: hidden;
    color: transparent;
    background: var(--border-1);
    font-size: 0;
    line-height: 0;
  }
  .items { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; }
  .item {
    position: relative;
    display: flex;
    align-items: center;
    gap: var(--sp-3);
    min-height: 36px;
    padding: 0 var(--sp-3);
    border-radius: var(--r-3);
    color: var(--text-2);
    text-decoration: none;
    font: 500 var(--fs-body) / var(--lh-body) var(--font-ui);
    white-space: nowrap;
    transition:
      background-color var(--dur-base) var(--ease-std),
      color var(--dur-base) var(--ease-std);
  }
  .item:hover { background: var(--surf-2); color: var(--text-1); }
  .item.active {
    background: var(--surf-2);
    color: var(--text-1);
  }
  .item.active::before {
    content: '';
    position: absolute;
    left: 0;
    top: 8px;
    bottom: 8px;
    width: 2px;
    border-radius: 1px;
    background: var(--accent);
  }
  .item.active .item-icon { color: var(--accent-text); }
  .item.disabled { color: var(--text-disabled); cursor: default; }
  .item-icon {
    display: grid;
    place-items: center;
    width: 24px;
    height: 24px;
    flex: none;
    color: var(--text-3);
    transition: color var(--dur-base) var(--ease-std);
  }
  .item:hover .item-icon { color: var(--text-1); }
  .item-label {
    flex: 1 1 auto;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .item-phase {
    flex: none;
    min-width: 18px;
    height: 18px;
    display: grid;
    place-items: center;
    border-radius: var(--r-1);
    border: 1px dashed var(--border-2);
    color: var(--text-3);
    font: 500 10px / 1 var(--font-mono);
  }
  .collapsed .item { justify-content: center; padding: 0; min-height: 40px; }
  .collapsed .item-label,
  .collapsed .item-phase { display: none; }
  .collapsed .item.active::before { top: 10px; bottom: 10px; }
  @media (max-width: 1023px) {
    .item { min-height: var(--touch); }
  }

  .sb-foot {
    flex: none;
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: var(--sp-3) var(--sp-4);
    border-top: 1px solid var(--border-1);
    color: var(--text-3);
    font: var(--fs-label) / var(--lh-label) var(--font-ui);
    letter-spacing: var(--ls-label);
    text-transform: uppercase;
    white-space: nowrap;
    overflow: hidden;
  }
  .collapsed .sb-foot { display: none; }
</style>
