<script lang="ts">
  /** Menu principal: Agora, Planta, Dashboard e Comunicação, com a engrenagem (Mais) no pé.
   *  Desktop: trilho fixo com ícone grande e o nome embaixo; o indicador da entrada ativa desliza
   *  com mola. Celular e tablet: as mesmas entradas em linhas, dentro do drawer. */
  import X from '@lucide/svelte/icons/x'
  import { MAIN_MENU, MORE_ITEM, menuSlugFor, type NavItem } from '../../lib/nav'
  import { live } from '../../lib/live.svelte'
  import { href } from '../../lib/router'
  import { situation } from '../../lib/situationStore.svelte'
  import { app } from '../../lib/state.svelte'
  import { TID } from '../../lib/testids'

  let { mode = 'rail' }: { mode?: 'rail' | 'drawer' } = $props()

  const activeSlug = $derived(menuSlugFor(app.route))
  /** Links por equipamento: o da rota ou o último visto; senão o primeiro perfil real. */
  const eqId = $derived(live.linkEquipmentId(app.equipmentId))
  const attention = $derived(situation.attention)

  let refs: Record<string, HTMLElement | undefined> = $state({})
  let height = $state(0)
  let marker = $state<{ y: number; h: number } | null>(null)

  $effect(() => {
    void height
    const el = refs[activeSlug]
    marker = el ? { y: el.offsetTop, h: el.offsetHeight } : null
  })
</script>

