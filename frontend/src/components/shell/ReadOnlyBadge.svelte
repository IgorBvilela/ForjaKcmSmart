<script lang="ts">
  /** Selo permanente. SVG inline (cadeado) + texto; a explicação abre no clique.
   *  `size="sm"` é o chip da área do equipamento; `testid` muda quando há mais de um na tela. */
  import { TID } from '../../lib/testids'
  import Tooltip from '../ui/Tooltip.svelte'

  let {
    compact = false,
    align = 'end',
    size = 'md',
    testid = TID.header.readOnlyBadge,
  }: { compact?: boolean; align?: 'start' | 'end'; size?: 'sm' | 'md'; testid?: string } = $props()

  const iconPx = $derived(size === 'sm' ? 12 : 14)
</script>

<span class="ro" class:compact data-size={size} data-testid={testid} data-state="read-only">
  <Tooltip
    label="Somente leitura: o que isso significa"
    text="Nenhuma rota, comando ou botão desta interface altera o KCM. A Forja só lê, historiza e explica."
    {align}
  >
    <svg class="lock" viewBox="0 0 24 24" width={iconPx} height={iconPx} aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <rect width="18" height="11" x="3" y="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
    <span class="txt">Somente leitura</span>
  </Tooltip>
</span>

<style>
  .ro {
    display: inline-flex;
    align-items: center;
    color: var(--text-2);
    font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui);
    white-space: nowrap;
  }
  .ro :global(.tip-btn) {
    position: relative;
    border: 1px solid var(--border-2);
    border-radius: var(--r-pill);
    padding: 0 var(--sp-3) 0 var(--sp-2);
    min-height: 28px;
    color: var(--text-2);
  }
  .ro :global(.tip-btn:hover) { color: var(--text-1); border-color: var(--text-3); }
  .lock { color: var(--text-2); flex: none; }
  .compact .txt { font-size: var(--fs-label); letter-spacing: var(--ls-label); text-transform: uppercase; }

  .ro[data-size='sm'] :global(.tip-btn) {
    min-height: 22px;
    padding: 0 var(--sp-2) 0 6px;
    gap: 5px;
    line-height: var(--lh-label);
  }
  /* toque e celular: alvo real de 44 px (esta regra vence a do Tooltip por especificidade) */
  @media (max-width: 767px), (pointer: coarse) {
    .ro :global(.tip-btn),
    .ro[data-size='sm'] :global(.tip-btn) { min-height: var(--touch); }
  }
</style>
