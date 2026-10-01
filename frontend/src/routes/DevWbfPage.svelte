<script lang="ts">
  // Página de desenvolvimento do dosador: exercita WbfMachine isolado, sem backend.
  // Só entra no roteador quando import.meta.env.DEV (rota /app/dev/wbf). Não é tela de produto.
  import { onMount, tick } from 'svelte'
  import WbfMachine from '../components/wbf/WbfMachine.svelte'
  import { PARTICLE_MAX } from '../components/wbf/wbf-scene'

  type Q = 'GOOD' | 'SIMULATED' | 'UNCERTAIN' | 'STALE' | 'COMM_ERROR' | 'BAD'

  // Valores iniciais = referências do perfil Pó Base só como ponto de partida da bancada
  // (reference_values em config/equipment/gtex_pha_po_base.yaml: rpm_ref 62, belt_load_ref 2,0).
  let rpm = $state(62)
  let rpmNull = $state(false)
  let beltLoad = $state(2)
  let driveCommand = $state(40)
  let massFlow = $state(1300)
  let machineState = $state<0 | 1 | 2>(1)
  let quality = $state<Q>('SIMULATED')
  let connection = $state('CONNECTED')
  let rpmRef = $state<number | null>(62)
  let beltLoadRef = $state<number | null>(2)
  let scenario = $state('NORMAL_OPERATION')
  let reducedMotion = $state(false)
  let theme = $state<'dark' | 'light'>('dark')
  let width = $state(100)

  const presets: Record<string, () => void> = {
    'Operação normal': () => { rpm = 62; rpmNull = false; beltLoad = 2; driveCommand = 40; machineState = 1; quality = 'SIMULATED'; connection = 'CONNECTED'; scenario = 'NORMAL_OPERATION' },
    'Pouco material (45 %)': () => { rpm = 62 / 0.45; rpmNull = false; beltLoad = 0.9; driveCommand = 86.5; machineState = 1; quality = 'SIMULATED'; connection = 'CONNECTED'; scenario = 'BELTLOAD_LOW' },
    'Falha de encoder': () => { rpm = 0; rpmNull = false; beltLoad = 2; driveCommand = 40; machineState = 1; quality = 'SIMULATED'; connection = 'CONNECTED'; scenario = 'ENCODER_FAILURE' },
    'Esforço alto (92 %)': () => { rpm = 143; rpmNull = false; beltLoad = 0.87; driveCommand = 92; machineState = 1; quality = 'SIMULATED'; connection = 'CONNECTED'; scenario = 'DRIVE_COMMAND_HIGH' },
    'Parada normal': () => { rpm = 0; rpmNull = false; beltLoad = 2; driveCommand = 0; machineState = 0; quality = 'SIMULATED'; connection = 'CONNECTED'; scenario = 'STOP_NORMAL' },
    'Sem comunicação': () => { quality = 'COMM_ERROR'; connection = 'ERROR'; scenario = 'COMMUNICATION_FAILURE' },
    'Dado antigo (STALE)': () => { quality = 'STALE'; connection = 'CONNECTED' },
    '60 partículas (1,2× ref.)': () => { beltLoad = 2.4; machineState = 1; quality = 'SIMULATED'; connection = 'CONNECTED' },
  }

  // ---- leitura dos data-* reais do DOM -------------------------------------------------------
  let host = $state<HTMLDivElement | null>(null)
  let dataset = $state<Record<string, string>>({})
  async function readDataset() {
    await tick()
    const el = host?.querySelector<HTMLElement>('[data-testid="wbf-root"]')
    if (!el) return
    const out: Record<string, string> = {}
    for (const [k, v] of Object.entries(el.dataset)) if (k !== 'testid') out[k] = v ?? ''
    dataset = out
  }
  $effect(() => {
    void [rpm, rpmNull, beltLoad, driveCommand, machineState, quality, connection, rpmRef, beltLoadRef, scenario, reducedMotion]
    void readDataset()
  })
  $effect(() => {
    document.documentElement.dataset.theme = theme
  })

  // ---- medidor de quadro (intervalo entre rAF; o custo real se mede com o Playwright/CDP) ------
  let frameAvg = $state(0)
  let frameMax = $state(0)
  let fps = $state(0)
  onMount(() => {
    let last = performance.now()
    const deltas: number[] = []
    let raf = 0
    const loop = (now: number) => {
      deltas.push(now - last)
      last = now
      if (deltas.length >= 60) {
        const sum = deltas.reduce((a, b) => a + b, 0)
        frameAvg = sum / deltas.length
        frameMax = Math.max(...deltas)
        fps = 1000 / frameAvg
        deltas.length = 0
      }
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  })

  const nf = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 })