{#snippet entry(item: NavItem)}
  {@const target = item.to(eqId)}
  {@const active = item.slug === activeSlug}
  <li>
    {#if target}
      <a
        bind:this={refs[item.slug]}
        class="item"
        class:active
        href={target}
        aria-current={active ? 'page' : undefined}
        data-testid={TID.sidebar.link(item.slug)}
      >
        <span class="item-icon" aria-hidden="true">
          <item.icon size={mode === 'rail' ? 24 : 20} strokeWidth={1.75} />
          {#if mode === 'rail' && item.slug === 'now' && attention > 0}
            <span class="count num" data-testid="menu-attention-count">{attention}</span>
          {/if}
        </span>
        <span class="item-label">{item.label}</span>
        {#if mode === 'drawer' && item.slug === 'now' && attention > 0}
          <!-- na lista do drawer o número vai para o fim da linha -->
          <span class="count end num" aria-hidden="true" data-testid="menu-attention-count">{attention}</span>
        {/if}
        {#if item.slug === 'now' && attention > 0}
          <span class="sr">, {attention} {attention === 1 ? 'dosador' : 'dosadores'} em atenção</span>
        {/if}
      </a>
    {:else}
      <span class="item disabled" aria-disabled="true" title="Selecione um equipamento">
        <span class="item-icon" aria-hidden="true"><item.icon size={mode === 'rail' ? 24 : 20} strokeWidth={1.75} /></span>
        <span class="item-label">{item.label}</span>
      </span>
    {/if}
  </li>
{/snippet}

<nav
  class="sb"
  data-mode={mode}
  data-testid={TID.sidebar.root}
  aria-label="Navegação principal"
  bind:clientHeight={height}
>
  {#if mode === 'drawer'}
    <div class="sb-top">
      <!-- no celular a marca sai do header (dá lugar ao seletor) e mora aqui -->
      <a class="sb-brand" href={href.now()} aria-label="Forja KCM Intelligence, ir para a tela Agora">
        <svg viewBox="0 0 32 32" width="28" height="28" aria-hidden="true">
          <rect width="32" height="32" rx="7" fill="var(--accent)" />
          <rect x="8" y="7" width="3.2" height="18" fill="var(--on-accent)" />
          <rect x="8" y="7" width="10" height="3" fill="var(--on-accent)" />
          <rect x="8" y="14" width="7.5" height="3" fill="var(--on-accent)" />
          <rect x="20.5" y="7" width="3.2" height="18" fill="var(--on-accent)" />
          <rect x="20.5" y="22" width="4.5" height="3" fill="var(--on-accent)" />
        </svg>
        <span class="sb-title">FORJA <strong>KCM</strong></span>
      </a>
      <button
        type="button"
        class="sb-btn"
        aria-label="Fechar menu"
        data-testid={TID.sidebar.toggle}
        onclick={() => app.closeDrawer()}
      >
        <X size={20} aria-hidden="true" />
      </button>
    </div>
  {/if}

  <ul class="items">
    {#each MAIN_MENU as item (item.slug)}
      {@render entry(item)}
    {/each}
  </ul>
  <ul class="items foot">
    {@render entry(MORE_ITEM)}
  </ul>

  {#if mode === 'rail' && marker}
    <span class="marker" aria-hidden="true" style:transform={`translateY(${marker.y}px)`} style:height={`${marker.h}px`}></span>
  {/if}

  {#if mode === 'drawer'}
    <div class="sb-foot">
      <span>Edge local · 127.0.0.1</span>
      <span>Observa. Não comanda.</span>
    </div>
  {/if}
</nav>

<style>
  .sb {
    position: relative;
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    padding-bottom: var(--sp-2);
    background: var(--surf-1);
    border-right: 1px solid var(--border-1);
    color: var(--text-2);
    overflow-x: hidden;
    overflow-y: auto;
  }
  .sb[data-mode='drawer'] { border-right: 0; padding-bottom: 0; }

  .sb-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: var(--header-h);
    padding: 0 var(--sp-3) 0 var(--sp-4);
    border-bottom: 1px solid var(--border-1);
    flex: none;
  }
  .sb-brand {
    display: inline-flex;
    align-items: center;
    gap: var(--sp-3);
    min-height: var(--touch);
    padding-right: var(--sp-2);
    color: inherit;
    text-decoration: none;
    border-radius: var(--r-2);
  }
  .sb-title { font: 600 15px / 16px var(--font-ui); letter-spacing: 0.02em; color: var(--text-1); }
  .sb-title strong { color: var(--accent-text); font-weight: 600; }
  .sb-btn {
    display: grid;
    place-items: center;
    width: var(--touch);
    height: var(--touch);
    border: 0;
    border-radius: var(--r-3);
    background: transparent;
    color: var(--text-3);
    cursor: pointer;
    transition: background-color var(--dur-base) var(--ease-std), color var(--dur-base) var(--ease-std);
  }
  .sb-btn:hover { background: var(--surf-2); color: var(--text-1); }

  .items { display: flex; flex-direction: column; gap: var(--sp-1); margin: 0; padding: var(--sp-2); list-style: none; }
  .foot { margin-top: auto; padding-top: var(--sp-3); border-top: 1px solid var(--border-1); }

  .item {
    position: relative;
    display: flex;
    align-items: center;
    gap: var(--sp-3);
    min-height: 48px;
    padding: 0 var(--sp-3);
    border-radius: var(--r-3);
    color: var(--text-2);
    font: 500 var(--fs-body-lg) / 1.2 var(--font-ui);
    text-decoration: none;
    transition: background-color var(--dur-base) var(--ease-std), color var(--dur-base) var(--ease-std);
  }
  .item:hover { background: var(--surf-2); color: var(--text-1); }
  .item.active { background: var(--surf-2); color: var(--text-1); }
  .item.disabled { color: var(--text-disabled); cursor: default; }
  .item-icon { position: relative; display: grid; place-items: center; flex: none; color: var(--text-3); transition: color var(--dur-base) var(--ease-std); }
  .item:hover .item-icon { color: var(--text-1); }
  .item.active .item-icon { color: var(--accent-text); }
  .item-label { min-width: 0; }
  .count {
    position: absolute;
    top: -8px;
    right: -12px;
    display: grid;
    place-items: center;
    min-width: 20px;
    height: 20px;
    padding: 0 5px;
    border-radius: var(--r-pill);
    background: var(--st-warn);
    color: var(--on-accent);
    font: 600 13px / 1 var(--font-mono);
    box-shadow: 0 0 0 2px var(--surf-1);
    animation: count-in 420ms var(--ease-out);
  }
  .count.end { position: static; margin-left: auto; box-shadow: none; }
  @keyframes count-in {
    0% { transform: scale(0.4); opacity: 0; }
    60% { transform: scale(1.15); opacity: 1; }
    100% { transform: scale(1); }
  }
  .sr {
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

  /* trilho do desktop: ícone em cima, nome embaixo */
  .sb[data-mode='rail'] .item {
    flex-direction: column;
    justify-content: center;
    gap: var(--sp-1);
    min-height: 72px;
    padding: var(--sp-2) var(--sp-1);
    font: 500 13px / 16px var(--font-ui);
    text-align: center;
  }
  .sb[data-mode='rail'] .item.active { background: transparent; }
  .sb[data-mode='rail'] .item.active:hover { background: var(--surf-2); }
  .marker {
    position: absolute;
    top: 0;
    left: 0;
    width: 3px;
    border-radius: 0 3px 3px 0;
    background: var(--accent);
    pointer-events: none;
    transition: transform var(--dur-spring) var(--ease-spring), height var(--dur-spring) var(--ease-spring);
  }

  /* drawer: barra cobre na entrada ativa */
  .sb[data-mode='drawer'] .item.active::before {
    content: '';
    position: absolute;
    left: 0;
    top: 10px;
    bottom: 10px;
    width: 3px;
    border-radius: 2px;
    background: var(--accent);
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
  }
</style>
