<script lang="ts">
  /** <select> nativo. Em desktop (≥ 1280 px) a opção carrega o estado: "● Dosador Pó Base · Normal";
   *  abaixo disso só glifo + nome (o estado vai pela cor do glifo). Alvo de 44 px em toque e < 1024 px. */
  import ChevronDown from '@lucide/svelte/icons/chevron-down'
  import { stateGlyph, stateTone } from '../../lib/api'
  import { href, type EqScreen } from '../../lib/router'
  import { live } from '../../lib/live.svelte'
  import { app } from '../../lib/state.svelte'
  import { TID } from '../../lib/testids'

  const PLANT_VALUE = '__plant__'

  const cards = $derived(live.plant)
  const selectedId = $derived(app.route.name === 'eq' ? app.route.id : null)
  const selectedCard = $derived(cards.find((c) => c.id === selectedId) ?? null)
  const value = $derived(selectedId ?? PLANT_VALUE)
  const tone = $derived(selectedCard ? stateTone(selectedCard.state_pt) : 'neutral')

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
    >
      <option value={PLANT_VALUE}>Visão da planta</option>
      {#each cards as c (c.id)}
        <option value={c.id}>
          {stateGlyph(c.state_pt)} {c.name}{app.isDesktop ? ` · ${c.state_pt}` : ''}
        </option>
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
  }
</style>
