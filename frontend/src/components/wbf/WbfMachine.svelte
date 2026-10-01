<script lang="ts">
  // STUB do dosador animado (bloco D substitui este arquivo mantendo as props abaixo).
  // Props: ver docs/contracts/CONTRATOS_B.md, seção "Bloco D".
  export type MachineState = 0 | 1 | 2 | null
  export type Quality = 'GOOD' | 'SIMULATED' | 'UNCERTAIN' | 'STALE' | 'COMM_ERROR' | 'BAD'

  let {
    rpm = null,
    beltLoad = null,
    driveCommand = null,
    massFlow = null,
    machineState = null,
    quality = 'SIMULATED',
    connection = 'CONNECTED',
    rpmRef = null,
    beltLoadRef = null,
    scenario = undefined,
    reducedMotion = false,
  }: {
    rpm?: number | null
    beltLoad?: number | null
    driveCommand?: number | null
    massFlow?: number | null
    machineState?: MachineState
    quality?: Quality
    connection?: string
    rpmRef?: number | null
    beltLoadRef?: number | null
    scenario?: string
    reducedMotion?: boolean
  } = $props()

  const level = $derived(
    beltLoad == null || beltLoadRef == null || beltLoadRef === 0
      ? 0
      : Math.max(0, Math.min(1.2, beltLoad / beltLoadRef)),
  )
  const state = $derived(
    connection !== 'CONNECTED' || quality === 'COMM_ERROR' || quality === 'STALE'
      ? 'unknown'
      : machineState === 1
        ? 'run'
        : 'stop',
  )
</script>

<div
  class="wbf"
  data-testid="wbf-root"
  data-state={state}
  data-speed={rpm ?? ''}
  data-material-level={level.toFixed(2)}
  data-encoder={rpm === 0 && (driveCommand ?? 0) > 5 ? 'no-signal' : 'ok'}
  data-scenario={scenario ?? ''}
  aria-label="Representação do dosador de correia (em construção)"
>
  <p class="placeholder">Dosador animado em construção (bloco D). Estado: {state}.</p>
  <p class="placeholder">{reducedMotion ? 'Animação reduzida.' : ''} {massFlow ?? ''}</p>
</div>

<style>
  .wbf {
    min-height: 240px;
    border: 1px dashed var(--border-2);
    border-radius: var(--r-3);
    display: grid;
    place-items: center;
    color: var(--text-3);
    background: var(--surf-1);
  }
  .placeholder { margin: 0; font-size: var(--fs-caption); }
</style>
