<script lang="ts">
  /** Sistema › Equipamentos: cadastrar, abrir a ficha e a comunicação, arquivar e restaurar.
   *  Nada aqui fala com o KCM: grava a configuração da Forja, com histórico e auditoria. */
  import { onMount } from 'svelte'
  import Plus from '@lucide/svelte/icons/plus'
  import { errorMessage, type PlantCard } from '../lib/api'
  import {
    EQUIPMENT_ID,
    KNOWLEDGE_ORDER,
    KNOWLEDGE_PT,
    RESPONSIBLE_PATTERN,
    equipmentApi,
    rememberResponsible,
    rememberedResponsible,
    shown,
    suggestId,
    type ArchivedEquipment,
    type Identity,
  } from '../lib/equipment'
  import { live } from '../lib/live.svelte'
  import { href } from '../lib/router'
  import Badge from '../components/ui/Badge.svelte'
  import Card from '../components/ui/Card.svelte'
  import PageHeader from '../components/ui/PageHeader.svelte'
  import EmptyState from '../components/ui/EmptyState.svelte'

  const cards = $derived(
    [...live.plant].sort((a, b) =>
      `${a.area}|${a.line}|${a.name}`.localeCompare(`${b.area}|${b.line}|${b.name}`, 'pt-BR'),
    ),
  )

  let responsible = $state('')
  let archived = $state<ArchivedEquipment[]>([])
  let notice = $state<{ tone: 'ok' | 'crit'; text: string; link?: { href: string; label: string } } | null>(null)

  // --- novo equipamento
  let form = $state<Identity>({
    name: '',
    plant: '',
    area: '',
    line: '',
    application: 'UNKNOWN',
    application_evidence: 'UNKNOWN',
    notes_pt: '',
  })
  let newId = $state('')
  let idTouched = $state(false)
  let reason = $state('')
  let creating = $state(false)
  let createError = $state<string | null>(null)
  let shake = $state(0)
  const suggested = $derived(suggestId(form.area, form.name))
  const idValue = $derived(idTouched ? newId : suggested)
  const idOk = $derived(EQUIPMENT_ID.test(idValue))
  const responsibleOk = $derived(RESPONSIBLE_PATTERN.test(responsible.trim()))

  // --- arquivar
  let archiving = $state<string | null>(null)
  let confirmId = $state('')
  let archiveReason = $state('')
  let archiveError = $state<string | null>(null)
  let busy = $state(false)

  onMount(() => {
    responsible = rememberedResponsible()
    void loadArchived()
  })

  async function loadArchived(): Promise<void> {
    try {
      archived = (await equipmentApi.archived()).equipments
    } catch {
      archived = []
    }
  }

  function orUnknown(v: string): string {
    return v.trim() === '' ? 'UNKNOWN' : v.trim()
  }

  async function create(e: SubmitEvent): Promise<void> {
    e.preventDefault()
    createError = null
    if (form.name.trim().length < 2 || !idOk || !responsibleOk) {
      createError = !responsibleOk
        ? 'Informe o responsável (letras, números, espaço, ponto, @ ou hífen).'
        : !idOk
          ? 'O id usa só letras maiúsculas, números e _ (2 a 64 caracteres).'
          : 'Informe o nome do equipamento.'
      shake += 1
      return
    }
    creating = true
    try {
      const identity: Identity = {
        ...form,
        name: form.name.trim(),
        plant: orUnknown(form.plant),
        area: orUnknown(form.area),
        line: orUnknown(form.line),
      }
      const view = await equipmentApi.create(idValue, identity, responsible.trim(), reason.trim())
      rememberResponsible(responsible.trim())
      notice = {
        tone: 'ok',
        text: `${view.profile.name} cadastrado com o protocolo ainda não identificado e a coleta desligada.`,
        link: { href: href.eq(view.equipment_id, 'kcm/communication'), label: 'Configurar a comunicação' },
      }
      form = { name: '', plant: form.plant, area: form.area, line: form.line, application: 'UNKNOWN', application_evidence: 'UNKNOWN', notes_pt: '' }
      newId = ''
      idTouched = false
      reason = ''
      await live.refreshPlant()
    } catch (err) {
      createError = errorMessage(err)
      shake += 1
    } finally {
      creating = false
    }
  }

  function startArchive(c: PlantCard): void {
    archiving = c.id
    confirmId = ''
    archiveReason = ''
    archiveError = null
  }

  async function archive(id: string): Promise<void> {
    archiveError = null
    if (!responsibleOk) {
      archiveError = 'Informe o responsável no topo da página.'
      return
    }
    busy = true
    try {
      await equipmentApi.archive(id, confirmId.trim(), responsible.trim(), archiveReason.trim())
      rememberResponsible(responsible.trim())
      notice = { tone: 'ok', text: `${id} arquivado. O histórico continua guardado e dá para restaurar.` }
      archiving = null
      await Promise.all([live.refreshPlant(), loadArchived()])
    } catch (err) {
      archiveError = errorMessage(err)
    } finally {
      busy = false
    }
  }

  async function restore(item: ArchivedEquipment): Promise<void> {
    notice = null
    if (!responsibleOk) {
      notice = { tone: 'crit', text: 'Informe o responsável no topo da página para restaurar.' }
      return
    }
    busy = true
    try {
      await equipmentApi.restore(item.equipment_id, responsible.trim(), '')
      rememberResponsible(responsible.trim())
      notice = { tone: 'ok', text: `${item.name} voltou para a planta. A coleta segue a regra do teste somente leitura.` }
      await Promise.all([live.refreshPlant(), loadArchived()])
    } catch (err) {
      notice = { tone: 'crit', text: errorMessage(err) }
    } finally {
      busy = false
    }
  }

  function commText(c: PlantCard): string {
    if (c.driver === 'simulator') return 'Simulador'
    if (c.driver === 'UNKNOWN') return 'Protocolo não identificado'
    if (c.needs_configuration) return 'Configuração necessária'
    return c.driver === 'modbus_tcp' ? 'Modbus TCP' : c.driver === 'ethernet_ip' ? 'EtherNet/IP' : c.driver
  }
