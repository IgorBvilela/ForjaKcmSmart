<script lang="ts">
  /** Nível de evidência traduzido + força (1 a 7) visível como barras. Nunca é cor de status. */
  import { EVIDENCE_PT, EVIDENCE_STRENGTH, type EvidenceLevel } from '../../lib/api'

  let { level, compact = false }: { level: EvidenceLevel; compact?: boolean } = $props()

  const text = $derived(EVIDENCE_PT[level] ?? level)
  const strength = $derived(EVIDENCE_STRENGTH[level] ?? 1)
  const bars = $derived(Math.max(1, Math.min(3, Math.ceil(strength / 2.4))))
</script>

<span
  class="ev"
  class:compact
  data-level={level}
  data-strength={strength}
  title={`Nível de evidência: ${text} (${strength} de 7)`}
>
  <span class="bars" aria-hidden="true">
    <i class:on={bars >= 1}></i><i class:on={bars >= 2}></i><i class:on={bars >= 3}></i>
  </span>
  <span class="txt">{text}</span>
</span>

<style>
  .ev {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 2px 8px;
    border-radius: var(--r-pill);
    border: 1px solid var(--border-2);
    color: var(--text-2);
    font: 500 var(--fs-label) / var(--lh-label) var(--font-ui);
    letter-spacing: var(--ls-label);
    text-transform: uppercase;
    white-space: nowrap;
  }
  .ev[data-level='HYPOTHESIS'] {
    border-style: dashed;
    color: var(--text-3);
  }
  .ev[data-strength='7'],
  .ev[data-strength='6'],
  .ev[data-strength='5'] {
    color: var(--text-1);
    border-color: var(--text-3);
  }
  .bars {
    display: inline-flex;
    gap: 2px;
    align-items: flex-end;
    height: 10px;
  }
  .bars i {
    display: block;
    width: 3px;
    background: var(--border-2);
    border-radius: 1px;
  }
  .bars i:nth-child(1) { height: 4px; }
  .bars i:nth-child(2) { height: 7px; }
  .bars i:nth-child(3) { height: 10px; }
  .bars i.on { background: currentColor; }
  .compact .txt { display: none; }
</style>