</script>

<section class="dev">
  <header class="dev-head">
    <h1>Bancada do dosador (DEV)</h1>
    <p class="muted">Componente isolado com props fixas. Pool de {PARTICLE_MAX} partículas. Nada aqui lê a API.</p>
  </header>

  <div class="dev-grid">
    <div class="preview" style:width="{width}%" bind:this={host}>
      <WbfMachine
        rpm={rpmNull ? null : rpm}
        {beltLoad}
        {driveCommand}
        {massFlow}
        {machineState}
        {quality}
        {connection}
        {rpmRef}
        {beltLoadRef}
        {scenario}
        {reducedMotion}
      />
      <dl class="dataset">
        {#each Object.entries(dataset) as [k, v] (k)}
          <dt>data-{k.replace(/[A-Z]/g, (m) => '-' + m.toLowerCase())}</dt>
          <dd>{v === '' ? '""' : v}</dd>
        {/each}
      </dl>
      <p class="muted num">intervalo entre quadros: média {nf.format(frameAvg)} ms · pior {nf.format(frameMax)} ms · {nf.format(fps)} qps</p>
    </div>

    <form class="controls" onsubmit={(e) => e.preventDefault()}>
      <fieldset>
        <legend>Presets</legend>
        <div class="chips">
          {#each Object.entries(presets) as [name, apply] (name)}
            <button type="button" class="chip" onclick={apply}>{name}</button>
          {/each}
        </div>
      </fieldset>

      <fieldset>
        <legend>Sinais</legend>
        <label>Velocidade (rpm) <output class="num">{rpmNull ? 'null' : rpm}</output>
          <input type="range" min="0" max="150" step="1" bind:value={rpm} disabled={rpmNull} /></label>
        <label class="row"><input type="checkbox" bind:checked={rpmNull} /> rpm = null (tag ausente)</label>
        <label>Material na correia (kg/m) <output class="num">{nf.format(beltLoad)}</output>
          <input type="range" min="0" max="3" step="0.05" bind:value={beltLoad} /></label>
        <label>Esforço do acionamento (%) <output class="num">{nf.format(driveCommand)}</output>
          <input type="range" min="0" max="100" step="0.5" bind:value={driveCommand} /></label>
        <label>Vazão (kg/h) <output class="num">{massFlow}</output>
          <input type="range" min="0" max="3000" step="10" bind:value={massFlow} /></label>
      </fieldset>

      <fieldset>
        <legend>Estado e qualidade</legend>
        <label>Estado da máquina
          <select bind:value={machineState}>
            <option value={0}>0 · Parada</option>
            <option value={1}>1 · Em operação</option>
            <option value={2}>2 · Alarme</option>
          </select></label>
        <label>Qualidade
          <select bind:value={quality}>
            {#each ['GOOD', 'SIMULATED', 'UNCERTAIN', 'STALE', 'COMM_ERROR', 'BAD'] as q (q)}<option value={q}>{q}</option>{/each}
          </select></label>
        <label>Conexão
          <select bind:value={connection}>
            {#each ['CONNECTED', 'CONNECTING', 'HANDSHAKE', 'RECONNECTING', 'ERROR', 'DISCONNECTED', 'NOT_CONFIGURED'] as c (c)}<option value={c}>{c}</option>{/each}
          </select></label>
        <label>Cenário (só eco em data-scenario) <input type="text" bind:value={scenario} /></label>
      </fieldset>

      <fieldset>
        <legend>Referências</legend>
        <label>rpmRef <input type="number" min="0" step="1" value={rpmRef ?? ''} oninput={(e) => (rpmRef = e.currentTarget.value === '' ? null : Number(e.currentTarget.value))} placeholder="null → máx. observado" /></label>
        <label>beltLoadRef <input type="number" min="0" step="0.1" value={beltLoadRef ?? ''} oninput={(e) => (beltLoadRef = e.currentTarget.value === '' ? null : Number(e.currentTarget.value))} placeholder="null → máx. observado" /></label>
      </fieldset>

      <fieldset>
        <legend>Bancada</legend>
        <label class="row"><input type="checkbox" bind:checked={reducedMotion} /> reducedMotion (prop)</label>
        <label>Tema
          <select bind:value={theme}><option value="dark">escuro</option><option value="light">claro</option></select></label>
        <label>Largura do componente (%) <output class="num">{width}</output>
          <input type="range" min="30" max="100" step="5" bind:value={width} /></label>
      </fieldset>
    </form>
  </div>
</section>

<style>
  .dev { padding: var(--sp-4); display: grid; gap: var(--sp-4); max-width: var(--content-max); color: var(--text-1); }
  .dev-head h1 { margin: 0; font: 600 var(--fs-h1) / var(--lh-h1) var(--font-ui); }
  .muted { margin: var(--sp-1) 0 0; color: var(--text-3); font: 400 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .dev-grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--sp-4); }
  @media (min-width: 1024px) { .dev-grid { grid-template-columns: minmax(0, 2fr) minmax(280px, 1fr); } }
  .preview { display: grid; gap: var(--sp-3); align-content: start; min-width: 0; }
  .dataset { display: grid; grid-template-columns: auto 1fr; gap: 2px var(--sp-3); margin: 0; font: 400 var(--fs-mono-sm) / var(--lh-mono-sm) var(--font-mono); color: var(--text-2); }
  .dataset dt { color: var(--text-3); }
  .dataset dd { margin: 0; }
  .controls { display: grid; gap: var(--sp-3); align-content: start; }
  fieldset { display: grid; gap: var(--sp-2); margin: 0; padding: var(--sp-3); border: 1px solid var(--border-1); border-radius: var(--r-3); background: var(--surf-1); }
  legend { padding: 0 var(--sp-1); font: 500 var(--fs-label) / var(--lh-label) var(--font-ui); letter-spacing: var(--ls-label); text-transform: uppercase; color: var(--text-3); }
  label { display: grid; gap: var(--sp-1); font: 400 var(--fs-caption) / var(--lh-caption) var(--font-ui); color: var(--text-2); }
  label.row { grid-template-columns: auto 1fr; align-items: center; min-height: 28px; }
  output { color: var(--text-1); }
  input[type='range'] { width: 100%; min-height: var(--touch); margin: 0; accent-color: var(--accent); }
  input[type='checkbox'] { width: 18px; height: 18px; accent-color: var(--accent); margin: 0; }
  select, input[type='text'], input[type='number'] { min-height: 36px; padding: 0 var(--sp-2); border-radius: var(--r-2); border: 1px solid var(--border-input); background: var(--surf-2); color: var(--text-1); font: 400 var(--fs-body) / var(--lh-body) var(--font-ui); }
  .chips { display: flex; flex-wrap: wrap; gap: var(--sp-2); }
  .chip { min-height: 36px; padding: 0 var(--sp-3); border-radius: var(--r-pill); border: 1px solid var(--border-input); background: var(--surf-2); color: var(--text-1); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); cursor: pointer; }
  .chip:hover { background: var(--surf-3); }
  .num { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
</style>
