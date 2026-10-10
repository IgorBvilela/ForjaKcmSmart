<script lang="ts">
  /** KCM › Ficha técnica: identificação, controlador e interface Host com a evidência de cada
   *  informação. Desconhecido fica como desconhecido até alguém confirmar em campo. */
  import { untrack } from 'svelte'
  import { errorMessage } from '../lib/api'
  import {
    FIELD_PT,
    KNOWLEDGE_ORDER,
    KNOWLEDGE_PT,
    RESPONSIBLE_PATTERN,
    equipmentApi,
    isUnknown,
    rememberResponsible,
    rememberedResponsible,

    type Datasheet,
    type EquipmentAdminView,
    type KnowledgeState,
  } from '../lib/equipment'
  import { live } from '../lib/live.svelte'
  import { href } from '../lib/router'
  import Badge from '../components/ui/Badge.svelte'
  import Card from '../components/ui/Card.svelte'
  import EmptyState from '../components/ui/EmptyState.svelte'

  let { equipmentId }: { equipmentId: string } = $props()

  let view = $state<EquipmentAdminView | null>(null)
  let error = $state<string | null>(null)
  let editing = $state(false)
  let draft = $state<Datasheet | null>(null)
  let responsible = $state('')
  let reason = $state('')
  let saving = $state(false)
  let saveError = $state<string | null>(null)
  let saved = $state(false)
  let shake = $state(0)

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

  /** Aplica `fn` a todo campo de texto de um objeto da ficha (o tipo continua o mesmo). */
  function mapText<T extends object>(obj: T, fn: (key: string, value: string) => string): T {
    const out: Record<string, unknown> = { ...(obj as Record<string, unknown>) }
    for (const [k, v] of Object.entries(obj)) if (typeof v === 'string') out[k] = fn(k, v)
    return out as T
  }

  /** Campo vazio no formulário = UNKNOWN; UNKNOWN aparece vazio para editar. */
  function forEdit(sheet: Datasheet): Datasheet {
    const blank = (k: string, v: string) => (k === 'evidence' || k === 'application' || k === 'application_evidence' || !isUnknown(v) ? v : '')
    return {
      identity: mapText(sheet.identity, blank),
      controller: mapText(sheet.controller, blank),
      host_interface: mapText(sheet.host_interface, blank),
      components: sheet.components,
    }
  }

  function forSave(sheet: Datasheet): Datasheet {
    const unk = (k: string, v: string) => (k === 'notes_pt' ? v.trim() : v.trim() === '' ? 'UNKNOWN' : v.trim())
    return {
      identity: mapText(sheet.identity, unk),
      controller: mapText(sheet.controller, unk),
      host_interface: mapText(sheet.host_interface, unk),
      components: sheet.components,
    }
  }

  function startEdit(): void {
    if (!view) return
    draft = forEdit(structuredClone($state.snapshot(view.datasheet)) as Datasheet)
    responsible = rememberedResponsible()
    reason = ''
    saveError = null
    saved = false
    editing = true
  }

  async function save(e: SubmitEvent): Promise<void> {
    e.preventDefault()
    if (!view || !draft) return
    saveError = null
    if (!RESPONSIBLE_PATTERN.test(responsible.trim())) {
      saveError = 'Informe o responsável (letras, números, espaço, ponto, @ ou hífen).'
      shake += 1
      return
    }
    if (draft.identity.name.trim().length < 2) {
      saveError = 'O nome precisa de pelo menos 2 letras.'
      shake += 1
      return
    }
    saving = true
    try {
      view = await equipmentApi.saveDatasheet(equipmentId, forSave(draft), view.config_hash, responsible.trim(), reason.trim())
      rememberResponsible(responsible.trim())
      editing = false
      saved = true
      void live.refreshPlant()
    } catch (err) {
      saveError = errorMessage(err)
      shake += 1
    } finally {
      saving = false
    }
  }

  const appPt = (a: string) => (a === 'WBF' ? 'WBF · dosador de correia' : a === 'LWF' ? 'LWF · perda de peso' : 'Não confirmada')
  const evidenceTone = (k: string) => (k === 'UNKNOWN' ? 'unknown' : k === 'HYPOTHESIS' ? 'warn' : 'info')
</script>