</script>

<section class="eqs" data-testid="equipments">
  <PageHeader kicker="Sistema" title="Equipamentos" lead="Cadastro dos equipamentos que a Forja observa.">
    {#snippet more()}
      <p>A comunicação de cada um é configurada em Comunicação, com teste somente leitura antes da coleta. Nada aqui fala com o KCM.</p>
    {/snippet}
  </PageHeader>

  <label class="who">
    <span class="label">Responsável pelas alterações</span>
    <input bind:value={responsible} maxlength="64" autocomplete="name" placeholder="seu nome" data-testid="eq-responsible" />
  </label>

  {#if notice}
    <p class="notice" data-tone={notice.tone} role="status" data-testid="eq-notice">
      {notice.text}
      {#if notice.link}<a class="link" href={notice.link.href}>{notice.link.label}</a>{/if}
    </p>
  {/if}

  <Card title="Na planta" kicker={`${cards.length} equipamento(s)`} testid="eq-active">
    {#if cards.length === 0}
      <EmptyState inline title="Nenhum equipamento ativo" text="Cadastre o primeiro equipamento abaixo." />
    {:else}
      <ul class="rows">
        {#each cards as c, i (c.id)}
          <li class="row" data-testid="eq-row-{c.id}" style:--i={i}>
            <div class="row-main">
              <p class="row-name">{c.name}{#if c.is_example}<Badge tone="ghost">exemplo</Badge>{/if}</p>
              <p class="row-meta">{shown(c.area)} · {shown(c.line)} · {c.application === 'UNKNOWN' ? 'aplicação não confirmada' : c.application} · <span class="mono">{c.id}</span></p>
              <p class="row-meta">{commText(c)}{#if c.data_source === 'SIMULATED'}&nbsp;· <Badge tone="sim" hatch>Simulado</Badge>{/if}</p>
            </div>
            <div class="row-actions">
              <a class="link" href={href.eq(c.id, 'kcm/datasheet')}>Ficha técnica</a>
              <a class="link" href={href.eq(c.id, 'kcm/communication')}>Comunicação</a>
              <button class="btn ghost" type="button" onclick={() => startArchive(c)} data-testid="eq-archive-{c.id}">Arquivar</button>
            </div>
            {#if archiving === c.id}
              <div class="confirm" data-testid="eq-archive-form">
                <p class="hint">
                  Arquivar tira o equipamento da planta e para a coleta. O histórico continua guardado
                  e dá para restaurar depois.
                </p>
                <label class="field">
                  <span class="label">Digite o id <span class="mono">{c.id}</span> para confirmar</span>
                  <input bind:value={confirmId} maxlength="64" autocomplete="off" data-testid="eq-archive-confirm" />
                </label>
                <label class="field">
                  <span class="label">Motivo</span>
                  <input bind:value={archiveReason} maxlength="2000" data-testid="eq-archive-reason" />
                </label>
                {#if archiveError}<p class="err" role="alert">{archiveError}</p>{/if}
                <div class="actions">
                  <button class="btn danger" type="button" disabled={busy || confirmId.trim() !== c.id || archiveReason.trim().length < 3} onclick={() => archive(c.id)} data-testid="eq-archive-submit">Arquivar equipamento</button>
                  <button class="btn ghost" type="button" onclick={() => (archiving = null)}>Cancelar</button>
                </div>
              </div>
            {/if}
          </li>
        {/each}
      </ul>
    {/if}
  </Card>

  <Card title="Novo equipamento" kicker="nasce com o protocolo não identificado" testid="eq-new">
    {#key shake}
      <form class="new" class:shake={shake > 0} onsubmit={create} data-testid="eq-new-form">
        <div class="grid">
          <label class="field wide">
            <span class="label">Nome</span>
            <input bind:value={form.name} maxlength="80" placeholder="ex.: Dosador de barrilha" data-testid="eq-new-name" />
          </label>
          <label class="field">
            <span class="label">Planta</span>
            <input bind:value={form.plant} maxlength="80" placeholder="em branco: desconhecida" />
          </label>
          <label class="field">
            <span class="label">Área</span>
            <input bind:value={form.area} maxlength="80" placeholder="em branco: desconhecida" data-testid="eq-new-area" />
          </label>
          <label class="field">
            <span class="label">Linha</span>
            <input bind:value={form.line} maxlength="80" placeholder="em branco: desconhecida" />
          </label>
          <label class="field">
            <span class="label">Aplicação</span>
            <select bind:value={form.application}>
              <option value="UNKNOWN">Não confirmada</option>
              <option value="WBF">WBF · dosador de correia</option>
              <option value="LWF">LWF · perda de peso</option>
            </select>
          </label>
          <label class="field">
            <span class="label">Evidência da aplicação</span>
            <select bind:value={form.application_evidence}>
              {#each KNOWLEDGE_ORDER as k (k)}<option value={k}>{KNOWLEDGE_PT[k]}</option>{/each}
            </select>
          </label>
          <label class="field">
            <span class="label">Id (sem espaço, maiúsculas)</span>
            <input
              value={idValue}
              oninput={(e) => {
                idTouched = true
                newId = (e.currentTarget as HTMLInputElement).value.toUpperCase()
              }}
              maxlength="64"
              class="mono-input"
              aria-invalid={!idOk && idValue !== ''}
              data-testid="eq-new-id"
            />
          </label>
          <label class="field wide">
            <span class="label">Motivo (opcional)</span>
            <input bind:value={reason} maxlength="2000" placeholder="ex.: visita de campo" />
          </label>
        </div>
        {#if createError}<p class="err" role="alert">{createError}</p>{/if}
        <div class="actions">
          <button class="btn primary" type="submit" disabled={creating} data-testid="eq-new-submit">
            <Plus size={16} aria-hidden="true" /> {creating ? 'Cadastrando…' : 'Cadastrar equipamento'}
          </button>
        </div>
      </form>
    {/key}
  </Card>

  <Card title="Arquivados" kicker="fora da planta, histórico guardado" testid="eq-archived">
    {#if archived.length === 0}
      <EmptyState inline title="Nenhum equipamento arquivado" text="Equipamento arquivado sai da planta e pode voltar quando precisar." />
    {:else}
      <ul class="rows" data-testid="eq-archived-list">
        {#each archived as a (a.equipment_id)}
          <li class="row">
            <div class="row-main">
              <p class="row-name">{a.name}</p>
              <p class="row-meta">{a.display_path} · <span class="mono">{a.equipment_id}</span></p>
            </div>
            <div class="row-actions">
              <button class="btn ghost" type="button" disabled={busy} onclick={() => restore(a)} data-testid="eq-restore-{a.equipment_id}">Restaurar</button>
            </div>
          </li>
        {/each}
      </ul>
    {/if}
  </Card>
</section>

<style>
  .eqs { display: flex; flex-direction: column; gap: var(--sp-5); }
  .who, .field { display: flex; flex-direction: column; gap: var(--sp-1); min-width: 0; }
  .who { max-width: 360px; }
  input, select {
    width: 100%;
    min-height: var(--touch);
    padding: var(--sp-2);
    border: 1px solid var(--border-input);
    border-radius: var(--r-2);
    background: var(--surf-2);
    color: var(--text-1);
    font: 16px / 1.3 var(--font-ui);
  }
  input:focus-visible, select:focus-visible { outline: none; box-shadow: var(--focus); }
  input[aria-invalid='true'] { border-color: var(--st-crit); }
  .mono-input { font-family: var(--font-mono); }
  .notice {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--sp-2) var(--sp-4);
    margin: 0;
    padding: var(--sp-3) var(--sp-4);
    border-radius: var(--r-3);
    border: 1px solid var(--st-ok);
    background: var(--st-ok-bg);
    color: var(--text-1);
    font: var(--fs-body) / var(--lh-body) var(--font-ui);
    animation: rise var(--dur-screen) var(--ease-out);
  }
  .notice[data-tone='crit'] { border-color: var(--st-crit); background: var(--st-crit-bg); }
  @keyframes rise {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: none; }
  }
  .rows { display: flex; flex-direction: column; margin: 0; padding: 0; list-style: none; }
  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--sp-2) var(--sp-4);
    padding: var(--sp-3) 0;
    border-top: 1px solid var(--border-1);
    animation: rise var(--dur-screen) var(--ease-out) backwards;
    animation-delay: calc(var(--i, 0) * var(--stagger));
  }
  .row:first-child { border-top: 0; }
  .row-main { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1 1 260px; }
  .row-name { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-2); margin: 0; color: var(--text-1); font: 600 var(--fs-body) / var(--lh-body) var(--font-ui); }
  .row-meta { margin: 0; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); overflow-wrap: anywhere; }
  .mono { font-family: var(--font-mono); }
  .row-actions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-2) var(--sp-4); }
  .confirm {
    flex: 1 1 100%;
    display: flex;
    flex-direction: column;
    gap: var(--sp-2);
    padding: var(--sp-3);
    border: 1px solid var(--st-crit);
    border-radius: var(--r-3);
    background: var(--st-crit-bg);
    animation: rise var(--dur-base) var(--ease-out);
  }
  .grid { display: grid; gap: var(--sp-3); grid-template-columns: 1fr; }
  @media (min-width: 768px) {
    .grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .wide { grid-column: span 3; }
  }
  .new.shake { animation: shake 360ms var(--ease-std); }
  @keyframes shake {
    20% { transform: translateX(-6px); }
    40% { transform: translateX(5px); }
    60% { transform: translateX(-3px); }
    80% { transform: translateX(2px); }
  }
  .actions { display: flex; flex-wrap: wrap; gap: var(--sp-2); margin-top: var(--sp-3); }
  .hint { margin: 0; color: var(--text-1); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .err { margin: var(--sp-2) 0 0; color: var(--st-crit); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
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
    transition: background-color var(--dur-micro) var(--ease-std), transform var(--dur-micro) var(--ease-std);
  }
  .btn:active:not(:disabled) { transform: scale(0.97); }
  .btn:disabled { opacity: 0.55; cursor: not-allowed; }
  .btn.primary { border: 1px solid var(--accent); background: var(--accent); color: var(--on-accent); }
  .btn.ghost { border: 1px solid var(--border-2); background: var(--surf-1); color: var(--text-1); }
  .btn.ghost:hover:not(:disabled) { background: var(--surf-2); }
  .btn.danger { border: 1px solid var(--st-crit); background: var(--st-crit-bg); color: var(--st-crit); }
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
</style>
