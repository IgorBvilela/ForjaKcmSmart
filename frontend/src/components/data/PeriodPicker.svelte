<script lang="ts">
  /** Período da consulta: atalhos (terminam agora) ou intervalo de/até no horário da planta. */
  import { PRESETS, fromLocalInput, resolvePeriod, toLocalInput, type Period } from '../../lib/period'

  let {
    period,
    now,
    onchange,
    testid = 'period',
  }: { period: Period; now: number; onchange: (p: Period) => void; testid?: string } = $props()

  const range = $derived(resolvePeriod(period, now))
  let fromText = $state('')
  let toText = $state('')
  let error = $state<string | null>(null)
  const uid = $props.id()

  $effect(() => {
    fromText = toLocalInput(range.from)
    toText = toLocalInput(range.to)
  })

  function applyCustom(): void {
    const a = fromLocalInput(fromText)
    const b = fromLocalInput(toText)
    if (a == null || b == null) {
      error = 'Informe data e hora completas.'
      return
    }
    if (b <= a) {
      error = 'O fim precisa ser depois do início.'
      return
    }
    if (b - a > 366 * 86_400_000) {
      error = 'Período máximo de 366 dias.'
      return
    }
    error = null
    onchange({ kind: 'custom', from: a, to: b })
  }
</script>

<div class="period" data-testid={testid}>
  <div class="presets" role="group" aria-label="Período">
    {#each PRESETS as p (p.id)}
      <button
        type="button"
        class="chip"
        aria-pressed={period.kind === 'preset' && period.preset === p.id}
        data-testid={`${testid}-preset-${p.id}`}
        onclick={() => onchange({ kind: 'preset', preset: p.id })}
      >
        {p.label}
      </button>
    {/each}
  </div>
  <form
    class="custom"
    onsubmit={(e) => {
      e.preventDefault()
      applyCustom()
    }}
  >
    <label for={`${uid}-from`}>De</label>
    <input id={`${uid}-from`} type="datetime-local" bind:value={fromText} data-testid={`${testid}-from`} />
    <label for={`${uid}-to`}>Até</label>
    <input id={`${uid}-to`} type="datetime-local" bind:value={toText} data-testid={`${testid}-to`} />
    <button type="submit" class="apply" data-testid={`${testid}-apply`}>Aplicar</button>
    {#if error}<p class="err" role="alert">{error}</p>{/if}
  </form>
</div>

<style>
  .period {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--sp-3) var(--sp-4);
    min-width: 0;
  }
  .presets { display: flex; flex-wrap: wrap; gap: var(--sp-2); }
  .chip {
    min-height: var(--touch);
    min-width: var(--touch);
    padding: 0 var(--sp-3);
    border: 1px solid var(--border-2);
    border-radius: var(--r-pill);
    background: var(--surf-1);
    color: var(--text-2);
    font: 500 var(--fs-body) / 1 var(--font-ui);
    cursor: pointer;
    transition: background var(--dur-micro) var(--ease-out), color var(--dur-micro) var(--ease-out),
      border-color var(--dur-micro) var(--ease-out);
  }
  .chip:hover { border-color: var(--border-input); color: var(--text-1); }
  .chip[aria-pressed='true'] {
    background: var(--accent-soft);
    border-color: var(--accent);
    color: var(--accent-text);
  }
  .custom {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--sp-2);
    min-width: 0;
  }
  .custom label { color: var(--text-3); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .custom input {
    min-height: var(--touch);
    padding: 0 var(--sp-2);
    border: 1px solid var(--border-input);
    border-radius: var(--r-2);
    background: var(--surf-2);
    color: var(--text-1);
    font: 16px / 1 var(--font-mono);
    color-scheme: inherit;
    max-width: 100%;
  }
  .apply {
    min-height: var(--touch);
    padding: 0 var(--sp-4);
    border: 1px solid var(--accent);
    border-radius: var(--r-3);
    background: var(--accent);
    color: var(--on-accent);
    font: 600 var(--fs-body) / 1 var(--font-ui);
    cursor: pointer;
  }
  .err {
    flex-basis: 100%;
    margin: 0;
    color: var(--st-crit);
    font: var(--fs-caption) / var(--lh-caption) var(--font-ui);
  }
  @media (max-width: 767px) {
    .custom { width: 100%; }
    .custom input { flex: 1 1 100%; }
    .apply { flex: 1 1 100%; }
  }
</style>
