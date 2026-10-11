<script lang="ts">
  /** KCM › Componentes: KCM, MDU, balança, SFT, encoder, SIB, motor e Anybus, com a evidência de
   *  cada um. Modelo e série desconhecidos ficam desconhecidos até a visita de campo. */
  import { untrack } from 'svelte'
  import Plus from '@lucide/svelte/icons/plus'
  import Trash from '@lucide/svelte/icons/trash-2'
  import { errorMessage } from '../lib/api'
  import {
    COMPONENT_PT,
    KNOWLEDGE_ORDER,
    KNOWLEDGE_PT,
    RESPONSIBLE_PATTERN,
    equipmentApi,
    isUnknown,
    rememberResponsible,
    rememberedResponsible,
    shown,
    type Component,
    type ComponentType,
    type EquipmentAdminView,
  } from '../lib/equipment'
  import { live } from '../lib/live.svelte'
  import Badge from '../components/ui/Badge.svelte'
  import Card from '../components/ui/Card.svelte'
  import PageHeader from '../components/ui/PageHeader.svelte'
  import EmptyState from '../components/ui/EmptyState.svelte'

  let { equipmentId }: { equipmentId: string } = $props()

  const TYPES = Object.keys(COMPONENT_PT) as ComponentType[]

  let view = $state<EquipmentAdminView | null>(null)
  let error = $state<string | null>(null)
  let editing = $state(false)
  let rows = $state<Component[]>([])
  let responsible = $state('')
  let saving = $state(false)
  let saveError = $state<string | null>(null)
  let saved = $state(false)

  const name = $derived(view?.profile.name ?? live.cardOf(equipmentId)?.name ?? equipmentId)

  async function load(id: string): Promise<void> {
    try {
      const v = await equipmentApi.datasheet(id)
      if (id !== equipmentId) return
      view = v
      error = null
    } catch (err) {
      if (id === equipmentId) error = errorMessage(err)
    }
  }

  $effect(() => {
    const id = equipmentId
    untrack(() => {
      editing = false
      void load(id)
    })
  })

  function startEdit(): void {
    if (!view) return
    rows = view.datasheet.components.map((c) => ({
      ...c,
      model: isUnknown(c.model) ? '' : c.model,
      serial: isUnknown(c.serial) ? '' : c.serial,
    }))
    responsible = rememberedResponsible()
    saveError = null
    saved = false
    editing = true
  }

  function addRow(): void {
    rows = [...rows, { type: 'Encoder', model: '', serial: '', quantity: null, evidence: 'UNKNOWN', note_pt: '' }]
  }

  async function save(): Promise<void> {
    if (!view) return
    saveError = null
    if (!RESPONSIBLE_PATTERN.test(responsible.trim())) {
      saveError = 'Informe o responsável (letras, números, espaço, ponto, @ ou hífen).'
      return
    }
    const components = rows.map((r) => ({
      ...r,
      model: r.model.trim() || 'UNKNOWN',
      serial: r.serial.trim() || 'UNKNOWN',
      quantity: r.quantity == null || Number.isNaN(Number(r.quantity)) ? null : Number(r.quantity),
      note_pt: r.note_pt.trim(),
    }))
    saving = true
    try {
      view = await equipmentApi.saveDatasheet(
        equipmentId,
        { ...$state.snapshot(view.datasheet), components },
        view.config_hash,
        responsible.trim(),
        'componentes atualizados',
      )
      rememberResponsible(responsible.trim())
      editing = false
      saved = true
    } catch (err) {
      saveError = errorMessage(err)
    } finally {
      saving = false
    }
  }

  const tone = (k: string) => (k === 'UNKNOWN' ? 'unknown' : k === 'HYPOTHESIS' ? 'warn' : 'info')
</script>

