<script lang="ts">
  /** Seleção de variáveis por rótulo em português. O código da tag fica no title (detalhe técnico).
   *  `collapsible`: no celular a lista vira um botão que abre e fecha (a tela não some em chips). */
  import Check from '@lucide/svelte/icons/check'
  import ChevronDown from '@lucide/svelte/icons/chevron-down'
  import type { TagMeta } from '../../lib/api'

  let {
    available,
    selected,
    max = 8,
    collapsible = false,
    onchange,
    testid = 'tags',
  }: {
    available: TagMeta[]
    selected: string[]
    max?: number
    collapsible?: boolean
    onchange: (tags: string[]) => void
    testid?: string
  } = $props()

  let open = $state(false)
  const listId = $props.id()
  const summary = $derived(
    available
      .filter((t) => selected.includes(t.code))
      .map((t) => t.label_pt)
      .join(', '),
  )

  function toggle(code: string): void {
    if (selected.includes(code)) {
      if (selected.length > 1) onchange(selected.filter((t) => t !== code))
    } else if (selected.length < max) {
      onchange([...selected, code])
    }
  }
</script>

<div class="picker" data-testid={testid}>
  {#if collapsible}
    <button
      type="button"
      class="summary"
      aria-expanded={open}
      aria-controls={listId}
      data-testid={`${testid}-toggle`}
      onclick={() => (open = !open)}
    >
      <span class="sum-text">
        <span class="sum-label">Variáveis ({selected.length} de {max})</span>
        <span class="sum-names">{summary}</span>
      </span>
      <span class="chev" class:open aria-hidden="true"><ChevronDown size={18} /></span>
    </button>
  {/if}
  {#if !collapsible || open}
    <fieldset class="tags" id={listId}>
      <legend class="sr">Variáveis exibidas</legend>
      {#each available as t (t.code)}
        {@const on = selected.includes(t.code)}
        <label
          class="tag"
          class:on
          class:off={!on && selected.length >= max}
          title={`${t.explanation_pt} (${t.code})`}
          data-testid={`${testid}-${t.code}`}
        >
          <input
            type="checkbox"
            class="sr"
            checked={on}
            disabled={!on && selected.length >= max}
            onchange={() => toggle(t.code)}
          />
          <span class="tick" aria-hidden="true">{#if on}<Check size={14} strokeWidth={2.5} />{/if}</span>
          {t.label_pt}
        </label>
      {/each}
    </fieldset>
  {/if}
</div>

<style>
  .picker { display: flex; flex-direction: column; gap: var(--sp-2); min-width: 0; }
  .summary {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--sp-3);
    width: 100%;
    min-height: var(--touch);
    padding: var(--sp-2) var(--sp-3);
    border: 1px solid var(--border-input);
    border-radius: var(--r-3);
    background: var(--surf-2);
    color: var(--text-1);
    text-align: left;
    cursor: pointer;
  }
  .sum-text { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .sum-label { font: 600 var(--fs-body) / var(--lh-body) var(--font-ui); }
  .sum-names { color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); overflow-wrap: anywhere; }
  .chev { display: inline-grid; transition: transform var(--dur-base) var(--ease-out); color: var(--text-2); }
  .chev.open { transform: rotate(180deg); }
  .tags { display: flex; flex-wrap: wrap; gap: var(--sp-2); min-width: 0; margin: 0; padding: 0; border: 0; }
  .sr {
    position: absolute;
    width: 1px;
    height: 1px;
    margin: -1px;
    padding: 0;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
    border: 0;
  }
  .tag {
    position: relative;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-height: var(--touch);
    padding: 0 var(--sp-3);
    border: 1px solid var(--border-2);
    border-radius: var(--r-pill);
    background: var(--surf-1);
    color: var(--text-2);
    font: 500 var(--fs-body) / 1 var(--font-ui);
    cursor: pointer;
    user-select: none;
    transition: background var(--dur-micro) var(--ease-out), border-color var(--dur-micro) var(--ease-out),
      transform var(--dur-micro) var(--ease-out);
  }
  .tag:hover:not(.off) { border-color: var(--border-input); color: var(--text-1); }
  .tag:active:not(.off) { transform: scale(0.97); }
  .tag:has(input:focus-visible) { box-shadow: var(--focus); }
  .tag.on {
    border-color: var(--accent);
    background: var(--accent-soft);
    color: var(--text-1);
  }
  .tag.off { opacity: 0.5; cursor: not-allowed; }
  .tick {
    display: inline-grid;
    place-items: center;
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid var(--border-input);
    color: var(--accent-text);
  }
  .tag.on .tick { border-color: var(--accent); }
</style>
