<script lang="ts">
  /** KCM › Comunicação, numa coluna: protocolo, endereço, teste somente leitura e salvar e ativar.
   *  Tempos, variáveis (mapping) e o detalhe do teste ficam fechados. Tudo aqui configura a FORJA
   *  e LÊ o KCM: nada envia comando ao equipamento. Protocolo nunca é escolhido sozinho. */
  import { untrack } from 'svelte'
  import Check from '@lucide/svelte/icons/check'
  import CircleHelp from '@lucide/svelte/icons/circle-help'
  import FlaskConical from '@lucide/svelte/icons/flask-conical'
  import Radio from '@lucide/svelte/icons/radio'
  import RefreshCw from '@lucide/svelte/icons/refresh-cw'
  import ShieldCheck from '@lucide/svelte/icons/shield-check'
  import { errorMessage, isUsable, type EquipmentProfile } from '../lib/api'
  import {
    clone,
    commApi,
    isRealDriver,
    PROTOCOL_DEFAULT_PORT,
    type CommLogEntry,
    type CommView,
    type DriverName,
    type MappingDto,
    type ReadTestResult,
    type ValidationResult,
  } from '../lib/comm'
  import { fmtDateTime, fmtNumber } from '../lib/format'
  import { live } from '../lib/live.svelte'
  import { href } from '../lib/router'
  import { tagCatalog } from '../lib/tagmeta.svelte'
  import MappingEditor from '../components/comm/MappingEditor.svelte'
  import ReadTestPanel from '../components/comm/ReadTestPanel.svelte'
  import Disclosure from '../components/ui/Disclosure.svelte'
  import EmptyState from '../components/ui/EmptyState.svelte'

  let { equipmentId }: { equipmentId: string } = $props()

  const LS_USER = 'forja.responsavel'
  function readUser(): string {
    try {
      return localStorage.getItem(LS_USER) ?? ''
    } catch {
      return ''
    }
  }

  let view = $state<CommView | null>(null)
  let comm = $state<EquipmentProfile['communication'] | null>(null)
  let mapping = $state<MappingDto | null>(null)
  let validation = $state<ValidationResult | null>(null)
  let test = $state<ReadTestResult | null>(null)
  /** Chave de leitura da configuração testada nesta tela (ver `readingKeyOf`). */
  let testedKey = $state<string | null>(null)
  let kcm = $state<Record<string, string>>({})
  let user = $state(readUser())
  let reason = $state('')
  let busy = $state<'' | 'load' | 'validate' | 'test' | 'save' | 'collection'>('load')
  let notice = $state<{ tone: 'ok' | 'warn' | 'crit'; text: string } | null>(null)
  let loadError = $state<string | null>(null)
  let log = $state<CommLogEntry[]>([])

  const driver = $derived((comm?.driver ?? 'UNKNOWN') as DriverName)
  const real = $derived(isRealDriver(driver))
  const name = $derived(view?.name ?? live.cardOf(equipmentId)?.name ?? equipmentId)
  /** Mapping da leitura: simulador usa o próprio (não editável); real usa o editável. */
  const readingMapping = $derived<MappingDto | null>(
    !view || !mapping ? null : real ? { ...mapping, driver } : view.mapping,
  )
  const candidate = $derived<EquipmentProfile | null>(
    view && comm && readingMapping
      ? { ...view.profile, communication: comm, mapping_profile: readingMapping.mapping_id }
      : null,
  )
  const dirtyComm = $derived(
    !!view && !!comm &&
      (JSON.stringify(comm) !== JSON.stringify(view.profile.communication) ||
        (readingMapping?.mapping_id ?? '') !== view.profile.mapping_profile),
  )
  const dirtyMapping = $derived(
    !!view && !!mapping && real &&
      (!view.editable_mapping_exists ||
        JSON.stringify({ ...mapping, driver }) !== JSON.stringify(view.editable_mapping)),
  )
  const dirty = $derived(dirtyComm || dirtyMapping)
  const userOk = $derived(/^[\w .@-]{1,64}$/.test(user.trim()))
  const collectionOn = $derived(!!view && view.collection.enabled && !view.collection.blocked)
  const canActivate = $derived(
    !!view && !collectionOn && !dirty &&
      (driver === 'simulator' || (view.last_test_matches && view.last_test?.success === true)),
  )

  /** O que muda a leitura: a comunicação (sem o liga e desliga da coleta) e o mapping (sem as
   *  conferências registradas). Diz se o teste feito nesta tela ainda vale para o que está nela.
   *  Conservador: qualquer outra mudança pede teste de novo; quem decide no fim é o servidor. */
  function readingKeyOf(c: EquipmentProfile['communication'] | null, m: MappingDto | null): string {
    if (!c || !m) return ''
    const commPart: Record<string, unknown> = { ...c }
    delete commPart.collection_enabled
    const entries = m.entries.map((e) => {
      const rest: Record<string, unknown> = { ...e }
      delete rest.validation
      delete rest.confirmed
      return rest
    })
    return JSON.stringify({ comm: commPart, mapping: { ...m, entries } })
  }
  const readingKey = $derived(readingKeyOf(comm, readingMapping))
  const testedOk = $derived(!!test && test.success && testedKey === readingKey)

  /** Botão único do passo 4. */
  type Action = 'save-activate' | 'save' | 'activate' | 'none'
  const action = $derived.by<Action>(() => {
    if (!view) return 'none'
    if (dirty) {
      if (driver === 'UNKNOWN') return 'save'
      return driver === 'simulator' || testedOk ? 'save-activate' : 'save'
    }
    return canActivate ? 'activate' : 'none'
  })
  const actionLabel = $derived(
    action === 'save-activate'
      ? 'Salvar e ativar a coleta'
      : action === 'save'
        ? 'Salvar sem ativar'
        : action === 'activate'
          ? 'Ativar a coleta'
          : collectionOn
            ? 'Coleta ativa'
            : 'Nada a salvar',
  )
  const actionHint = $derived.by<string | null>(() => {
    if (action !== 'none' && !userOk) return 'Informe o responsável: ele vai para a auditoria.'
    switch (action) {
      case 'save-activate':
      case 'activate':
        return 'Liga a leitura periódica da Forja. Nada é enviado ao KCM.'
      case 'save':
        return driver === 'UNKNOWN'
          ? 'Sem protocolo, a coleta fica pausada.'
          : 'Sem um teste bem-sucedido desta configuração, a coleta fica pausada.'
      default:
        return !collectionOn && real ? 'Teste a leitura (passo 3) para poder ativar.' : null
    }
  })

  const addressOk = $derived(
    !!comm && comm.ip !== 'UNKNOWN' && comm.port !== 'UNKNOWN' &&
      (driver !== 'modbus_tcp' || comm.unit_id !== 'UNKNOWN'),
  )
  const testDone = $derived(
    testedOk || (!dirty && !!view?.last_test_matches && view?.last_test?.success === true),
  )

  /** "Variáveis (mapping) · 12 variáveis · 3 sem endereço". */
  const mappingSummary = $derived.by(() => {
    if (!mapping) return 'Variáveis (mapping)'
    const total = mapping.entries.length
    const missing = mapping.entries.filter((e) => e.protocol_address === 'UNKNOWN').length
    const parts = [`Variáveis (mapping) · ${total} ${total === 1 ? 'variável' : 'variáveis'}`]
    if (missing) parts.push(`${missing} sem endereço`)
    return parts.join(' · ')
  })

  /** Resultado do teste numa frase. Conta só as variáveis com leitura utilizável. */
  function testSentence(r: ReadTestResult): string {
    if (!r.success) return `${r.final_pt ?? 'O teste falhou'}${r.error_pt ? `: ${r.error_pt}` : ''}.`
    const total = r.detail.tags.length
    const read = r.detail.tags.filter((t) => t.value != null && t.quality != null && isUsable(t.quality)).length
    const time = r.latency_ms != null ? ` em ${fmtNumber(r.latency_ms, 0)} ms` : ''
    if (total === 0) return `Leitura obtida${time}.`
    return `Leu ${read} de ${total} ${total === 1 ? 'variável' : 'variáveis'}${time}.`
  }

  function adopt(next: CommView, keepTest = false): void {
    view = next
    comm = clone(next.profile.communication)
    mapping = clone(next.editable_mapping)
    validation = null
    if (!keepTest) {
      test = null
      testedKey = null
      kcm = {}
    }
  }

  async function load(id: string): Promise<void> {
    busy = 'load'
    try {
      await tagCatalog.ensure()
      const v = await commApi.view(id)
      if (id !== equipmentId) return
      adopt(v)
      loadError = null
      void loadLog(id)
    } catch (err) {
      if (id === equipmentId) loadError = errorMessage(err)
    } finally {
      if (id === equipmentId) busy = ''
    }
  }

  async function loadLog(id: string): Promise<void> {
    try {
      log = (await commApi.log(id, 50)).entries
    } catch {
      log = []
    }
  }

  $effect(() => {
    const id = equipmentId
    untrack(() => void load(id))
  })

  // estado de conexão e coleta mudam sozinhos: atualiza a cada 5 s sem tocar no que está em edição
  $effect(() => {
    const id = equipmentId
    const timer = window.setInterval(async () => {
      if (busy !== '' || !view) return
      try {
        const fresh = await commApi.view(id)
        if (id === equipmentId && busy === '') view = fresh
      } catch {
        // sem resposta: o banner do Edge cuida do aviso
      }
    }, 5000)
    return () => clearInterval(timer)
  })

  const SAVED_DRIVER_PT: Record<string, string> = {
    simulator: 'Simulador',
    modbus_tcp: 'Modbus TCP',
    ethernet_ip: 'EtherNet/IP',
    UNKNOWN: 'protocolo não identificado',
  }

  function rememberUser(): void {
    try {
      localStorage.setItem(LS_USER, user.trim())
    } catch {
      // armazenamento indisponível: fica só nesta tela
    }
  }

  function choose(next: DriverName): void {
    if (!comm || !view) return
    const saved = view.profile.communication
    comm.driver = next
    if (next === 'simulator') {
      comm.protocol = saved.driver === 'simulator' ? saved.protocol : 'UNKNOWN'
      comm.options = saved.driver === 'simulator' ? clone(saved.options) : { scenario: 'NORMAL_OPERATION', seed: 1 }
    } else {
      comm.protocol = next === 'UNKNOWN' ? 'UNKNOWN' : next
      if (saved.driver === 'simulator') comm.options = {}
    }
    validation = null
    test = null
    testedKey = null
  }

  function textOrUnknown(value: string): string {
    const t = value.trim()
    return t === '' ? 'UNKNOWN' : t
  }

  function intOrUnknown(value: string): number | string {
    const t = value.trim()
    if (t === '') return 'UNKNOWN'
    const n = Number(t)
    return Number.isInteger(n) ? n : t
  }

  async function runValidate(): Promise<void> {
    if (!comm || !readingMapping) return
    busy = 'validate'
    notice = null
    try {
      validation = await commApi.validate(equipmentId, comm, readingMapping)
    } catch (err) {
      notice = { tone: 'crit', text: errorMessage(err) }
    } finally {
      busy = ''
    }
  }

  async function runTest(): Promise<void> {
    if (!candidate || !readingMapping) return
    busy = 'test'
    notice = null
    const key = readingKey
    rememberUser()
    try {
      test = await commApi.testRead(candidate, readingMapping, user.trim())
      testedKey = test.success ? key : null
      kcm = {}
      if (view) view = await commApi.view(equipmentId).then((v) => ({ ...v })).catch(() => view)
    } catch (err) {
      test = null
      testedKey = null
      notice = { tone: 'crit', text: errorMessage(err) }
    } finally {
      busy = ''
    }
  }

  function register(tag: string, matched: boolean, forja: number | null, kcmValue: string): void {
    if (!mapping) return
    const entry = mapping.entries.find((e) => e.semantic_tag === tag)
    if (!entry) return
    const known =
      entry.protocol_address !== 'UNKNOWN' &&
      entry.datatype !== 'UNKNOWN' &&
      entry.endianness !== 'UNKNOWN' &&
      entry.source !== 'UNKNOWN'
    if (matched && !known) {
      notice = {
        tone: 'warn',
        text: `${tagCatalog.meta(tag).label_pt}: informe tipo, ordem dos bytes e de onde veio o endereço antes de validar.`,
      }
      return
    }
    entry.validation = {
      validated_at_utc: new Date().toISOString(),
      validated_by: user.trim() || 'não informado',
      forja_value: forja ?? '',
      kcm_value: kcmValue,
      matched,
      note_pt: '',
    }
    entry.confirmed = matched
    notice = {
      tone: matched ? 'ok' : 'warn',
      text: `${tagCatalog.meta(tag).label_pt}: conferência registrada (${matched ? 'confere' : 'diverge'}). Salve para gravar.`,
    }
  }

  /** Grava o mapping e a comunicação que mudaram. Cada gravação vai para a auditoria. */
  async function persist(start: CommView): Promise<CommView> {
    let current = start
    if (!comm || !readingMapping) return current
    if (dirtyMapping && mapping) {
      current = await commApi.saveMapping(
        equipmentId,
        { ...mapping, driver },
        start.editable_mapping_exists ? start.editable_mapping.version : null,
        user.trim(),
        reason.trim(),
      )
    }
    const needConfig =
      JSON.stringify(comm) !== JSON.stringify(current.profile.communication) ||
      readingMapping.mapping_id !== current.profile.mapping_profile
    if (needConfig) {
      current = await commApi.saveConfig(equipmentId, {
        communication: { ...comm, collection_enabled: current.profile.communication.collection_enabled },
        mapping_profile: readingMapping.mapping_id,
        base_hash: current.config_hash,
        user: user.trim(),
        reason_pt: reason.trim(),
      })
    }
    return current
  }

  /** O botão único: salva o que mudou e, quando pode, ativa a coleta. Se salvar der certo e a
   *  ativação for recusada, a tela diz exatamente isso. */
  async function apply(): Promise<void> {
    if (!view || !userOk || action === 'none') return
    const activate = action === 'save-activate' || action === 'activate'
    const willSave = dirty
    busy = 'save'
    notice = null
    rememberUser()
    let current = view
    try {
      if (willSave) {
        current = await persist(current)
        adopt(current, true)
      }
    } catch (err) {
      notice = { tone: 'crit', text: `Não foi salvo: ${errorMessage(err)}` }
      busy = ''
      return
    }
    try {
      if (activate && (!current.collection.enabled || current.collection.blocked)) {
        busy = 'collection'
        current = await commApi.setCollection(equipmentId, true, user.trim(), reason.trim())
        adopt(current, true)
      }
      notice = {
        tone: 'ok',
        text: activate
          ? willSave
            ? 'Configuração salva e coleta ativada: a Forja passa a ler o KCM.'
            : 'Coleta ativada: a Forja passa a ler o KCM.'
          : current.collection_paused_by_change
            ? 'Configuração salva. A coleta foi pausada porque a leitura mudou: teste e ative de novo.'
            : 'Configuração salva. A coleta continua pausada.',
      }
      reason = ''
    } catch (err) {
      notice = {
        tone: 'warn',
        text: `${willSave ? 'Configuração salva. ' : ''}A coleta não foi ativada: ${errorMessage(err)}`,
      }
    } finally {
      busy = ''
      void loadLog(equipmentId)
    }
  }

  async function pause(): Promise<void> {
    if (!userOk) return
    busy = 'collection'
    notice = null
    rememberUser()
    try {
      adopt(await commApi.setCollection(equipmentId, false, user.trim(), reason.trim()), true)
      notice = { tone: 'ok', text: 'Coleta pausada: a Forja parou de ler este equipamento.' }
      void loadLog(equipmentId)
    } catch (err) {
      notice = { tone: 'crit', text: errorMessage(err) }
    } finally {
      busy = ''
    }
  }

  const PROTOCOLS: Array<{ id: DriverName; title: string }> = [
    { id: 'modbus_tcp', title: 'Modbus TCP' },
    { id: 'ethernet_ip', title: 'EtherNet/IP' },
    { id: 'simulator', title: 'Simulador' },
    { id: 'UNKNOWN', title: 'Ainda não sei' },
  ]