<section class="comp" data-testid="components">
  <PageHeader kicker={name} title="Componentes" lead="O que compõe o dosador, com a evidência de cada informação.">
    {#snippet more()}
      <p>Modelo e número de série ficam desconhecidos até alguém conferir no equipamento.</p>
    {/snippet}
  </PageHeader>

  {#if error && !view}
    <EmptyState title="Não foi possível carregar os componentes" text={error} />
  {:else if !view}
    <div class="sk" aria-busy="true" aria-label="Carregando componentes"></div>
  {:else}
    {#if saved}<p class="notice" role="status">Componentes salvos. A versão anterior ficou no histórico da configuração.</p>{/if}
    {#if !editing}
      {#if view.datasheet.components.length === 0}
        <EmptyState title="Nenhum componente registrado" text="Registre o que for confirmado no equipamento: tipo, modelo, série e a evidência." />
      {:else}
        <div class="list" data-testid="components-list">
          {#each view.datasheet.components as c, i (i)}
            <article class="item" style:--i={i}>
              <div class="item-head">
                <h2 class="item-title">{COMPONENT_PT[c.type] ?? c.type}</h2>
                <Badge tone={tone(c.evidence)}>{KNOWLEDGE_PT[c.evidence]}</Badge>
              </div>
              <dl class="dl">
                <div><dt>Modelo</dt><dd class:unknown={isUnknown(c.model)}>{shown(c.model)}</dd></div>
                <div><dt>Série</dt><dd class:unknown={isUnknown(c.serial)}>{shown(c.serial)}</dd></div>
                {#if c.quantity != null}<div><dt>Quantidade</dt><dd>{c.quantity}</dd></div>{/if}
              </dl>
              {#if c.note_pt}<p class="note">{c.note_pt}</p>{/if}
            </article>
          {/each}
        </div>
      {/if}
      <div class="actions">
        <button class="btn primary" type="button" onclick={startEdit} data-testid="components-edit">Editar componentes</button>
      </div>
    {:else}
      <Card title="Editar componentes" kicker="campo em branco fica desconhecido" testid="components-form">
        <div class="rows">
          {#each rows as r, i (i)}
            <div class="row">
              <label class="field"><span class="label">Tipo</span>
                <select bind:value={r.type}>{#each TYPES as t (t)}<option value={t}>{COMPONENT_PT[t]}</option>{/each}</select>
              </label>
              <label class="field"><span class="label">Modelo</span><input bind:value={r.model} maxlength="80" /></label>
              <label class="field"><span class="label">Série</span><input bind:value={r.serial} maxlength="80" /></label>
              <label class="field small"><span class="label">Qtd.</span><input type="number" min="1" max="99" bind:value={r.quantity} /></label>
              <label class="field"><span class="label">Evidência</span>
                <select bind:value={r.evidence}>{#each KNOWLEDGE_ORDER as k (k)}<option value={k}>{KNOWLEDGE_PT[k]}</option>{/each}</select>
              </label>
              <label class="field note-field"><span class="label">Nota</span><input bind:value={r.note_pt} maxlength="500" /></label>
              <button class="icon" type="button" aria-label={`Remover ${COMPONENT_PT[r.type]}`} onclick={() => (rows = rows.filter((_, j) => j !== i))}>
                <Trash size={18} aria-hidden="true" />
              </button>
            </div>
          {/each}
        </div>
        <button class="btn ghost add" type="button" onclick={addRow} data-testid="components-add"><Plus size={16} aria-hidden="true" /> Adicionar componente</button>
        <label class="field who"><span class="label">Responsável</span><input bind:value={responsible} maxlength="64" autocomplete="name" /></label>
        {#if saveError}<p class="err" role="alert">{saveError}</p>{/if}
        <div class="actions">
          <button class="btn primary" type="button" disabled={saving} onclick={save} data-testid="components-save">{saving ? 'Salvando…' : 'Salvar componentes'}</button>
          <button class="btn ghost" type="button" onclick={() => (editing = false)} disabled={saving}>Cancelar</button>
        </div>
      </Card>
    {/if}
  {/if}
</section>

<style>
  .comp { display: flex; flex-direction: column; gap: var(--sp-5); }
  .list { display: grid; gap: var(--sp-3); grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); }
  .item {
    display: flex;
    flex-direction: column;
    gap: var(--sp-2);
    padding: var(--sp-4);
    border: 1px solid var(--border-1);
    border-radius: var(--r-3);
    background: var(--surf-1);
    animation: rise var(--dur-screen) var(--ease-out) backwards;
    animation-delay: calc(var(--i, 0) * var(--stagger));
  }
  @keyframes rise {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: none; }
  }
  .item-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--sp-2); }
  .item-title { margin: 0; color: var(--text-1); font: 600 var(--fs-h3) / var(--lh-h3) var(--font-ui); }
  .dl { display: flex; flex-direction: column; gap: 2px; margin: 0; }
  .dl > div { display: grid; grid-template-columns: 7em minmax(0, 1fr); gap: var(--sp-2); }
  dt { color: var(--text-2); font: 500 var(--fs-caption) / var(--lh-body) var(--font-ui); }
  dd { margin: 0; color: var(--text-1); font: var(--fs-body) / var(--lh-body) var(--font-ui); overflow-wrap: anywhere; }
  dd.unknown { color: var(--text-2); }
  .note { margin: 0; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .notice { margin: 0; padding: var(--sp-3) var(--sp-4); border: 1px solid var(--st-ok); border-radius: var(--r-3); background: var(--st-ok-bg); color: var(--text-1); font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  .rows { display: flex; flex-direction: column; gap: var(--sp-3); }
  .row {
    display: grid;
    gap: var(--sp-2);
    grid-template-columns: 1fr 44px;
    align-items: end;
    padding: var(--sp-3);
    border: 1px solid var(--border-1);
    border-radius: var(--r-3);
    background: var(--surf-2);
  }
  .row .field { grid-column: 1; }
  .row .icon { grid-column: 2; grid-row: 1; }
  @media (min-width: 1024px) {
    .row { grid-template-columns: 1.3fr 1fr 1fr 5em 1.2fr 1.4fr 44px; }
    .row .field, .row .icon { grid-column: auto; grid-row: auto; }
  }
  .field { display: flex; flex-direction: column; gap: var(--sp-1); min-width: 0; }
  .who { max-width: 360px; margin-top: var(--sp-3); }
  input, select {
    width: 100%;
    min-height: var(--touch);
    padding: var(--sp-2);
    border: 1px solid var(--border-input);
    border-radius: var(--r-2);
    background: var(--surf-1);
    color: var(--text-1);
    font: 16px / 1.3 var(--font-ui);
  }
  input:focus-visible, select:focus-visible { outline: none; box-shadow: var(--focus); }
  .icon {
    display: grid;
    place-items: center;
    width: 44px;
    height: 44px;
    border: 1px solid var(--border-2);
    border-radius: var(--r-3);
    background: var(--surf-1);
    color: var(--text-2);
    cursor: pointer;
  }
  .icon:hover { color: var(--st-crit); border-color: var(--st-crit); }
  .icon:focus-visible { outline: none; box-shadow: var(--focus); }
  .add { margin-top: var(--sp-3); }
  .err { margin: var(--sp-2) 0 0; color: var(--st-crit); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .actions { display: flex; flex-wrap: wrap; gap: var(--sp-2); margin-top: var(--sp-3); }
  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--sp-2);
    min-height: var(--touch);
    padding: 0 var(--sp-4);
    border-radius: var(--r-3);
    font: 600 var(--fs-body) / 1.2 var(--font-ui);
    cursor: pointer;
    transition: transform var(--dur-micro) var(--ease-std);
  }
  .btn:active:not(:disabled) { transform: scale(0.97); }
  .btn:disabled { opacity: 0.55; cursor: not-allowed; }
  .btn.primary { border: 1px solid var(--accent); background: var(--accent); color: var(--on-accent); }
  .btn.ghost { border: 1px solid var(--border-2); background: var(--surf-1); color: var(--text-1); }
  .btn:focus-visible { outline: none; box-shadow: var(--focus); }
  .sk { height: 200px; border-radius: var(--r-4); background: var(--surf-2); opacity: 0.6; }
</style>
