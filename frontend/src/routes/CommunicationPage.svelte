<script lang="ts">
  /** KCM › Comunicação. Passos: protocolo, endereço, variáveis (mapping), teste somente leitura
   *  com comparação na tela do KCM, salvar e coleta. Tudo aqui configura a FORJA e LÊ o KCM:
   *  nada envia comando ao equipamento. Protocolo nunca é escolhido sozinho. */
  import { untrack } from 'svelte'
  import ShieldCheck from '@lucide/svelte/icons/shield-check'
  import Plug from '@lucide/svelte/icons/plug'
  import FlaskConical from '@lucide/svelte/icons/flask-conical'
  import Save from '@lucide/svelte/icons/save'
  import Radio from '@lucide/svelte/icons/radio'
  import CircleHelp from '@lucide/svelte/icons/circle-help'
  import { errorMessage, type EquipmentProfile } from '../lib/api'
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
  import { tagCatalog } from '../lib/tagmeta.svelte'
  import MappingEditor from '../components/comm/MappingEditor.svelte'
  import ReadTestPanel from '../components/comm/ReadTestPanel.svelte'
  import Card from '../components/ui/Card.svelte'
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
  const userOk = $derived(/^[\w .@-]{1,64}$/.test(user.trim()))
  const canActivate = $derived(
    !!view && !view.collection.enabled && !dirtyComm && !dirtyMapping &&
      (driver === 'simulator' || (view.last_test_matches && view.last_test?.success === true)),
  )

  function adopt(next: CommView, keepTest = false): void {
    view = next
    comm = clone(next.profile.communication)
    mapping = clone(next.editable_mapping)
    validation = null
    if (!keepTest) {
      test = null
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
    rememberUser()
    try {
      test = await commApi.testRead(candidate, readingMapping, user.trim())
      kcm = {}
      if (view) view = await commApi.view(equipmentId).then((v) => ({ ...v })).catch(() => view)
    } catch (err) {
      test = null
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

  async function save(): Promise<void> {
    if (!view || !comm || !readingMapping || !userOk) return
    busy = 'save'
    notice = null
    rememberUser()
    try {
      let current = view
      if (dirtyMapping && mapping) {
        current = await commApi.saveMapping(
          equipmentId,
          { ...mapping, driver },
          view.editable_mapping_exists ? view.editable_mapping.version : null,
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
      adopt(current, true)
      notice = {
        tone: 'ok',
        text: current.collection_paused_by_change
          ? 'Configuração salva. A coleta foi pausada porque o que muda a leitura mudou: teste e ative de novo.'
          : 'Configuração salva e registrada na auditoria.',
      }
      reason = ''
      void loadLog(equipmentId)
    } catch (err) {
      notice = { tone: 'crit', text: errorMessage(err) }
    } finally {
      busy = ''
    }
  }

  async function setCollection(active: boolean): Promise<void> {
    if (!userOk) return
    busy = 'collection'
    notice = null
    rememberUser()
    try {
      adopt(await commApi.setCollection(equipmentId, active, user.trim(), reason.trim()), true)
      notice = {
        tone: 'ok',
        text: active ? 'Coleta ativada: a Forja passa a LER o KCM periodicamente.' : 'Coleta pausada: a Forja parou de ler este equipamento.',
      }
      void loadLog(equipmentId)
    } catch (err) {
      notice = { tone: 'crit', text: errorMessage(err) }
    } finally {
      busy = ''
    }
  }

  const PROTOCOLS: Array<{ id: DriverName; title: string; text: string }> = [
    { id: 'UNKNOWN', title: 'Ainda não identificado', text: 'Use até confirmar no KCM qual protocolo a interface Host/Anybus usa.' },
    { id: 'modbus_tcp', title: 'Modbus TCP', text: 'Leitura de registradores (funções 01 a 04).' },
    { id: 'ethernet_ip', title: 'EtherNet/IP', text: 'Leitura de atributos CIP por mensagem explícita, sem conexão de I/O.' },
    { id: 'simulator', title: 'Simulador', text: 'Dados simulados para demonstração e treinamento.' },
  ]
</script>

<section class="comm" data-testid="communication">
  <header class="head">
    <div>
      <p class="label">{name}</p>
      <h1 class="title">Comunicação com o KCM</h1>
      <p class="sub">
        Configure como a Forja lê este KCM, teste a leitura e compare com a tela do equipamento.
      </p>
    </div>
    {#if view}
      <div class="state" data-testid="comm-state" data-code={view.state.code} data-tone={view.state.tone}>
        <span class="dot" aria-hidden="true"></span>
        <span>{view.state.label_pt}</span>
      </div>
    {/if}
  </header>

  <aside class="safety" aria-label="O que esta tela faz">
    <ShieldCheck size={20} aria-hidden="true" />
    <p>
      <b>Somente leitura.</b> Esta tela grava a configuração da Forja e lê o KCM. Nenhum botão envia
      comando ao equipamento: não altera parâmetro, não mexe em alarme, não calibra. Nenhuma varredura
      de rede é feita; a Forja só conecta no endereço informado, quando você testa ou ativa a coleta.
    </p>
  </aside>

  {#if loadError}
    <EmptyState title="Não foi possível carregar a comunicação" text={loadError} />
  {:else if !view || !comm || !mapping}
    <div class="sk" aria-busy="true" aria-label="Carregando"></div>
  {:else}
    {#if notice}
      <p class="notice" data-tone={notice.tone} role="status" data-testid="comm-notice">{notice.text}</p>
    {/if}

    <div class="layout">
      <div class="steps">
        <Card title="1 · Protocolo" testid="comm-step-protocol">
          <div class="protocols" role="radiogroup" aria-label="Protocolo">
            {#each PROTOCOLS as p (p.id)}
              {@const info = p.id === 'UNKNOWN' ? null : view.drivers[p.id]}
              <label class="proto" class:on={driver === p.id} data-testid={`protocol-${p.id}`}>
                <input type="radio" name="protocol" class="sr" checked={driver === p.id} onchange={() => choose(p.id)} />
                <span class="proto-title">
                  {p.title}
                  {#if info}<span class="pill" data-state={info.state}>{info.state_pt}</span>{/if}
                </span>
                <span class="proto-text">{p.text}</span>
                {#if info?.reason_pt && p.id !== 'simulator'}<span class="proto-note">{info.reason_pt}</span>{/if}
              </label>
            {/each}
          </div>
          {#if driver === 'UNKNOWN'}
            <div class="unknown" data-testid="protocol-unknown">
              <CircleHelp size={20} aria-hidden="true" />
              <div>
                <b>Protocolo ainda não identificado.</b>
                <p>
                  Cabo de rede e módulo Anybus não dizem qual protocolo está ativo. Confirme no KCM
                  (menu de versões, placa Host) e na etiqueta do módulo; fotografe os dois. Enquanto
                  isso, nada é lido deste equipamento.
                </p>
              </div>
            </div>
          {/if}
        </Card>

        {#if real}
          <Card title="2 · Endereço" testid="comm-step-address">
            <div class="grid">
              <label>Endereço IP
                <input type="text" inputmode="decimal" autocomplete="off" placeholder="ex.: [IP do módulo Host]" value={comm.ip === 'UNKNOWN' ? '' : comm.ip} oninput={(e) => comm && (comm.ip = textOrUnknown(e.currentTarget.value))} data-testid="comm-ip" />
              </label>
              <label>Porta
                <input type="number" min="1" max="65535" inputmode="numeric" value={comm.port === 'UNKNOWN' ? '' : comm.port} oninput={(e) => comm && (comm.port = intOrUnknown(e.currentTarget.value))} data-testid="comm-port" />
                {#if PROTOCOL_DEFAULT_PORT[driver]}
                  <button type="button" class="link" onclick={() => comm && (comm.port = PROTOCOL_DEFAULT_PORT[driver] ?? comm.port)}>
                    Usar a porta padrão do protocolo ({PROTOCOL_DEFAULT_PORT[driver]})
                  </button>
                {/if}
              </label>
              {#if driver === 'modbus_tcp'}
                <label>Unit ID (endereço do escravo)
                  <input type="number" min="0" max="255" inputmode="numeric" value={comm.unit_id === 'UNKNOWN' ? '' : comm.unit_id} oninput={(e) => comm && (comm.unit_id = intOrUnknown(e.currentTarget.value))} data-testid="comm-unit" />
                </label>
              {/if}
              <label>Tempo de espera (s)
                <input type="number" min="0.1" max="60" step="0.1" inputmode="decimal" bind:value={comm.timeout_s} />
              </label>
              <label>Intervalo entre leituras (s)
                <input type="number" min="0.25" max="3600" step="0.25" inputmode="decimal" bind:value={comm.poll_interval_s} />
              </label>
              <label>Valor antigo depois de (s)
                <input type="number" min="1" step="1" inputmode="decimal" bind:value={comm.stale_after_s} />
              </label>
              {#if driver === 'modbus_tcp'}
                <label class="check">
                  <input type="checkbox" checked={comm.options['block_reads'] !== false} onchange={(e) => comm && (comm.options = { ...comm.options, block_reads: e.currentTarget.checked })} />
                  Ler registradores vizinhos em bloco (menos requisições)
                </label>
              {/if}
            </div>
          </Card>

          <Card title="3 · Variáveis (mapping)" testid="comm-step-mapping">
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
          </Card>
        {:else if driver === 'simulator'}
          <Card title="2 · Simulador" testid="comm-step-simulator">
            <p class="hint">
              Leitura simulada pelo modelo WBF da Forja. Nenhum valor representa um KCM real. O cenário
              é escolhido em Ferramentas › Simulador.
            </p>
          </Card>
        {/if}
      </div>

      <div class="side">
        <Card title="4 · Teste somente leitura" testid="comm-step-test">
          <p class="hint">
            Cria uma conexão descartável, lê uma vez e fecha. Usa o que está nesta tela, mesmo antes de
            salvar. Nada é escrito no KCM.
          </p>
          <label class="user">Responsável
            <input type="text" maxlength="64" autocomplete="name" placeholder="nome do técnico" bind:value={user} data-testid="comm-user" />
          </label>
          <button type="button" class="btn primary" disabled={busy !== '' || driver === 'UNKNOWN'} onclick={runTest} data-testid="comm-test">
            <FlaskConical size={18} aria-hidden="true" />
            {busy === 'test' ? 'Lendo…' : 'Testar comunicação — somente leitura'}
          </button>
          {#if test}
            <ReadTestPanel result={test} bind:kcm canRegister={real} onregister={register} />
          {/if}
        </Card>

        <Card title="5 · Salvar" testid="comm-step-save">
          <label class="user">Motivo da alteração
            <input type="text" maxlength="200" placeholder="ex.: protocolo confirmado na tela do KCM" bind:value={reason} data-testid="comm-reason" />
          </label>
          <p class="hint">
            {#if dirtyComm || dirtyMapping}
              Há alterações não salvas{dirtyMapping ? ' no mapping' : ''}{dirtyComm ? ' na comunicação' : ''}.
              Cada gravação fica na auditoria e a versão anterior é guardada.
            {:else}
              Nada a salvar.
            {/if}
          </p>
          <button type="button" class="btn primary" disabled={busy !== '' || !(dirtyComm || dirtyMapping) || !userOk} onclick={save} data-testid="comm-save">
            <Save size={18} aria-hidden="true" /> Salvar configuração
          </button>
          {#if !userOk && (dirtyComm || dirtyMapping)}<p class="hint">Informe o responsável no passo 4.</p>{/if}
        </Card>

        <Card title="6 · Coleta" testid="comm-step-collection">
          <p class="collection" data-on={view.collection.enabled} data-testid="comm-collection">
            <Radio size={18} aria-hidden="true" /> {view.collection.label_pt}
          </p>
          <p class="hint">
            Configuração salva em uso: <b>{SAVED_DRIVER_PT[view.profile.communication.driver] ?? view.profile.communication.driver}</b>{dirtyComm || dirtyMapping ? ' (há alterações na tela ainda não salvas)' : ''}.
          </p>
          <p class="hint">
            Ativar a coleta liga a LEITURA periódica da Forja. Não envia nenhum comando ao KCM.
            {#if real}Para driver real, exige teste de leitura bem-sucedido da configuração salva.{/if}
          </p>
          {#if view.collection.enabled}
            <button type="button" class="btn ghost" disabled={busy !== '' || !userOk} onclick={() => setCollection(false)} data-testid="comm-collection-off">
              Pausar coleta
            </button>
          {:else}
            <button type="button" class="btn primary" disabled={busy !== '' || !canActivate || !userOk} onclick={() => setCollection(true)} data-testid="comm-collection-on">
              <Plug size={18} aria-hidden="true" /> Ativar coleta (somente leitura)
            </button>
            {#if real && !canActivate}
              <p class="hint">
                {dirtyComm || dirtyMapping
                  ? 'Salve a configuração antes.'
                  : 'Faça o teste somente leitura com a configuração salva e obtenha leitura.'}
              </p>
            {/if}
          {/if}
          <dl class="runtime">
            <div><dt>Conexão</dt><dd>{view.runtime.connection_pt}</dd></div>
            <div><dt>Latência</dt><dd class="num">{view.runtime.latency_ms != null ? `${fmtNumber(view.runtime.latency_ms, 1)} ms` : '—'}</dd></div>
            <div><dt>Falhas seguidas</dt><dd class="num">{view.runtime.consecutive_errors}</dd></div>
            {#if view.last_test}
              <div><dt>Último teste</dt><dd>{view.last_test.success ? 'leitura obtida' : 'falhou'} · {fmtDateTime(view.last_test.ts_utc)}{view.last_test_matches ? '' : ' (outra configuração)'}</dd></div>
            {/if}
          </dl>
        </Card>
      </div>
    </div>

    <Disclosure summary="Detalhes técnicos e log de conexão" testid="comm-tech">
      <dl class="tech">
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
  .comm { display: flex; flex-direction: column; gap: var(--sp-5); min-width: 0; }
  .head { display: flex; align-items: flex-end; justify-content: space-between; gap: var(--sp-4); flex-wrap: wrap; }
  .head .label { margin: 0 0 var(--sp-1); }
  .title { margin: 0; font: 600 var(--fs-h1) / var(--lh-h1) var(--font-ui); color: var(--text-1); }
  @media (min-width: 1024px) { .title { font-size: var(--fs-display); line-height: var(--lh-display); } }
  .sub { margin: var(--sp-1) 0 0; max-width: 72ch; color: var(--text-2); font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  .state { display: inline-flex; align-items: center; gap: var(--sp-2); min-height: var(--touch); padding: 0 var(--sp-4); border: 1px solid var(--border-2); border-radius: var(--r-pill); color: var(--text-1); font: 600 var(--fs-body) / 1 var(--font-ui); }
  .state .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--text-3); }
  .state[data-tone='ok'] { border-color: var(--st-ok); } .state[data-tone='ok'] .dot { background: var(--st-ok); }
  .state[data-tone='warn'] { border-color: var(--st-warn); } .state[data-tone='warn'] .dot { background: var(--st-warn); }
  .state[data-tone='crit'] { border-color: var(--st-crit); } .state[data-tone='crit'] .dot { background: var(--st-crit); }
  .state[data-tone='sim'] { border-color: var(--q-sim); } .state[data-tone='sim'] .dot { background: var(--q-sim); }
  .safety { display: flex; gap: var(--sp-3); align-items: flex-start; padding: var(--sp-3) var(--sp-4); border: 1px solid var(--border-1); border-left: 3px solid var(--st-ok); border-radius: var(--r-3); background: var(--surf-1); color: var(--st-ok); }
  .safety p { margin: 0; color: var(--text-2); font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  .safety b { color: var(--text-1); }
  .notice { margin: 0; padding: var(--sp-3) var(--sp-4); border-radius: var(--r-3); font: 500 var(--fs-body) / var(--lh-body) var(--font-ui); animation: rise var(--dur-base) var(--ease-out) both; }
  .notice[data-tone='ok'] { background: var(--st-ok-bg); color: var(--st-ok); }
  .notice[data-tone='warn'] { background: var(--st-warn-bg); color: var(--st-warn); }
  .notice[data-tone='crit'] { background: var(--st-crit-bg); color: var(--st-crit); }
  @keyframes rise { from { opacity: 0; transform: translateY(3px); } to { opacity: 1; transform: none; } }
  .sk { height: 360px; border-radius: var(--r-4); background: var(--surf-2); opacity: 0.6; }
  .layout { display: grid; gap: var(--sp-4); grid-template-columns: minmax(0, 1fr); align-items: start; }
  @media (min-width: 1280px) { .layout { grid-template-columns: minmax(0, 3fr) minmax(360px, 2fr); } }
  .steps, .side { display: flex; flex-direction: column; gap: var(--sp-4); min-width: 0; }
  .protocols { display: grid; gap: var(--sp-2); grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); }
  .proto { position: relative; display: flex; flex-direction: column; gap: 4px; min-height: var(--touch); padding: var(--sp-3); border: 1px solid var(--border-2); border-radius: var(--r-3); background: var(--surf-1); cursor: pointer; transition: border-color var(--dur-micro) var(--ease-out), background var(--dur-micro) var(--ease-out), transform var(--dur-micro) var(--ease-out); }
  .proto:hover { border-color: var(--border-input); }
  .proto:active { transform: scale(0.99); }
  .proto.on { border-color: var(--accent); background: var(--accent-soft); }
  .proto:has(input:focus-visible) { box-shadow: var(--focus); }
  .proto-title { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-2); color: var(--text-1); font: 600 var(--fs-body) / var(--lh-body) var(--font-ui); }
  .proto-text { color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .proto-note { color: var(--text-3); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .pill { padding: 1px 8px; border-radius: var(--r-pill); border: 1px solid var(--border-2); color: var(--text-2); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .pill[data-state='EXPERIMENTAL'] { border-color: var(--st-warn); color: var(--st-warn); }
  .pill[data-state='AVAILABLE'] { border-color: var(--st-ok); color: var(--st-ok); }
  .sr { position: absolute; width: 1px; height: 1px; margin: -1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0; }
  .unknown { display: flex; gap: var(--sp-3); margin-top: var(--sp-3); padding: var(--sp-3); border-radius: var(--r-3); background: var(--surf-2); color: var(--st-info); }
  .unknown b { color: var(--text-1); font: 600 var(--fs-body) / var(--lh-body) var(--font-ui); }
  .unknown p { margin: 4px 0 0; color: var(--text-2); font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  .grid { display: grid; gap: var(--sp-3); grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); }
  label { display: flex; flex-direction: column; gap: 4px; min-width: 0; color: var(--text-3); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  label.check { flex-direction: row; align-items: center; gap: var(--sp-2); grid-column: 1 / -1; min-height: var(--touch); color: var(--text-1); font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  label.check input { width: 20px; height: 20px; min-height: 0; accent-color: var(--accent); }
  input { width: 100%; min-height: var(--touch); padding: 0 var(--sp-2); border: 1px solid var(--border-input); border-radius: var(--r-2); background: var(--surf-2); color: var(--text-1); font: 16px / 1.2 var(--font-ui); }
  input[type='number'] { font-family: var(--font-mono); }
  .link { align-self: flex-start; min-height: var(--touch); padding: 0; border: 0; background: none; color: var(--accent-text); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); text-decoration: underline; cursor: pointer; }
  .hint { margin: 0; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .hint b { color: var(--text-1); }
  .actions { display: flex; flex-wrap: wrap; gap: var(--sp-2); margin-top: var(--sp-3); }
  .btn { display: inline-flex; align-items: center; justify-content: center; gap: var(--sp-2); min-height: var(--touch); padding: 0 var(--sp-4); border-radius: var(--r-3); font: 600 var(--fs-body) / 1.2 var(--font-ui); cursor: pointer; transition: transform var(--dur-micro) var(--ease-out), opacity var(--dur-micro) var(--ease-out); }
  .btn:active:not(:disabled) { transform: scale(0.98); }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn.primary { border: 1px solid var(--accent); background: var(--accent); color: var(--on-accent); }
  .btn.ghost { border: 1px solid var(--border-2); background: var(--surf-1); color: var(--text-1); }
  :global([data-testid='comm-step-test']), :global([data-testid='comm-step-save']), :global([data-testid='comm-step-collection']) { display: flex; flex-direction: column; gap: var(--sp-3); }
  .user { color: var(--text-3); }
  .validation { display: flex; flex-direction: column; gap: var(--sp-2); margin-top: var(--sp-3); }
  .err, .warnline, .okline { margin: 0; padding: var(--sp-2) var(--sp-3); border-radius: var(--r-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .err { background: var(--st-crit-bg); color: var(--st-crit); }
  .warnline { background: var(--st-warn-bg); color: var(--text-1); }
  .okline { background: var(--st-ok-bg); color: var(--st-ok); }
  .collection { display: flex; align-items: center; gap: var(--sp-2); margin: 0; color: var(--text-2); font: 600 var(--fs-body) / var(--lh-body) var(--font-ui); }
  .collection[data-on='true'] { color: var(--st-ok); }
  .runtime, .tech { display: grid; gap: 4px; margin: 0; }
  .runtime div, .tech div { display: grid; grid-template-columns: 140px minmax(0, 1fr); gap: var(--sp-2); }
  dt { color: var(--text-3); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  dd { margin: 0; color: var(--text-1); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); overflow-wrap: anywhere; }
  dd.num { font-family: var(--font-mono); }
  .log { margin: var(--sp-3) 0 0; padding-left: var(--sp-4); color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .log li[data-level='WARNING'] { color: var(--st-warn); }
  @media (max-width: 767px) {
    .runtime div, .tech div { grid-template-columns: minmax(0, 1fr); gap: 0; }
  }
</style>
