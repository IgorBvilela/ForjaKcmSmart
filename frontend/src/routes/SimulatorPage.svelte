<script lang="ts">
  // Página do simulador (bloco D). Só cenário e sliders: nenhum comando chega ao KCM.
  // Dados ao vivo por polling de 1 Hz em GET /equipments/{id}/live.
  // Usa o sistema de componentes (KpiTile, QualityBadge via KpiTile, Button, EmptyState): a faixa
  // DADOS SIMULADOS e o padding da página vêm do shell, não daqui.
  import { onMount } from 'svelte'
  import WbfMachine from '../components/wbf/WbfMachine.svelte'
  import KpiTile from '../components/data/KpiTile.svelte'
  import Button from '../components/ui/Button.svelte'
  import EmptyState from '../components/ui/EmptyState.svelte'
  import { app } from '../lib/state.svelte'
  import {
    ApiFailure,
    equipmentIdFromUrl,
    formatValue,
    simulatorApi,
    tagMap,
    type LiveView,
    type QualityCode,
    type ReferenceValues,
    type SimulatorView,
  } from '../components/wbf/simulator-api'

  let { equipmentId = undefined }: { equipmentId?: string } = $props()

  const id = $derived(equipmentId ?? equipmentIdFromUrl() ?? '')

  // ---- dados --------------------------------------------------------------------------------
  let sim = $state<SimulatorView | null>(null)
  let live = $state<LiveView | null>(null)
  let refs = $state<ReferenceValues | null>(null)
  let loadError = $state<ApiFailure | null>(null)
  let notSimulator = $state(false)
  let busy = $state<string | null>(null)
  let notice = $state<{ kind: 'ok' | 'err'; text: string } | null>(null)
  let pollFailures = $state(0)

  const tags = $derived(tagMap(live))
  const val = (k: string): number | null => tags[k]?.value ?? null
  const activeCode = $derived(sim?.controls.scenario ?? '')
  const activeScenario = $derived(sim?.scenarios.find((s) => s.code === activeCode) ?? null)

  /** Qualidade que manda no desenho: a pior entre as tags que ele usa. */
  const machineQuality = $derived.by<QualityCode>(() => {
    const core = ['machine_state', 'rpm', 'belt_load', 'drive_command'].map((k) => tags[k]?.quality)
    if (core.includes('COMM_ERROR')) return 'COMM_ERROR'
    if (core.includes('STALE')) return 'STALE'
    if (core.includes('BAD')) return 'BAD'
    if (core.includes('UNCERTAIN')) return 'UNCERTAIN'
    return (tags['rpm']?.quality as QualityCode | undefined) ?? 'SIMULATED'
  })
  const machineState = $derived.by<0 | 1 | 2 | null>(() => {
    const v = val('machine_state')
    return v === 0 || v === 1 || v === 2 ? v : null
  })

  // ---- textos explicativos (spec §39–41, knowledge/diagnostics/*.yaml) -----------------------
  const EXPLAIN: Record<string, string> = {
    BELTLOAD_LOW:
      'O KCM está aumentando o esforço para tentar compensar a redução de material sobre a correia.',
    ENCODER_FAILURE:
      'A máquina apresenta comando de acionamento, mas o sistema deixou de receber feedback de velocidade.',
    COMMUNICATION_FAILURE:
      'As tentativas de leitura do equipamento estão falhando. A Forja não está medindo o KCM: está medindo o caminho de comunicação até ele. O KCM pode estar operando normalmente; a dosagem não depende da Forja.',
  }

  // ---- sliders (modo avançado) ---------------------------------------------------------------
  interface SliderDef {
    key: string
    label: string
    unit: string
    step: number
    decimals: number
    max: () => number
  }
  const twice = (ref: number | undefined, current: number | null, floor: number) =>
    Math.max(floor, 2 * (ref ?? current ?? floor / 2))
  const sliderDefs: SliderDef[] = [
    { key: 'setpoint', label: 'Setpoint', unit: 'kg/h', step: 10, decimals: 0, max: () => twice(refs?.setpoint_ref, val('setpoint'), 100) },
    { key: 'mass_flow', label: 'Vazão', unit: 'kg/h', step: 10, decimals: 0, max: () => twice(refs?.setpoint_ref, val('mass_flow'), 100) },
    { key: 'drive_command', label: 'Esforço do acionamento', unit: '%', step: 0.5, decimals: 1, max: () => 100 },
    { key: 'rpm', label: 'Velocidade', unit: 'rpm', step: 1, decimals: 0, max: () => twice(refs?.rpm_ref, val('rpm'), 10) },
    { key: 'belt_load', label: 'Material na correia', unit: 'kg/m', step: 0.01, decimals: 2, max: () => twice(refs?.belt_load_ref, val('belt_load'), 0.5) },
    { key: 'net_weight', label: 'Peso líquido', unit: 'kg', step: 0.001, decimals: 3, max: () => twice(undefined, val('net_weight'), 0.5) },
    { key: 'int_channel_pct', label: 'Canal de integração', unit: '%', step: 0.5, decimals: 1, max: () => 100 },
  ]
  let sliders = $state<Record<string, { on: boolean; value: number }>>({})
  let slidersSeeded = false

  function seedSliders(view: SimulatorView, current: LiveView | null) {
    const t = tagMap(current)
    const next: Record<string, { on: boolean; value: number }> = {}
    for (const d of sliderDefs) {
      const ov = view.controls.overrides[d.key]
      next[d.key] = { on: ov != null, value: ov ?? t[d.key]?.value ?? 0 }
    }
    sliders = next
    slidersSeeded = true
  }
  const anySliderOn = $derived(Object.values(sliders).some((s) => s.on))
  const hasOverrides = $derived(Object.keys(sim?.controls.overrides ?? {}).length > 0)

  // ---- tiles ao vivo ------------------------------------------------------------------------
  const TILE_TAGS = ['setpoint', 'mass_flow', 'drive_command', 'rpm', 'belt_load', 'net_weight', 'int_channel_pct']
  const STATE_PT: Record<number, string> = { 0: 'Parada', 1: 'Em operação', 2: 'Alarme' }
  const stateTag = $derived(tags['machine_state'])

  // ---- ciclo de vida ------------------------------------------------------------------------
  async function loadStatic() {
    loadError = null
    notSimulator = false
    try {
      const [s, e] = await Promise.all([simulatorApi.get(id), simulatorApi.equipment(id)])
      sim = s
      refs = e.profile.reference_values
    } catch (err) {
      if (err instanceof ApiFailure && err.status === 409) notSimulator = true
      else loadError = err instanceof ApiFailure ? err : new ApiFailure(0, 'UNKNOWN', 'Falha ao carregar o simulador.')
    }
  }

  async function poll() {
    if (!id || document.hidden) return
    try {
      live = await simulatorApi.live(id)
      pollFailures = 0
      if (sim && !slidersSeeded) seedSliders(sim, live)
    } catch {
      pollFailures += 1
    }
  }

  onMount(() => {
    if (!id) return
    void loadStatic().then(poll)
    const timer = setInterval(() => void poll(), 1000)
    const onVis = () => {
      if (!document.hidden) void poll()
    }
    document.addEventListener('visibilitychange', onVis)
    return () => {
      clearInterval(timer)
      document.removeEventListener('visibilitychange', onVis)
    }
  })

  // ---- ações (só no simulador) ----------------------------------------------------------------
  async function chooseScenario(code: string) {
    if (!sim || busy) return
    const previous = sim
    busy = code
    sim = { ...sim, controls: { ...sim.controls, scenario: code } } // otimista
    try {
      sim = await simulatorApi.setScenario(id, code)
      const title = sim.scenarios.find((s) => s.code === code)?.title_pt ?? code
      notice = { kind: 'ok', text: `Cenário alterado para "${title}". O simulador reinicia o tempo do cenário.` }
    } catch (err) {
      sim = previous
      notice = { kind: 'err', text: err instanceof ApiFailure ? err.messagePt : 'Falha ao trocar o cenário.' }
    } finally {
      busy = null
    }
  }

  async function applySliders() {
    if (!sim || busy) return
    const overrides: Record<string, number> = {}
    for (const d of sliderDefs) if (sliders[d.key]?.on) overrides[d.key] = sliders[d.key].value
    if (Object.keys(overrides).length === 0) {
      notice = { kind: 'err', text: 'Marque "Fixar" em pelo menos um controle antes de aplicar.' }
      return
    }
    busy = 'controls'
    try {
      sim = await simulatorApi.setControls(id, overrides)
      notice = { kind: 'ok', text: `${Object.keys(overrides).length} controle(s) fixado(s) no simulador.` }
    } catch (err) {
      notice = { kind: 'err', text: err instanceof ApiFailure ? err.messagePt : 'Falha ao aplicar os controles.' }
    } finally {
      busy = null
    }
  }

  async function clearSliders() {
    if (!sim || busy) return
    busy = 'controls'
    try {
      sim = await simulatorApi.clearControls(id)
      for (const k of Object.keys(sliders)) sliders[k].on = false
      notice = { kind: 'ok', text: 'Controles removidos. O cenário continua.' }
    } catch (err) {
      notice = { kind: 'err', text: err instanceof ApiFailure ? err.messagePt : 'Falha ao limpar os controles.' }
    } finally {
      busy = null
    }
  }
