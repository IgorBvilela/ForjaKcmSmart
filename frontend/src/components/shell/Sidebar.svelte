<script lang="ts">
  /** Navegação em 7 grupos. Recolhida (rail de 64 px) mostra só ícones: o nome continua acessível
   *  (rótulo visualmente oculto) e aparece como tooltip no mouse e no foco. Sem hover (toque),
   *  o toque num ícone expande o rail em vez de navegar às cegas. O único botão de recolher/expandir
   *  é o do header. */
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

  /** Tooltip do rail: um só elemento, posicionado em `fixed` para escapar do overflow do rail. */
  let tip = $state<{ text: string; top: number } | null>(null)

  function tipText(item: NavItem): string {
    return item.phase ? `${item.label} · disponível na fase ${item.phase}` : item.label
  }
  function showTip(e: Event, text: string): void {
    if (!collapsed) return
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect()
    tip = { text, top: r.top + r.height / 2 }
  }
  function hideTip(): void {
    tip = null
  }
  /** Toque no rail recolhido: expande para mostrar os nomes; a navegação fica para o segundo toque. */
  function onItemClick(e: MouseEvent): void {
    if (collapsed && app.noHover) {
      e.preventDefault()
      hideTip()
      app.toggleSidebar()
    }
  }

  $effect(() => {
    if (!collapsed) tip = null
  })
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
    {:else if !collapsed}
      <span class="sb-caption label">Navegação</span>
    {/if}
  </div>

  <div class="sb-scroll" onscroll={hideTip}>
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
                  onmouseenter={(e) => showTip(e, tipText(item))}
                  onmouseleave={hideTip}
                  onfocus={(e) => showTip(e, tipText(item))}
                  onblur={hideTip}
                  onclick={onItemClick}
                >
                  <span class="item-icon" aria-hidden="true">
                    <item.icon size={18} strokeWidth={1.75} />
                  </span>
                  <span class="item-label">{item.label}</span>
                  {#if item.phase}
                    <span
                      class="item-phase"
                      role="img"
                      aria-label={`Disponível na fase ${item.phase}`}
                      title={`Disponível na fase ${item.phase}`}
                    ></span>
                  {/if}
                </a>
              {:else}
                <span
                  class="item disabled"
                  aria-disabled="true"
                  title={collapsed ? `${item.label} · selecione um equipamento` : 'Selecione um equipamento'}
                >
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

  {#if collapsed && tip}
    <span class="rail-tip" aria-hidden="true" data-testid="sidebar-tooltip" style:top={`${tip.top}px`}>{tip.text}</span>
  {/if}
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
    padding: 0 var(--sp-3) 0 var(--sp-4);
    border-bottom: 1px solid var(--border-1);
    flex: none;
  }
  .collapsed .sb-top { justify-content: center; padding: 0; }
  .sb-title {
    font: 600 var(--fs-h3) / var(--lh-h3) var(--font-ui);
    color: var(--text-1);
  }
  .sb-caption { white-space: nowrap; }
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
  @media (max-width: 1023px), (pointer: coarse) {
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
  /* recolhido: o título do grupo vira um separador visível (o texto segue no DOM para leitor de tela) */
  .collapsed .group-label {
    height: 1px;
    padding: 0;
    margin: var(--sp-2) var(--sp-3);
    overflow: hidden;
    color: transparent;
    background: var(--border-2);
    font-size: 0;
    line-height: 0;
  }
  .collapsed .group:first-child .group-label { display: none; }
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
  /* tela que ainda depende de fase posterior: ponto discreto, não chip */
  .item-phase {
    flex: none;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--chumbo);
  }
  .collapsed .item { justify-content: center; padding: 0; min-height: 40px; }
  /* nome continua no DOM (nome acessível do link), só sai da tela */
  .collapsed .item-label {
    position: absolute;
    width: 1px;
    height: 1px;
    margin: -1px;
    padding: 0;
    overflow: hidden;
    clip: rect(0 0 0 0);
    clip-path: inset(50%);
    white-space: nowrap;
  }
  .collapsed .item-phase { display: none; }
  .collapsed .item.active::before { top: 9px; bottom: 9px; width: 3px; }
  @media (max-width: 1023px), (pointer: coarse) {
    .item { min-height: var(--touch); }
    .collapsed .item { min-height: var(--touch); }
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

  /* ---- tooltip do rail ---- */
  .rail-tip {
    position: fixed;
    left: calc(var(--sidebar-w-collapsed) + var(--sp-2));
    z-index: 40;
    padding: var(--sp-1) var(--sp-3);
    border: 1px solid var(--border-2);
    border-radius: var(--r-2);
    background: var(--surf-3);
    box-shadow: var(--elev-2);
    color: var(--text-1);
    font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui);
    white-space: nowrap;
    pointer-events: none;
    transform: translateY(-50%);
    animation: tip-in var(--dur-micro) var(--ease-out) both;
  }
  .rail-tip::before {
    content: '';
    position: absolute;
    left: -5px;
    top: 50%;
    width: 8px;
    height: 8px;
    background: var(--surf-3);
    border-left: 1px solid var(--border-2);
    border-bottom: 1px solid var(--border-2);
    transform: translateY(-50%) rotate(45deg);
  }
  @keyframes tip-in {
    from { opacity: 0; transform: translate(-4px, -50%); }
    to { opacity: 1; transform: translateY(-50%); }
  }
</style>
