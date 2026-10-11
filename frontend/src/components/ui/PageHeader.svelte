<script lang="ts">
  /** Cabeçalho padrão de tela: rótulo (equipamento ou grupo), título curto, no máximo uma frase
   *  de apoio (até ~100 caracteres) e, quando há explicação longa, "Saiba mais" fechado.
   *  As ações da tela (exportar, imprimir) ficam à direita. */
  import type { Snippet } from 'svelte'
  import Disclosure from './Disclosure.svelte'

  let {
    kicker,
    title,
    lead,
    more,
    actions,
    noPrint = false,
  }: {
    kicker?: string
    title: string
    lead?: string
    more?: Snippet
    actions?: Snippet
    noPrint?: boolean
  } = $props()
</script>

<header class="ph" class:no-print={noPrint} data-testid="page-head">
  <div class="ph-text">
    {#if kicker}<p class="label">{kicker}</p>{/if}
    <h1 class="ph-title">{title}</h1>
    {#if lead}<p class="ph-lead" data-testid="page-lead">{lead}</p>{/if}
    {#if more}
      <div class="ph-more">
        <Disclosure summary="Saiba mais" size="sm" testid="page-more">
          <div class="ph-more-body">{@render more()}</div>
        </Disclosure>
      </div>
    {/if}
  </div>
  {#if actions}<div class="ph-actions">{@render actions()}</div>{/if}
</header>

<style>
  .ph { display: flex; align-items: flex-end; justify-content: space-between; gap: var(--sp-3) var(--sp-4); flex-wrap: wrap; }
  .ph-text { display: flex; flex-direction: column; gap: var(--sp-1); min-width: 0; max-width: 72ch; }
  .label { margin: 0; }
  .ph-title { margin: 0; color: var(--text-1); font: 600 var(--fs-h1) / var(--lh-h1) var(--font-ui); }
  .ph-lead { margin: 0; color: var(--text-2); font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  .ph-more { margin-left: calc(-1 * var(--sp-1)); }
  .ph-more-body {
    display: flex;
    flex-direction: column;
    gap: var(--sp-2);
    padding: var(--sp-1) 0 0 var(--sp-5);
    color: var(--text-2);
    font: var(--fs-body) / var(--lh-body) var(--font-ui);
  }
  .ph-more-body :global(p) { margin: 0; }
  .ph-actions { display: flex; flex-wrap: wrap; gap: var(--sp-2); }
  @media (min-width: 1024px) {
    .ph-title { font-size: var(--fs-display); line-height: var(--lh-display); }
  }
</style>
