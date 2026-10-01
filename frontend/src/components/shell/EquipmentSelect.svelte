<script lang="ts">
  /** <select> nativo. A opção sempre carrega glifo, nome e a PALAVRA do estado
   *  ("● Dosador Pó Base · Normal"): leitor de tela não enxerga cor de glifo.
   *  Abaixo de 1280 px o sufixo " (exemplo)" sai do nome; se ainda assim não couber no campo
   *  (medido com a fonte real), o nome é encurtado com "…". O estado nunca é abreviado.
   *  Alvo de 44 px em toque e < 1024 px. */
  import { onMount } from 'svelte'
  import ChevronDown from '@lucide/svelte/icons/chevron-down'
  import { stateGlyph, stateTone, type PlantCard } from '../../lib/api'
  import { href, type EqScreen } from '../../lib/router'
  import { live } from '../../lib/live.svelte'
  import { app } from '../../lib/state.svelte'
  import { TID } from '../../lib/testids'

  const PLANT_VALUE = '__plant__'
  const EXAMPLE_SUFFIX = /\s*\(exemplo\)\s*$/i

  const cards = $derived(live.plant)
  const selectedId = $derived(app.route.name === 'eq' ? app.route.id : null)
  const selectedCard = $derived(cards.find((c) => c.id === selectedId) ?? null)
  const value = $derived(selectedId ?? PLANT_VALUE)
  const tone = $derived(selectedCard ? stateTone(selectedCard.state_pt) : 'neutral')

  let selectEl: HTMLSelectElement | undefined = $state()
  /** Largura do <select> (ResizeObserver do Svelte): re-mede o texto ao girar a tela. */
  let width = $state(0)
  let fontsReady = $state(false)
  let ctx: CanvasRenderingContext2D | null = null

  onMount(() => {
    // a fonte local (Plex) pode chegar depois do primeiro desenho: mede de novo quando carregar
    document.fonts?.ready.then(() => (fontsReady = true)).catch(() => (fontsReady = true))
  })

  /** Espaço útil para o texto da opção e a fonte real do campo. Null quando não dá para medir. */
  const fit = $derived.by(() => {
    void fontsReady
    if (!selectEl || width <= 0) return null
    const cs = getComputedStyle(selectEl)
    const inner = width - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight)
    if (!Number.isFinite(inner) || inner <= 0) return null
    return { inner, font: `${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}` }
  })

  function measure(text: string, font: string): number {
    ctx ??= document.createElement('canvas').getContext('2d')
    if (!ctx) return 0
    ctx.font = font
    return ctx.measureText(text).width
  }

  function compose(glyph: string, name: string, state: string): string {
    return `${glyph} ${name} · ${state}`
  }

  /** Texto da opção. Desktop (≥ 1280 px): nome completo. Abaixo: sem "(exemplo)" e, se faltar
   *  espaço, nome encurtado com "…" até caber. O estado fica inteiro sempre. */
  function optionText(c: PlantCard): string {
    const glyph = stateGlyph(c.state_pt)
    if (app.isDesktop) return compose(glyph, c.name, c.state_pt)
    const short = c.name.replace(EXAMPLE_SUFFIX, '') || c.name
    const f = fit
    if (!f) return compose(glyph, short, c.state_pt)
    let name = short
    let text = compose(glyph, name, c.state_pt)
    while (measure(text, f.font) > f.inner && name.length > 2) {
      name = `${name.replace(/…$/, '').slice(0, -1).trimEnd()}…`
      text = compose(glyph, name, c.state_pt)
    }
    return text
  }

  function onChange(e: Event) {
    const next = (e.currentTarget as HTMLSelectElement).value
    if (next === PLANT_VALUE) {
      app.go(href.plant())
      return
    }
    const screen: EqScreen = app.route.name === 'eq' && !app.route.eventId ? app.route.screen : 'dashboard'
    app.go(href.eq(next, screen))
  }
</script>

<label class="sel" data-tone={tone}>
  <span class="sel-label label">Equipamento</span>
  <span class="sel-field">
    <select
      class="sel-input"
      data-testid={TID.header.equipmentSelect}
      data-selected={selectedId ?? ''}
      {value}
      onchange={onChange}
      aria-label="Equipamento selecionado"
      bind:this={selectEl}
      bind:clientWidth={width}
    >
      <option value={PLANT_VALUE}>Visão da planta</option>
      {#each cards as c (c.id)}
        <option value={c.id}>{optionText(c)}</option>
      {/each}
    </select>
    <span class="sel-chev" aria-hidden="true"><ChevronDown size={16} /></span>
  </span>
</label>

<style>
  .sel {
    display: flex;
    align-items: center;
    gap: var(--sp-3);
    min-width: 0;
    flex: 1 1 auto;
    max-width: 420px;
  }
  .sel-label { flex: none; }
  .sel-field {
    position: relative;
    display: flex;
    align-items: center;
    flex: 1 1 auto;
    min-width: 0;
    height: 36px;
    border: 1px solid var(--border-input);
    border-radius: var(--r-3);
    background: var(--surf-2);
    transition: border-color var(--dur-base) var(--ease-std);
  }
  .sel-field:hover { border-color: var(--text-3); }
  .sel-field:focus-within { box-shadow: var(--focus); border-color: var(--accent); }
  .sel-input {
    appearance: none;
    -webkit-appearance: none;
    width: 100%;
    height: 100%;
    min-width: 0;
    padding: 0 var(--sp-8) 0 var(--sp-3);
    border: 0;
    background: transparent;
    color: var(--text-1);
    font: 500 var(--fs-body) / var(--lh-body) var(--font-ui);
    text-overflow: ellipsis;
    cursor: pointer;
  }
  .sel-input:focus-visible { outline: none; box-shadow: none; }
  .sel-input option { background: var(--surf-3); color: var(--text-1); }
  .sel-chev {
    position: absolute;
    right: var(--sp-2);
    display: grid;
    place-items: center;
    color: var(--text-3);
    pointer-events: none;
  }
  @media (max-width: 1023px), (pointer: coarse) {
    /* o <select> é o alvo: 44 px dentro da borda de 1 px do campo */
    .sel-field { height: calc(var(--touch) + 2px); }
  }
  @media (max-width: 767px) {
    .sel { gap: 0; max-width: none; }
    .sel-label {
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      clip: rect(0 0 0 0);
      white-space: nowrap;
    }
    /* celular: a seta encosta mais e sobra texto; 10 px à esquerda, 28 à direita */
    .sel-input { padding: 0 28px 0 10px; }
  }
</style>
