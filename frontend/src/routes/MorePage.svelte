<script lang="ts">
  /** Mais (engrenagem): as telas que saíram do menu, em grupos de atalhos.
   *  As do dosador abrem no equipamento selecionado; sem equipamento, ficam indisponíveis
   *  (enquanto a lista da planta não chega, sem aviso: ainda não se sabe se há equipamento). */
  import { GEAR_GROUPS } from '../lib/nav'
  import { live } from '../lib/live.svelte'
  import { shortcuts } from '../lib/shortcuts.svelte'
  import { app } from '../lib/state.svelte'
  import { TID } from '../lib/testids'

  const eqId = $derived(live.linkEquipmentId(app.equipmentId))
  const eqName = $derived(live.cardOf(eqId)?.name ?? eqId)
  /** O nome do equipamento aparece uma vez, no primeiro grupo que depende dele. */
  const eqGroupId = GEAR_GROUPS.find((g) => g.items.some((i) => i.kind === 'eq'))?.id
</script>

<section class="more" data-testid={TID.more.root} aria-labelledby="more-title">
  <header class="more-head">
    <h1 id="more-title">Mais</h1>
    <p class="lead">Ficha do dosador, relatórios, exportações e ajustes do sistema.</p>
  </header>

  {#each GEAR_GROUPS as group, gi (group.id)}
    <section class="group" style:--i={gi} aria-labelledby={`more-group-${group.id}`}>
      <h2 class="label" id={`more-group-${group.id}`}>
        {group.label}
        {#if group.id === eqGroupId && eqName}
          <span class="eq" data-testid={TID.more.equipment}>· {eqName}</span>
        {/if}
      </h2>
      {#if group.id === eqGroupId && !eqId && live.plantLoaded}
        <p class="hint">Nenhum equipamento configurado.</p>
      {/if}
      <ul class="tiles">
        {#each group.items as item (item.slug)}
          {@const target = item.to(eqId)}
          <li>
            {#if target}
              <a class="tile" href={target} data-testid={TID.more.link(item.slug)}>
                <span class="tile-icon" aria-hidden="true"><item.icon size={20} strokeWidth={1.75} /></span>
                <span class="tile-label">{item.label}</span>
              </a>
            {:else}
              <span class="tile disabled" aria-disabled="true" data-testid={TID.more.link(item.slug)}>
                <span class="tile-icon" aria-hidden="true"><item.icon size={20} strokeWidth={1.75} /></span>
                <span class="tile-label">{item.label}</span>
              </span>
            {/if}
          </li>
        {/each}
      </ul>
    </section>
  {/each}

  <section class="group" style:--i={GEAR_GROUPS.length} aria-labelledby="more-group-teclado">
    <h2 class="label" id="more-group-teclado">Teclado</h2>
    <label class="choice">
      <input type="checkbox" checked={shortcuts.enabled} onchange={(e) => shortcuts.set(e.currentTarget.checked)} />
      <span class="choice-mark" data-kind="check" aria-hidden="true"></span>
      Atalhos de teclado: 1 Agora, 2 Planta, 3 Dashboard, 4 Comunicação
    </label>
  </section>

  <p class="foot"><span>Edge local · 127.0.0.1</span><span>Observa. Não comanda.</span></p>
</section>

<style>
  .more { display: flex; flex-direction: column; gap: var(--sp-6); max-width: 1120px; }
  .more-head { display: flex; flex-direction: column; gap: var(--sp-1); }
  h1 { margin: 0; color: var(--text-1); font: 600 var(--fs-h1) / var(--lh-h1) var(--font-ui); }
  .lead { margin: 0; color: var(--text-2); font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  .group {
    display: flex;
    flex-direction: column;
    gap: var(--sp-2);
    animation: rise var(--dur-screen) var(--ease-out) both;
    animation-delay: calc(var(--i) * var(--stagger));
  }
  .group .label { margin: 0; }
  .eq { color: var(--text-2); text-transform: none; letter-spacing: 0; }
  .hint { margin: 0; color: var(--text-2); font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  .tiles {
    display: grid;
    gap: var(--sp-2);
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .tile {
    display: flex;
    align-items: center;
    gap: var(--sp-3);
    min-height: 56px;
    height: 100%;
    padding: var(--sp-2) var(--sp-4);
    border: 1px solid var(--border-1);
    border-radius: var(--r-3);
    background: var(--surf-1);
    color: var(--text-1);
    font: 500 var(--fs-body) / var(--lh-body) var(--font-ui);
    text-decoration: none;
    transition:
      background-color var(--dur-base) var(--ease-std),
      border-color var(--dur-base) var(--ease-std),
      transform var(--dur-base) var(--ease-out);
  }
  .tile-icon { display: grid; place-items: center; flex: none; color: var(--text-3); transition: color var(--dur-base) var(--ease-std); }
  .tile-label { min-width: 0; overflow-wrap: break-word; }
  a.tile:hover { border-color: var(--border-2); background: var(--surf-2); transform: translateY(-1px); }
  a.tile:hover .tile-icon { color: var(--accent-text); }
  a.tile:active { transform: none; }
  .tile.disabled { color: var(--text-disabled); cursor: default; }
  .tile.disabled .tile-icon { color: var(--text-disabled); }
  .foot {
    display: flex;
    flex-wrap: wrap;
    gap: var(--sp-1) var(--sp-4);
    margin: 0;
    color: var(--text-3);
    font: var(--fs-label) / var(--lh-label) var(--font-ui);
    letter-spacing: var(--ls-label);
    text-transform: uppercase;
  }
  @keyframes rise {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: none; }
  }
  @media (min-width: 1024px) {
    h1 { font-size: var(--fs-display); line-height: var(--lh-display); }
  }
  @media (prefers-reduced-motion: reduce) {
    a.tile:hover { transform: none; }
  }
</style>