{#snippet value(v: string)}
  {#if isUnknown(v)}<span class="unknown">Desconhecido</span>{:else}<span class="known">{v}</span>{/if}
{/snippet}

<section class="sheet" data-testid="datasheet">
  <header class="head">
    <p class="label">{name}</p>
    <h1 class="title">Ficha técnica</h1>
    <p class="sub">
      Cada informação traz a sua evidência. O que não se sabe fica como desconhecido até alguém
      confirmar no equipamento; nada é deduzido.
    </p>
  </header>

  {#if error && !view}
    <EmptyState title="Não foi possível carregar a ficha" text={error} />
  {:else if !view}
    <div class="sk" aria-busy="true" aria-label="Carregando ficha"></div>
  {:else}
    {#if saved}<p class="notice" role="status" data-testid="datasheet-saved">Ficha salva. A versão anterior ficou no histórico da configuração.</p>{/if}

    {#if view.unknown_fields.length}
      <Card title="O que falta levantar em campo" kicker="leve esta lista na visita" testid="datasheet-unknown">
        <ul class="chips">
          {#each view.unknown_fields as f (f)}<li class="chip">{FIELD_PT[f] ?? f}</li>{/each}
        </ul>
      </Card>
    {/if}

    {#if !editing}
      <div class="cards">
        <Card title="Identificação" testid="datasheet-identity">
          <dl class="dl">
            <div><dt>Nome</dt><dd>{view.datasheet.identity.name}</dd></div>
            <div><dt>Planta</dt><dd>{@render value(view.datasheet.identity.plant)}</dd></div>
            <div><dt>Área</dt><dd>{@render value(view.datasheet.identity.area)}</dd></div>
            <div><dt>Linha</dt><dd>{@render value(view.datasheet.identity.line)}</dd></div>
            <div>
              <dt>Aplicação</dt>
              <dd>
                {appPt(view.datasheet.identity.application)}
                <Badge tone={evidenceTone(view.datasheet.identity.application_evidence)}>{KNOWLEDGE_PT[view.datasheet.identity.application_evidence as KnowledgeState]}</Badge>
              </dd>
            </div>
            <div><dt>Id</dt><dd class="mono">{view.equipment_id}</dd></div>
          </dl>
        </Card>
        <Card title="Controlador" testid="datasheet-controller">
          <dl class="dl">
            <div><dt>Fabricante</dt><dd>{@render value(view.datasheet.controller.manufacturer)}</dd></div>
            <div><dt>Modelo</dt><dd>{@render value(view.datasheet.controller.model)}</dd></div>
            <div><dt>Versão de software</dt><dd>{@render value(view.datasheet.controller.software_version)}</dd></div>
            <div><dt>KGR</dt><dd>{@render value(view.datasheet.controller.kgr)}</dd></div>
            <div><dt>Host File</dt><dd>{@render value(view.datasheet.controller.host_file)}</dd></div>
          </dl>
        </Card>
        <Card title="Interface Host" testid="datasheet-host">
          <dl class="dl">
            <div><dt>Tipo</dt><dd>{@render value(view.datasheet.host_interface.type)}</dd></div>
            <div><dt>Slot</dt><dd>{@render value(view.datasheet.host_interface.slot)}</dd></div>
            <div><dt>Modelo</dt><dd>{@render value(view.datasheet.host_interface.model)}</dd></div>
            <div><dt>Part number</dt><dd>{@render value(view.datasheet.host_interface.part_number)}</dd></div>
            <div><dt>MAC</dt><dd>{@render value(view.datasheet.host_interface.mac)}</dd></div>
            <div>
              <dt>Evidência</dt>
              <dd><Badge tone={evidenceTone(view.datasheet.host_interface.evidence)}>{KNOWLEDGE_PT[view.datasheet.host_interface.evidence]}</Badge></dd>
            </div>
          </dl>
        </Card>
        <Card title="Comunicação" kicker="configurada em KCM › Comunicação" testid="datasheet-comm">
          <dl class="dl">
            <div><dt>Driver</dt><dd>{@render value(view.profile.communication.driver)}</dd></div>
            <div><dt>Protocolo</dt><dd>{@render value(view.profile.communication.protocol)}</dd></div>
            <div><dt>Endereço</dt><dd>{@render value(String(view.profile.communication.ip))}</dd></div>
            <div><dt>Mapping</dt><dd class="mono">{view.mapping.mapping_id} · {view.mapping.readable} de {view.mapping.entries} variáveis com endereço</dd></div>
          </dl>
          <a class="link" href={href.eq(equipmentId, 'kcm/communication')}>Abrir Comunicação</a>
        </Card>
      </div>
      {#if view.datasheet.identity.notes_pt}
        <Card title="Notas" testid="datasheet-notes"><p class="notes">{view.datasheet.identity.notes_pt}</p></Card>
      {/if}
      <div class="actions">
        <button class="btn primary" type="button" onclick={startEdit} data-testid="datasheet-edit">Editar ficha</button>
        <a class="link" href={href.eq(equipmentId, 'kcm/components')}>Componentes</a>
      </div>
    {:else if draft}
      {#key shake}
        <form class="edit" class:shake={shake > 0} onsubmit={save} data-testid="datasheet-form">
          <p class="hint">Campo em branco fica como desconhecido. Só a comunicação não muda aqui.</p>
          <fieldset>
            <legend class="label">Identificação</legend>
            <div class="grid">
              <label class="field wide"><span class="label">Nome</span><input bind:value={draft.identity.name} maxlength="80" data-testid="datasheet-name" /></label>
              <label class="field"><span class="label">Planta</span><input bind:value={draft.identity.plant} maxlength="80" /></label>
              <label class="field"><span class="label">Área</span><input bind:value={draft.identity.area} maxlength="80" /></label>
              <label class="field"><span class="label">Linha</span><input bind:value={draft.identity.line} maxlength="80" /></label>
              <label class="field">
                <span class="label">Aplicação</span>
                <select bind:value={draft.identity.application}>
                  <option value="UNKNOWN">Não confirmada</option>
                  <option value="WBF">WBF · dosador de correia</option>
                  <option value="LWF">LWF · perda de peso</option>
                </select>
              </label>
              <label class="field">
                <span class="label">Evidência da aplicação</span>
                <select bind:value={draft.identity.application_evidence}>
                  {#each KNOWLEDGE_ORDER as k (k)}<option value={k}>{KNOWLEDGE_PT[k]}</option>{/each}
                </select>
              </label>
            </div>
          </fieldset>
          <fieldset>
            <legend class="label">Controlador</legend>
            <div class="grid">
              <label class="field"><span class="label">Fabricante</span><input bind:value={draft.controller.manufacturer} maxlength="80" /></label>
              <label class="field"><span class="label">Modelo</span><input bind:value={draft.controller.model} maxlength="80" /></label>
              <label class="field"><span class="label">Versão de software</span><input bind:value={draft.controller.software_version} maxlength="80" data-testid="datasheet-version" /></label>
              <label class="field"><span class="label">KGR</span><input bind:value={draft.controller.kgr} maxlength="80" /></label>
              <label class="field"><span class="label">Host File</span><input bind:value={draft.controller.host_file} maxlength="80" /></label>
            </div>
          </fieldset>
          <fieldset>
            <legend class="label">Interface Host</legend>
            <div class="grid">
              <label class="field"><span class="label">Tipo</span><input bind:value={draft.host_interface.type} maxlength="80" /></label>
              <label class="field"><span class="label">Slot</span><input bind:value={draft.host_interface.slot} maxlength="80" /></label>
              <label class="field"><span class="label">Modelo</span><input bind:value={draft.host_interface.model} maxlength="80" /></label>
              <label class="field"><span class="label">Part number</span><input bind:value={draft.host_interface.part_number} maxlength="80" /></label>
              <label class="field"><span class="label">MAC</span><input bind:value={draft.host_interface.mac} maxlength="80" /></label>
              <label class="field">
                <span class="label">Evidência</span>
                <select bind:value={draft.host_interface.evidence}>
                  {#each KNOWLEDGE_ORDER as k (k)}<option value={k}>{KNOWLEDGE_PT[k]}</option>{/each}
                </select>
              </label>
            </div>
          </fieldset>
          <label class="field"><span class="label">Notas</span><textarea rows="3" maxlength="4000" bind:value={draft.identity.notes_pt}></textarea></label>
          <div class="grid">
            <label class="field"><span class="label">Responsável</span><input bind:value={responsible} maxlength="64" autocomplete="name" data-testid="datasheet-responsible" /></label>
            <label class="field wide2"><span class="label">Motivo (opcional)</span><input bind:value={reason} maxlength="2000" placeholder="ex.: conferido na etiqueta da CPU" /></label>
          </div>
          {#if saveError}<p class="err" role="alert">{saveError}</p>{/if}
          <div class="actions">
            <button class="btn primary" type="submit" disabled={saving} data-testid="datasheet-save">{saving ? 'Salvando…' : 'Salvar ficha'}</button>
            <button class="btn ghost" type="button" onclick={() => (editing = false)} disabled={saving}>Cancelar</button>
          </div>
        </form>
      {/key}
    {/if}
  {/if}
</section>

<style>
  .sheet { display: flex; flex-direction: column; gap: var(--sp-5); }
  .head .label { margin: 0 0 var(--sp-1); }
  .title { margin: 0; color: var(--text-1); font: 600 var(--fs-h1) / var(--lh-h1) var(--font-ui); }
  @media (min-width: 1024px) {
    .title { font-size: var(--fs-display); line-height: var(--lh-display); }
  }
  .sub { margin: var(--sp-1) 0 0; max-width: 72ch; color: var(--text-2); font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  .cards { display: grid; gap: var(--sp-4); grid-template-columns: 1fr; }
  @media (min-width: 1024px) { .cards { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
  .dl { display: flex; flex-direction: column; margin: 0; }
  .dl > div {
    display: grid;
    grid-template-columns: minmax(8em, 38%) minmax(0, 1fr);
    gap: var(--sp-3);
    padding: var(--sp-2) 0;
    border-top: 1px solid var(--border-1);
  }
  .dl > div:first-child { border-top: 0; }
  dt { color: var(--text-2); font: 500 var(--fs-caption) / var(--lh-body) var(--font-ui); }
  dd { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-2); margin: 0; color: var(--text-1); font: var(--fs-body) / var(--lh-body) var(--font-ui); overflow-wrap: anywhere; }
  .unknown {
    padding: 0 8px;
    border: 1px dashed var(--border-2);
    border-radius: var(--r-pill);
    color: var(--text-2);
    font: 500 var(--fs-caption) / 20px var(--font-ui);
  }
  .mono { font-family: var(--font-mono); font-size: var(--fs-mono-sm); }
  .chips { display: flex; flex-wrap: wrap; gap: var(--sp-2); margin: 0; padding: 0; list-style: none; }
  .chip {
    padding: 2px 10px;
    border-radius: var(--r-pill);
    border: 1px dashed var(--st-warn);
    background: var(--st-warn-bg);
    color: var(--text-1);
    font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui);
    animation: pop var(--dur-base) var(--ease-out) backwards;
  }
  @keyframes pop {
    from { opacity: 0; transform: scale(0.94); }
    to { opacity: 1; transform: none; }
  }
  .notes { margin: 0; color: var(--text-1); font: var(--fs-body) / var(--lh-body) var(--font-ui); white-space: pre-line; }
  .notice { margin: 0; padding: var(--sp-3) var(--sp-4); border: 1px solid var(--st-ok); border-radius: var(--r-3); background: var(--st-ok-bg); color: var(--text-1); font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  .edit { display: flex; flex-direction: column; gap: var(--sp-4); padding: var(--sp-4); border: 1px solid var(--border-1); border-radius: var(--r-4); background: var(--surf-1); }
  .edit.shake { animation: shake 360ms var(--ease-std); }
  @keyframes shake {
    20% { transform: translateX(-6px); }
    40% { transform: translateX(5px); }
    60% { transform: translateX(-3px); }
    80% { transform: translateX(2px); }
  }
  fieldset { margin: 0; padding: 0; border: 0; min-width: 0; }
  legend { margin-bottom: var(--sp-2); padding: 0; }
  .grid { display: grid; gap: var(--sp-3); grid-template-columns: 1fr; }
  @media (min-width: 768px) {
    .grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .wide { grid-column: span 3; }
    .wide2 { grid-column: span 2; }
  }
  .field { display: flex; flex-direction: column; gap: var(--sp-1); min-width: 0; }
  input, select, textarea {
    width: 100%;
    min-height: var(--touch);
    padding: var(--sp-2);
    border: 1px solid var(--border-input);
    border-radius: var(--r-2);
    background: var(--surf-2);
    color: var(--text-1);
    font: 16px / 1.3 var(--font-ui);
  }
  input:focus-visible, select:focus-visible, textarea:focus-visible { outline: none; box-shadow: var(--focus); }
  .hint { margin: 0; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .err { margin: 0; color: var(--st-crit); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .actions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-2) var(--sp-4); }
  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: var(--touch);
    padding: 0 var(--sp-4);
    border-radius: var(--r-3);
    font: 600 var(--fs-body) / 1.2 var(--font-ui);
    cursor: pointer;
    transition: transform var(--dur-micro) var(--ease-std), background-color var(--dur-micro) var(--ease-std);
  }
  .btn:active:not(:disabled) { transform: scale(0.97); }
  .btn:disabled { opacity: 0.55; cursor: not-allowed; }
  .btn.primary { border: 1px solid var(--accent); background: var(--accent); color: var(--on-accent); }
  .btn.ghost { border: 1px solid var(--border-2); background: var(--surf-1); color: var(--text-1); }
  .btn:focus-visible { outline: none; box-shadow: var(--focus); }
  .link {
    display: inline-flex;
    align-items: center;
    min-height: var(--touch);
    color: var(--accent-text);
    font: 600 var(--fs-body) / 1.2 var(--font-ui);
    text-decoration: underline;
    text-underline-offset: 3px;
  }
  .link:focus-visible { outline: none; box-shadow: var(--focus); border-radius: var(--r-1); }
  .sk { height: 240px; border-radius: var(--r-4); background: var(--surf-2); opacity: 0.6; }
</style>