</script>

{#snippet ball(done: boolean, n: number)}
  <span class="ball num" class:done aria-hidden="true">
    {#if done}<span class="pop"><Check size={16} strokeWidth={3} /></span>{:else}{n}{/if}
  </span>
{/snippet}

<section class="comm" data-testid="communication">
  <header class="head">
    <div>
      <p class="label">{name}</p>
      <h1 class="title">Comunicação com o KCM</h1>
    </div>
    {#if view}
      <div class="state" data-testid="comm-state" data-code={view.state.code} data-tone={view.state.tone}>
        <span class="dot" aria-hidden="true"></span>
        <span>{view.state.label_pt}</span>
      </div>
    {/if}
  </header>

  <p class="safety" data-testid="comm-safety">
    <ShieldCheck size={18} aria-hidden="true" />
    Somente leitura: a Forja só lê o KCM, no endereço que você informar.
  </p>

  {#if loadError}
    <EmptyState title="Não foi possível carregar a comunicação" text={loadError} />
  {:else if !view || !comm || !mapping}
    <div class="sk" aria-busy="true" aria-label="Carregando"></div>
  {:else}
    {#if notice}
      <p class="notice" data-tone={notice.tone} role="status" data-testid="comm-notice">{notice.text}</p>
    {/if}

    <ol class="steps">
      <li class="step" class:done={driver !== 'UNKNOWN'} data-testid="comm-step-protocol">
        <h2 class="step-title" id="comm-h-protocol">{@render ball(driver !== 'UNKNOWN', 1)} Protocolo</h2>
        <div class="protocols" role="radiogroup" aria-labelledby="comm-h-protocol">
          {#each PROTOCOLS as p (p.id)}
            {@const info = p.id === 'UNKNOWN' ? null : view.drivers[p.id]}
            <label class="proto" class:on={driver === p.id} data-testid={`protocol-${p.id}`}>
              <input type="radio" name="protocol" class="sr" checked={driver === p.id} onchange={() => choose(p.id)} />
              <span class="proto-name">{p.title}</span>
              <span class="proto-state" data-state={info?.state ?? 'UNKNOWN'}>{info ? info.state_pt : 'Fica desconhecido'}</span>
            </label>
          {/each}
        </div>
        {#if driver === 'UNKNOWN'}
          <p class="unknown" data-testid="protocol-unknown">
            <CircleHelp size={18} aria-hidden="true" />
            <span>
              <b>Protocolo ainda não identificado.</b> Sem protocolo, nada é lido. Confirme no KCM
              (menu de versões, placa Host) e na etiqueta do módulo Anybus.
            </span>
          </p>
        {/if}
      </li>

      {#if real}
        <li class="step" class:done={addressOk} data-testid="comm-step-address">
          <h2 class="step-title">{@render ball(addressOk, 2)} Endereço</h2>
          <div class="fields">
            <label class="wide">IP do KCM
              <input type="text" inputmode="decimal" autocomplete="off" placeholder="ex.: [IP do módulo Host]" value={comm.ip === 'UNKNOWN' ? '' : comm.ip} oninput={(e) => comm && (comm.ip = textOrUnknown(e.currentTarget.value))} data-testid="comm-ip" />
            </label>
            <label>Porta
              <input type="number" min="1" max="65535" inputmode="numeric" value={comm.port === 'UNKNOWN' ? '' : comm.port} oninput={(e) => comm && (comm.port = intOrUnknown(e.currentTarget.value))} data-testid="comm-port" />
            </label>
            {#if driver === 'modbus_tcp'}
              <label>Unit ID
                <input type="number" min="0" max="255" inputmode="numeric" value={comm.unit_id === 'UNKNOWN' ? '' : comm.unit_id} oninput={(e) => comm && (comm.unit_id = intOrUnknown(e.currentTarget.value))} data-testid="comm-unit" />
              </label>
            {/if}
          </div>
          {#if PROTOCOL_DEFAULT_PORT[driver]}
            <button type="button" class="link" onclick={() => comm && (comm.port = PROTOCOL_DEFAULT_PORT[driver] ?? comm.port)} data-testid="comm-default-port">
              Usar a porta padrão do protocolo ({PROTOCOL_DEFAULT_PORT[driver]})
            </button>
          {/if}
          <Disclosure summary="Avançado: tempos e leitura em bloco" testid="comm-advanced">
            <div class="fields advanced">
              <label>Tempo de espera (s)
                <input type="number" min="0.1" max="60" step="0.1" inputmode="decimal" bind:value={comm.timeout_s} data-testid="comm-timeout" />
              </label>
              <label>Intervalo entre leituras (s)
                <input type="number" min="0.25" max="3600" step="0.25" inputmode="decimal" bind:value={comm.poll_interval_s} data-testid="comm-poll" />
              </label>
              <label>Valor antigo depois de (s)
                <input type="number" min="1" step="1" inputmode="decimal" bind:value={comm.stale_after_s} />
              </label>
              {#if driver === 'modbus_tcp'}
                <label class="check">
                  <input type="checkbox" class="sr" checked={comm.options['block_reads'] !== false} onchange={(e) => comm && (comm.options = { ...comm.options, block_reads: e.currentTarget.checked })} />
                  <span class="box" aria-hidden="true"><Check size={14} strokeWidth={3} /></span>
                  Ler registradores vizinhos em bloco (menos requisições)
                </label>
              {/if}
            </div>
          </Disclosure>
        </li>

        <li class="step quiet" data-testid="comm-step-mapping">
          <Disclosure summary={mappingSummary} testid="comm-mapping">
            <div class="mapping">
              {#if view.mapping_shared}
                <p class="hint">
                  Este equipamento ainda usa o mapping do simulador. Para {driver === 'modbus_tcp' ? 'Modbus TCP' : 'EtherNet/IP'}
                  a Forja usa o mapping próprio dele, <b class="num">{mapping.mapping_id}</b>{view.editable_mapping_exists ? '' : ' (novo, todo em "não definido")'}.
                </p>
              {/if}
              <MappingEditor bind:mapping={mapping} {driver} />
              <div class="actions">
                <button type="button" class="btn ghost" disabled={busy !== ''} onclick={runValidate} data-testid="comm-validate">
                  Conferir configuração (sem conectar)
                </button>
              </div>
              {#if validation}
                <div class="validation" data-ok={validation.ok} data-testid="comm-validation">
                  {#each validation.errors as e, i (i)}<p class="err">{e}</p>{/each}
                  {#each validation.warnings as w, i (i)}<p class="warnline">{w}</p>{/each}
                  {#if validation.ok}
                    <p class="okline">
                      Configuração coerente: {validation.requests_per_cycle} requisição(ões) de leitura por ciclo.
                    </p>
                  {/if}
                </div>
              {/if}
            </div>
          </Disclosure>
        </li>
      {:else if driver === 'simulator'}
        <li class="step done" data-testid="comm-step-simulator">
          <h2 class="step-title">{@render ball(true, 2)} Endereço</h2>
          <p class="hint">O simulador não precisa de endereço. Nenhum valor representa um KCM real.</p>
        </li>
      {/if}

      <li class="step" class:done={testDone} data-testid="comm-step-test">
        <h2 class="step-title">{@render ball(testDone, 3)} Testar, só lendo</h2>
        <button type="button" class="btn primary big" disabled={busy !== '' || driver === 'UNKNOWN'} onclick={runTest} data-testid="comm-test">
          {#if busy === 'test'}
            <span class="spin" aria-hidden="true"><RefreshCw size={18} /></span> Lendo…
          {:else}
            <FlaskConical size={18} aria-hidden="true" /> Testar (somente leitura)
          {/if}
        </button>
        {#if test}
          {#key test}
            <p class="verdict" data-ok={test.success} role="status" data-testid="comm-test-summary">
              {#if test.success}<span class="pop"><Check size={18} strokeWidth={3} aria-hidden="true" /></span>{/if}
              {testSentence(test)}
            </p>
          {/key}
          <Disclosure summary="Ver o que foi lido e comparar com a tela do KCM" testid="comm-test-detail">
            <ReadTestPanel result={test} bind:kcm canRegister={real} onregister={register} />
          </Disclosure>
          {#if test.success}
            <a class="next" href={href.eq(equipmentId, 'kcm/commissioning')} data-testid="comm-next-commissioning">
              Próximo passo: conferir os valores na tela do KCM (Comissionamento)
            </a>
          {/if}
        {/if}
      </li>

      <li class="step" class:done={collectionOn && !dirty} data-testid="comm-step-save">
        <h2 class="step-title">{@render ball(collectionOn && !dirty, 4)} Salvar e ativar a coleta</h2>
        <p class="collection" data-on={collectionOn} data-blocked={view.collection.blocked} data-testid="comm-collection">
          <Radio size={18} aria-hidden="true" /> {view.collection.label_pt}
          <span class="in-use">· em uso: {SAVED_DRIVER_PT[view.profile.communication.driver] ?? view.profile.communication.driver}</span>
        </p>
        <div class="fields">
          <label>Responsável (vai para a auditoria)
            <input type="text" maxlength="64" autocomplete="name" placeholder="nome do técnico" bind:value={user} data-testid="comm-user" />
          </label>
          <label class="wide">Motivo da alteração
            <input type="text" maxlength="200" placeholder="ex.: protocolo confirmado no KCM" bind:value={reason} data-testid="comm-reason" />
          </label>
        </div>
        <div class="actions">
          <button type="button" class="btn primary" disabled={busy !== '' || action === 'none' || !userOk} onclick={apply} data-testid="comm-save" data-action={action}>
            {busy === 'save' ? 'Salvando…' : busy === 'collection' ? 'Ativando…' : actionLabel}
          </button>
          {#if collectionOn}
            <button type="button" class="btn ghost" disabled={busy !== '' || !userOk} onclick={pause} data-testid="comm-collection-off">
              Pausar coleta
            </button>
          {/if}
        </div>
        {#if actionHint}<p class="hint" data-testid="comm-action-hint">{actionHint}</p>{/if}
      </li>
    </ol>

    <Disclosure summary="Detalhes técnicos e log de conexão" testid="comm-tech">
      <dl class="tech">
        <div><dt>Conexão</dt><dd>{view.runtime.connection_pt}</dd></div>
        <div><dt>Latência</dt><dd class="num">{view.runtime.latency_ms != null ? `${fmtNumber(view.runtime.latency_ms, 1)} ms` : '—'}</dd></div>
        <div><dt>Falhas seguidas</dt><dd class="num">{view.runtime.consecutive_errors}</dd></div>
        {#if view.last_test}
          <div><dt>Último teste</dt><dd>{view.last_test.success ? 'leitura obtida' : 'falhou'} · {fmtDateTime(view.last_test.ts_utc)}{view.last_test_matches ? '' : ' (outra configuração)'}</dd></div>
        {/if}
        <div><dt>Driver</dt><dd class="num">{view.profile.communication.driver}</dd></div>
        <div><dt>Protocolo salvo</dt><dd class="num">{view.profile.communication.protocol}</dd></div>
        <div><dt>Mapping em uso</dt><dd class="num">{view.profile.mapping_profile} v{view.mapping.version}</dd></div>
        <div><dt>Impressão da configuração</dt><dd class="num">{view.fingerprint.slice(0, 16)}…</dd></div>
        <div><dt>Hash do perfil</dt><dd class="num">{view.config_hash.slice(0, 16)}…</dd></div>
      </dl>
      {#if log.length}
        <ol class="log">
          {#each log as entry, i (i)}
            <li data-level={entry.level}><span class="num">{fmtDateTime(entry.ts_utc)}</span> {entry.message_pt}</li>
          {/each}
        </ol>
      {:else}
        <p class="hint">Sem registros de conexão ainda.</p>
      {/if}
    </Disclosure>
  {/if}
</section>

<style>
  .comm { display: flex; flex-direction: column; gap: var(--sp-4); min-width: 0; max-width: 820px; }
  .head { display: flex; align-items: flex-end; justify-content: space-between; gap: var(--sp-3) var(--sp-4); flex-wrap: wrap; }
  .head .label { margin: 0 0 var(--sp-1); }
  .title { margin: 0; font: 600 var(--fs-h1) / var(--lh-h1) var(--font-ui); color: var(--text-1); }
  @media (min-width: 1024px) { .title { font-size: var(--fs-display); line-height: var(--lh-display); } }
  .state { display: inline-flex; align-items: center; gap: var(--sp-2); min-height: var(--touch); padding: 0 var(--sp-4); border: 1px solid var(--border-2); border-radius: var(--r-pill); color: var(--text-1); font: 600 var(--fs-body) / 1 var(--font-ui); }
  .state .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--text-3); }
  .state[data-tone='ok'] { border-color: var(--st-ok); } .state[data-tone='ok'] .dot { background: var(--st-ok); }
  .state[data-tone='warn'] { border-color: var(--st-warn); } .state[data-tone='warn'] .dot { background: var(--st-warn); }
  .state[data-tone='crit'] { border-color: var(--st-crit); } .state[data-tone='crit'] .dot { background: var(--st-crit); }
  .state[data-tone='sim'] { border-color: var(--q-sim); } .state[data-tone='sim'] .dot { background: var(--q-sim); }
  .safety { display: flex; align-items: flex-start; gap: var(--sp-2); margin: 0; color: var(--text-2); font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  .safety :global(svg) { flex: none; margin-top: 1px; color: var(--st-ok); }
  .notice { margin: 0; padding: var(--sp-3) var(--sp-4); border-radius: var(--r-3); font: 500 var(--fs-body) / var(--lh-body) var(--font-ui); animation: rise var(--dur-base) var(--ease-out) both; }
  .notice[data-tone='ok'] { background: var(--st-ok-bg); color: var(--st-ok); }
  .notice[data-tone='warn'] { background: var(--st-warn-bg); color: var(--st-warn); }
  .notice[data-tone='crit'] { background: var(--st-crit-bg); color: var(--st-crit); }
  .sk { height: 360px; border-radius: var(--r-4); background: var(--surf-2); opacity: 0.6; }

  .steps { display: flex; flex-direction: column; gap: var(--sp-3); margin: 0; padding: 0; list-style: none; }
  .step {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--sp-3);
    min-width: 0;
    padding: var(--sp-4);
    border: 1px solid var(--border-1);
    border-radius: var(--r-4);
    background: var(--surf-1);
    transition: border-color var(--dur-base) var(--ease-std);
    animation: rise var(--dur-screen) var(--ease-out) both;
  }
  .step > :global(*) { max-width: 100%; }
  .step.done { border-color: color-mix(in srgb, var(--st-ok) 45%, var(--border-1)); }
  .step.quiet { padding: var(--sp-2) var(--sp-4); border-style: dashed; border-color: var(--border-2); background: transparent; }
  .step-title { display: flex; align-items: center; gap: var(--sp-2); margin: 0; color: var(--text-1); font: 600 var(--fs-body-lg) / var(--lh-body-lg) var(--font-ui); }
  .ball {
    display: grid;
    place-items: center;
    flex: none;
    width: 28px;
    height: 28px;
    border: 1px solid var(--border-2);
    border-radius: var(--r-pill);
    color: var(--text-2);
    font: 600 14px / 1 var(--font-mono);
    transition: background-color var(--dur-base) var(--ease-std), border-color var(--dur-base) var(--ease-std);
  }
  .ball.done { border-color: var(--st-ok); background: var(--st-ok); color: var(--on-accent); }
  .pop { display: inline-grid; place-items: center; animation: pop var(--dur-spring) var(--ease-spring) both; }

  .protocols { display: grid; gap: var(--sp-2); width: 100%; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); }
  .proto { position: relative; display: flex; flex-direction: column; gap: 2px; min-height: 56px; padding: var(--sp-2) var(--sp-3); border: 1px solid var(--border-2); border-radius: var(--r-3); background: var(--surf-2); cursor: pointer; transition: border-color var(--dur-micro) var(--ease-out), background-color var(--dur-micro) var(--ease-out), transform var(--dur-micro) var(--ease-out); }
  .proto:hover { border-color: var(--border-input); }
  .proto:active { transform: scale(0.99); }
  .proto.on { border-color: var(--accent); background: var(--accent-soft); }
  .proto:has(input:focus-visible) { box-shadow: var(--focus); }
  .proto-name { color: var(--text-1); font: 600 var(--fs-body) / var(--lh-body) var(--font-ui); }
  .proto-state { color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .proto-state[data-state='EXPERIMENTAL'] { color: var(--st-warn); }
  .proto-state[data-state='AVAILABLE'] { color: var(--st-ok); }
  .sr { position: absolute; width: 1px; height: 1px; margin: -1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0; }
  .unknown { display: flex; gap: var(--sp-2); margin: 0; color: var(--st-info); font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  .unknown :global(svg) { flex: none; margin-top: 1px; }
  .unknown span { color: var(--text-2); }
  .unknown b { color: var(--text-1); font-weight: 600; }

  .fields { display: grid; gap: var(--sp-3); width: 100%; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); }
  .fields .wide { grid-column: span 2; }
  .fields.advanced { margin-top: var(--sp-2); }
  label { display: flex; flex-direction: column; gap: 4px; min-width: 0; color: var(--text-3); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  /* caixa de marcar: o alvo é a linha inteira (44 px); a caixa visível é desenho */
  label.check { position: relative; flex-direction: row; align-items: center; gap: var(--sp-2); grid-column: 1 / -1; min-height: var(--touch); color: var(--text-1); font: var(--fs-body) / var(--lh-body) var(--font-ui); cursor: pointer; }
  .box { display: grid; place-items: center; flex: none; width: 22px; height: 22px; border: 1px solid var(--border-input); border-radius: var(--r-1); background: var(--surf-2); color: transparent; transition: background-color var(--dur-micro) var(--ease-out), border-color var(--dur-micro) var(--ease-out), color var(--dur-micro) var(--ease-out); }
  label.check input:checked + .box { border-color: var(--accent); background: var(--accent); color: var(--on-accent); }
  label.check input:focus-visible + .box { box-shadow: var(--focus); }
  input { width: 100%; min-height: var(--touch); padding: 0 var(--sp-2); border: 1px solid var(--border-input); border-radius: var(--r-2); background: var(--surf-2); color: var(--text-1); font: 16px / 1.2 var(--font-ui); }
  input[type='number'] { font-family: var(--font-mono); }
  .link { min-height: 24px; padding: 0; border: 0; background: none; color: var(--accent-text); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); text-decoration: underline; cursor: pointer; }
  .hint { margin: 0; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .hint b { color: var(--text-1); }
  .mapping { display: flex; flex-direction: column; gap: var(--sp-3); padding: var(--sp-2) 0 var(--sp-3); }
  .actions { display: flex; flex-wrap: wrap; gap: var(--sp-2); }
  .btn { display: inline-flex; align-items: center; justify-content: center; gap: var(--sp-2); min-height: var(--touch); padding: 0 var(--sp-4); border-radius: var(--r-3); font: 600 var(--fs-body) / 1.2 var(--font-ui); cursor: pointer; transition: transform var(--dur-micro) var(--ease-out), opacity var(--dur-micro) var(--ease-out), filter var(--dur-micro) var(--ease-out); }
  .btn:hover:not(:disabled) { filter: brightness(1.08); }
  .btn:active:not(:disabled) { transform: scale(0.98); }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn.primary { border: 1px solid var(--accent); background: var(--accent); color: var(--on-accent); }
  .btn.ghost { border: 1px solid var(--border-2); background: var(--surf-1); color: var(--text-1); }
  .btn.big { min-height: 48px; padding: 0 var(--sp-5); font-size: var(--fs-body-lg); }
  .spin { display: inline-flex; animation: spin 0.9s linear infinite; }
  .verdict { display: flex; align-items: center; gap: var(--sp-2); margin: 0; padding: var(--sp-2) var(--sp-3); border-radius: var(--r-2); color: var(--text-1); font: 500 var(--fs-body-lg) / var(--lh-body-lg) var(--font-ui); }
  .verdict[data-ok='true'] { background: var(--st-ok-bg); }
  .verdict[data-ok='true'] :global(svg) { color: var(--st-ok); }
  .verdict[data-ok='false'] { background: var(--st-crit-bg); color: var(--st-crit); animation: shake var(--dur-scenario) var(--ease-out); }
  .next { display: inline-flex; align-items: center; min-height: 24px; color: var(--accent-text); font: 500 var(--fs-body) / var(--lh-body) var(--font-ui); }
  .collection { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-2); margin: 0; color: var(--text-2); font: 600 var(--fs-body) / var(--lh-body) var(--font-ui); }
  .collection[data-on='true'] { color: var(--st-ok); }
  .collection[data-blocked='true'] { color: var(--st-warn); }
  .in-use { color: var(--text-2); font-weight: 400; }
  .validation { display: flex; flex-direction: column; gap: var(--sp-2); }
  .err, .warnline, .okline { margin: 0; padding: var(--sp-2) var(--sp-3); border-radius: var(--r-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .err { background: var(--st-crit-bg); color: var(--st-crit); }
  .warnline { background: var(--st-warn-bg); color: var(--text-1); }
  .okline { background: var(--st-ok-bg); color: var(--st-ok); }
  .tech { display: grid; gap: 4px; margin: var(--sp-2) 0 0; }
  .tech div { display: grid; grid-template-columns: 180px minmax(0, 1fr); gap: var(--sp-2); }
  dt { color: var(--text-3); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  dd { margin: 0; color: var(--text-1); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); overflow-wrap: anywhere; }
  dd.num { font-family: var(--font-mono); }
  .log { margin: var(--sp-3) 0 0; padding-left: var(--sp-4); color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .log li[data-level='WARNING'] { color: var(--st-warn); }

  @keyframes rise { from { opacity: 0; transform: translateY(3px); } to { opacity: 1; transform: none; } }
  @keyframes pop { 0% { transform: scale(0.4); opacity: 0; } 100% { transform: scale(1); opacity: 1; } }
  @keyframes spin { to { transform: rotate(360deg); } }
  @keyframes shake {
    0%, 100% { transform: none; }
    20% { transform: translateX(-6px); }
    40% { transform: translateX(5px); }
    60% { transform: translateX(-3px); }
    80% { transform: translateX(2px); }
  }

  @media (max-width: 767px), (pointer: coarse) {
    .link, .next { min-height: var(--touch); }
  }
  @media (max-width: 559px) {
    .fields .wide { grid-column: auto; }
    .tech div { grid-template-columns: minmax(0, 1fr); gap: 0; }
  }
  @media (prefers-reduced-motion: reduce) {
    .spin { animation: none; }
  }
</style>