</script>

<section class="page" data-testid="simulator-page" aria-labelledby="sim-title">
  <header class="head">
    <h1 id="sim-title">Simulador</h1>
    {#if live}
      <p class="sub">{live.name} · <span class="num">{id}</span></p>
    {:else if id}
      <p class="sub"><span class="num">{id}</span></p>
    {/if}
    <p class="note">{sim?.note_pt ?? 'Controles afetam apenas o simulador. Nenhum comando chega ao KCM.'}</p>
  </header>

  {#if !id}
    <EmptyState
      title="Nenhum equipamento selecionado"
      text="Abra o simulador a partir de um equipamento (menu Ferramentas → Simulador)."
    />
  {:else if notSimulator}
    <EmptyState
      title="Simulador indisponível: este equipamento lê dados reais"
      text="Cenários e controles só existem para equipamentos ligados ao driver simulator. Dados do equipamento não podem ser alterados pela Forja."
    />
  {:else if loadError}
    <EmptyState title="Não foi possível carregar o simulador" text={`${loadError.messagePt} (${loadError.code})`}>
      <Button variant="ghost" onclick={() => void loadStatic().then(poll)}>Tentar de novo</Button>
    </EmptyState>
  {:else}
    <div class="grid">
      <div class="col-machine">
        <WbfMachine
          rpm={val('rpm')}
          beltLoad={val('belt_load')}
          driveCommand={val('drive_command')}
          massFlow={val('mass_flow')}
          {machineState}
          quality={machineQuality}
          connection={live?.connection ?? 'CONNECTING'}
          rpmRef={refs?.rpm_ref ?? null}
          beltLoadRef={refs?.belt_load_ref ?? null}
          scenario={activeCode}
          reducedMotion={app.reducedMotion}
        />

        <div class="tiles" aria-label="Valores ao vivo">
          <KpiTile
            tag="machine_state"
            label={stateTag?.label_pt ?? 'Estado da máquina'}
            textValue={machineState == null ? '—' : STATE_PT[machineState]}
            quality={stateTag?.quality ?? 'COMM_ERROR'}
            qualityPt={stateTag?.quality_pt ?? null}
            ageS={stateTag?.age_s ?? null}
            reasonPt={stateTag?.reason_pt ?? null}
            compact
            sparkline={false}
            explainQuality
            animate={false}
            index={0}
          />
          {#each TILE_TAGS as key, i (key)}
            {@const t = tags[key]}
            <KpiTile
              tag={key}
              label={t?.label_pt ?? sliderDefs.find((d) => d.key === key)?.label ?? key}
              unit={t?.unit ?? ''}
              decimals={t?.decimals ?? 1}
              value={t?.value ?? null}
              quality={t?.quality ?? 'COMM_ERROR'}
              qualityPt={t?.quality_pt ?? null}
              ageS={t?.age_s ?? null}
              reasonPt={t?.reason_pt ?? null}
              compact
              sparkline={false}
              explainQuality
              animate={!app.reducedMotion}
              index={i + 1}
              popoverAlign={i >= 3 ? 'end' : 'start'}
            />
          {/each}
        </div>
        {#if pollFailures >= 3}
          <p class="poll-warn" role="status">Sem resposta do Edge há {pollFailures} s. Os valores acima podem estar antigos.</p>
        {/if}
      </div>

      <aside class="col-panel">
        <fieldset class="scenarios" data-testid="sim-scenarios">
          <legend class="label">Cenário</legend>
          {#if !sim}
            <p class="muted">Carregando cenários…</p>
          {:else}
            {#each sim.scenarios as s (s.code)}
              <label
                class="card"
                class:active={s.code === activeCode}
                data-testid="sim-scenario-{s.code}"
                data-state={s.code === activeCode ? 'active' : 'idle'}
              >
                <input
                  type="radio"
                  name="scenario"
                  value={s.code}
                  checked={s.code === activeCode}
                  disabled={busy != null}
                  onchange={() => void chooseScenario(s.code)}
                />
                <span class="card-title">{s.title_pt}</span>
                <span class="card-code num">{s.code}</span>
              </label>
            {/each}
          {/if}
        </fieldset>

        {#if activeScenario}
          <div class="explain" data-testid="sim-explanation">
            <span class="label">O que este cenário mostra</span>
            {#if EXPLAIN[activeScenario.code]}
              <p class="explain-main">{EXPLAIN[activeScenario.code]}</p>
            {/if}
            <p class="explain-desc">{activeScenario.description_pt}</p>
          </div>
        {/if}

        {#if notice}
          <p class="notice" class:is-err={notice.kind === 'err'} role="status" data-testid="sim-notice">{notice.text}</p>
        {/if}

        <details class="advanced" data-testid="sim-advanced">
          <summary>
            <span>Controles avançados</span>
            <span class="muted">{hasOverrides ? `${Object.keys(sim?.controls.overrides ?? {}).length} fixado(s)` : 'nenhum fixado'}</span>
          </summary>
          <p class="muted hint">Fixa o valor de uma variável na saída do simulador. Faixa dos controles: 0 a 2× a referência do perfil (só interface).</p>
          <div class="sliders">
            {#each sliderDefs as d (d.key)}
              {@const s = sliders[d.key]}
              {#if s}
                <div class="slider" class:on={s.on}>
                  <label class="slider-fix">
                    <input type="checkbox" bind:checked={s.on} disabled={busy != null} />
                    <span>Fixar</span>
                  </label>
                  <label class="slider-name" for="sl-{d.key}">{d.label}</label>
                  <output class="slider-val num" for="sl-{d.key}">{formatValue(s.value, d.decimals)} <span class="unit">{d.unit}</span></output>
                  <input
                    id="sl-{d.key}"
                    class="range"
                    type="range"
                    min="0"
                    max={d.max()}
                    step={d.step}
                    bind:value={s.value}
                    disabled={!s.on || busy != null}
                    aria-label="{d.label} ({d.unit})"
                  />
                </div>
              {/if}
            {/each}
          </div>
          <div class="actions">
            <Button variant="primary" onclick={() => void applySliders()} disabled={busy != null || !anySliderOn}>Aplicar</Button>
            <Button variant="ghost" onclick={() => void clearSliders()} disabled={busy != null || !hasOverrides}>Limpar</Button>
          </div>
        </details>
      </aside>
    </div>
  {/if}
</section>

<style>
  .page {
    display: grid;
    gap: var(--sp-5);
    color: var(--text-1);
  }

  .head { display: grid; gap: var(--sp-1); }
  h1 { margin: 0; font: 600 var(--fs-h1) / var(--lh-h1) var(--font-ui); }
  @media (min-width: 1024px) {
    h1 { font-size: var(--fs-display); line-height: var(--lh-display); }
  }
  .sub { margin: 0; color: var(--text-3); font: 400 var(--fs-body) / var(--lh-body) var(--font-ui); }
  .note { margin: var(--sp-1) 0 0; max-width: 80ch; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .muted { color: var(--text-3); font: 400 var(--fs-caption) / var(--lh-caption) var(--font-ui); margin: 0; }

  /* ---- grid 12 colunas no desktop; 1 coluna no celular ---- */
  .grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--sp-4); }
  .col-machine { display: grid; gap: var(--sp-3); min-width: 0; align-content: start; }
  .col-panel { display: grid; gap: var(--sp-3); min-width: 0; align-content: start; }
  @media (min-width: 1024px) {
    .grid { grid-template-columns: repeat(12, minmax(0, 1fr)); }
    .col-machine { grid-column: span 8; }
    .col-panel { grid-column: span 4; }
  }

  /* ---- tiles (KpiTile compacto, sem mini-tendência) ---- */
  .tiles { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--sp-2); }
  @media (max-width: 359px) { .tiles { grid-template-columns: minmax(0, 1fr); } }
  @media (min-width: 768px) { .tiles { grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--sp-3); } }

  .poll-warn { margin: 0; padding: var(--sp-2) var(--sp-3); border-radius: var(--r-2); background: var(--st-info-bg); color: var(--st-info); font: 400 var(--fs-caption) / var(--lh-caption) var(--font-ui); }

  /* ---- radio-cards dos cenários: cobre só na borda e na barra (seleção), nunca no fundo ou no texto ---- */
  .scenarios { display: grid; gap: var(--sp-2); margin: 0; padding: 0; border: 0; min-width: 0; }
  .scenarios legend { padding: 0; margin-bottom: var(--sp-1); }
  @media (min-width: 768px) and (max-width: 1023px) { .scenarios { grid-template-columns: repeat(2, minmax(0, 1fr)); } .scenarios legend { grid-column: 1 / -1; } }
  .card {
    position: relative;
    display: grid;
    gap: 2px;
    min-height: var(--touch);
    padding: var(--sp-2) var(--sp-3);
    background: var(--surf-1);
    border: 1px solid var(--border-1);
    border-radius: var(--r-3);
    cursor: pointer;
    transition: border-color var(--dur-base) var(--ease-std), background var(--dur-base) var(--ease-std);
  }
  .card:hover { border-color: var(--border-2); background: var(--surf-2); }
  .card.active { border-color: var(--accent); }
  .card.active::before { content: ''; position: absolute; left: 0; top: var(--sp-2); bottom: var(--sp-2); width: 3px; border-radius: var(--r-pill); background: var(--accent); }
  .card:has(input:focus-visible) { box-shadow: var(--focus); }
  .card:has(input:disabled) { cursor: progress; }
  .card input { position: absolute; opacity: 0; width: 1px; height: 1px; margin: 0; pointer-events: none; }
  .card-title { font: 500 var(--fs-body) / var(--lh-body) var(--font-ui); color: var(--text-1); }
  .card-code { font: 400 var(--fs-mono-sm) / var(--lh-mono-sm) var(--font-mono); color: var(--text-3); }

  .explain { display: grid; gap: var(--sp-2); padding: var(--sp-3); border-radius: var(--r-3); border: 1px solid var(--border-1); background: var(--surf-1); }
  .explain-main { margin: 0; font: 400 var(--fs-body-lg) / var(--lh-body-lg) var(--font-ui); color: var(--text-1); }
  .explain-desc { margin: 0; font: 400 var(--fs-body) / var(--lh-body) var(--font-ui); color: var(--text-2); }

  .notice { margin: 0; padding: var(--sp-2) var(--sp-3); border-radius: var(--r-2); background: var(--surf-2); color: var(--text-2); font: 400 var(--fs-caption) / var(--lh-caption) var(--font-ui); border-left: 3px solid var(--border-2); }
  .notice.is-err { border-left-color: var(--st-crit); color: var(--st-crit); background: var(--st-crit-bg); }

  /* ---- modo avançado ---- */
  .advanced { border: 1px solid var(--border-1); border-radius: var(--r-3); background: var(--surf-1); }
  .advanced summary { display: flex; justify-content: space-between; align-items: center; gap: var(--sp-2); min-height: var(--touch); padding: var(--sp-2) var(--sp-3); cursor: pointer; font: 600 var(--fs-h3) / var(--lh-h3) var(--font-ui); list-style: none; }
  .advanced summary::-webkit-details-marker { display: none; }
  .advanced summary::after { content: '+'; color: var(--text-3); font-family: var(--font-mono); }
  .advanced[open] summary::after { content: '−'; }
  .hint { padding: 0 var(--sp-3); }
  .sliders { display: grid; gap: var(--sp-2); padding: var(--sp-3); }
  .slider {
    display: grid;
    grid-template-columns: auto 1fr auto;
    grid-template-areas: 'fix name val' 'range range range';
    align-items: center;
    gap: var(--sp-1) var(--sp-3);
    padding: var(--sp-2) var(--sp-3);
    border-radius: var(--r-2);
    background: var(--surf-2);
    border: 1px solid transparent;
    transition: border-color var(--dur-base) var(--ease-std);
  }
  .slider.on { border-color: var(--accent); }
  /* "Fixar": alvo de 44 px com caixa de 24 px */
  .slider-fix { grid-area: fix; display: inline-flex; align-items: center; gap: var(--sp-2); min-height: var(--touch); padding-right: var(--sp-1); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); color: var(--text-2); cursor: pointer; }
  .slider-fix input { width: 24px; height: 24px; accent-color: var(--accent); margin: 0; cursor: pointer; }
  .slider-name { grid-area: name; font: 500 var(--fs-body) / var(--lh-body) var(--font-ui); color: var(--text-1); }
  .slider-val { grid-area: val; font: 500 var(--fs-mono) / var(--lh-mono) var(--font-mono); font-variant-numeric: tabular-nums; color: var(--text-1); }
  .slider:not(.on) .slider-val, .slider:not(.on) .slider-name { color: var(--text-3); }
  .range { grid-area: range; width: 100%; min-height: var(--touch); margin: 0; accent-color: var(--accent); }
  .range:disabled { opacity: 0.5; }
  .actions { display: flex; gap: var(--sp-2); padding: 0 var(--sp-3) var(--sp-3); }

  .num { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
  .label { font: 500 var(--fs-label) / var(--lh-label) var(--font-ui); letter-spacing: var(--ls-label); text-transform: uppercase; color: var(--text-3); }

  @media (prefers-reduced-motion: reduce) {
    .card, .slider { transition: none; }
  }
</style>
