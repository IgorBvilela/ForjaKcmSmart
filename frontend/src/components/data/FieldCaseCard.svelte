<script lang="ts">
  /** Caso de campo: o que foi observado, o que foi feito, aprendizado, medições com a natureza e a
   *  evidência de cada uma. Causa só aparece como confirmada com evidência que feche a cadeia. */
  import type { FieldCase } from '../../lib/intelligence'
  import Badge from '../ui/Badge.svelte'
  import Disclosure from '../ui/Disclosure.svelte'

  let { item, other = false }: { item: FieldCase; other?: boolean } = $props()
</script>

<article class="case" data-testid="case-{item.id}" data-confirmed={item.cause_confirmed}>
  <header class="case-head">
    <div class="badges">
      <Badge tone="info">{item.evidence_pt}</Badge>
      <Badge tone={item.cause_confirmed ? 'ok' : 'unknown'} dashed={!item.cause_confirmed}>{item.cause_pt}</Badge>
      {#if other}<Badge tone="ghost">Outro equipamento</Badge>{/if}
    </div>
    <h3 class="case-title">{item.title_pt}</h3>
    <p class="case-meta">{item.equipment} · {item.application} · {item.period_pt}</p>
  </header>
  {#if item.observed_facts_pt.length}
    <div class="block">
      <h4 class="label">O que foi observado</h4>
      <ul>{#each item.observed_facts_pt as f (f)}<li>{f}</li>{/each}</ul>
    </div>
  {/if}
  {#if item.interventions_pt.length}
    <div class="block">
      <h4 class="label">O que foi feito</h4>
      <ul>{#each item.interventions_pt as f (f)}<li>{f}</li>{/each}</ul>
    </div>
  {/if}
  {#if item.learned_rule_pt}
    <blockquote class="learned">
      <span class="label">O que ficou de aprendizado</span>
      <p>{item.learned_rule_pt}</p>
    </blockquote>
  {/if}
  {#if item.measurements.length || item.calibration_reported_pt.length}
    <Disclosure summary="Medições e calibração relatadas" size="sm">
      {#if item.measurements.length}
        <table class="resp">
          <thead><tr><th>O quê</th><th>Valor</th><th>Natureza</th><th>Evidência</th></tr></thead>
          <tbody>
            {#each item.measurements as m (m.what_pt)}
              <tr>
                <th data-label="O quê">{m.what_pt}</th>
                <td data-label="Valor" class="mono">{m.value}</td>
                <td data-label="Natureza">{m.nature_pt}</td>
                <td data-label="Evidência">{m.evidence_pt}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
      {#if item.calibration_reported_pt.length}
        <ul class="calib">{#each item.calibration_reported_pt as f (f)}<li>{f}</li>{/each}</ul>
      {/if}
    </Disclosure>
  {/if}
  {#if item.notes_pt}<p class="small">{item.notes_pt}</p>{/if}
  {#if item.sources.length}
    <p class="small">Fonte: {item.sources.map((s) => s.title).join(' · ')}</p>
  {/if}
</article>

<style>
  .case {
    display: flex;
    flex-direction: column;
    gap: var(--sp-3);
    padding: var(--sp-4);
    border: 1px solid var(--border-1);
    border-radius: var(--r-3);
    background: var(--surf-2);
    min-width: 0;
    animation: rise var(--dur-screen) var(--ease-out) backwards;
  }
  @keyframes rise {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: none; }
  }
  .case-head { display: flex; flex-direction: column; gap: var(--sp-1); }
  .badges { display: flex; flex-wrap: wrap; gap: var(--sp-2); }
  .case-title { margin: var(--sp-1) 0 0; color: var(--text-1); font: 600 var(--fs-h3) / var(--lh-h3) var(--font-ui); }
  .case-meta { margin: 0; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .block h4 { margin: 0 0 var(--sp-1); }
  .block ul, .calib { margin: 0; padding-left: var(--sp-5); color: var(--text-1); font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  .block li + li, .calib li + li { margin-top: 2px; }
  .learned {
    margin: 0;
    padding: var(--sp-3) var(--sp-4);
    border-left: 3px solid var(--accent);
    border-radius: 0 var(--r-3) var(--r-3) 0;
    background: var(--accent-soft);
  }
  .learned p { margin: var(--sp-1) 0 0; color: var(--text-1); font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  table { width: 100%; border-collapse: collapse; margin-top: var(--sp-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  th, td { padding: var(--sp-2); border-bottom: 1px solid var(--border-1); text-align: left; vertical-align: top; color: var(--text-1); }
  thead th { color: var(--text-2); font-weight: 500; }
  .mono { font-family: var(--font-mono); }
  .calib { margin-top: var(--sp-3); }
  .small { margin: 0; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); max-width: 90ch; }
</style>
