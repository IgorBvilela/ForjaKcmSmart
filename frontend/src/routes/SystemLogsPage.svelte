<script lang="ts">
  /** Sistema › Saúde e registros. Saúde de cada parte do Edge em linguagem simples (achados do
   *  mais grave ao mais leve) e os registros: serviço, comunicação e auditoria. Código técnico
   *  fica em "Detalhes técnicos". */
  import { untrack } from 'svelte'
  import Download from '@lucide/svelte/icons/download'
  import CircleCheck from '@lucide/svelte/icons/circle-check'
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert'
  import OctagonAlert from '@lucide/svelte/icons/octagon-alert'
  import Info from '@lucide/svelte/icons/info'
  import { API_BASE, errorMessage } from '../lib/api'
  import { fmtDateTime, fmtDuration, fmtNumber, fmtWhen } from '../lib/format'
  import { app } from '../lib/state.svelte'
  import Card from '../components/ui/Card.svelte'
  import EmptyState from '../components/ui/EmptyState.svelte'

  type Sev = 'ok' | 'info' | 'warn' | 'crit'
  interface Finding { severity: Sev; area: string; text_pt: string }
  interface EquipmentHealth {
    equipment_id: string
    name: string
    driver: string
    collecting: boolean
    connection: string
    connection_pt: string
    latency_ms: number | null
    consecutive_errors: number
    reconnect_count: number
    restart_count: number
    samples_per_min: number
    last_ok_utc: string | null
    is_stale: boolean
    detail_pt: string
  }
  interface Report {
    status: Sev
    status_pt: string
    findings: Finding[]
    edge: { version: string; uptime_s: number }
    equipment: EquipmentHealth[]
    storage: { disk?: { total_bytes: number; free_bytes: number; free_fraction: number }; historian_fraction?: number | null }
    historian: Record<string, unknown> | null
    core: Record<string, unknown> | null
    jobs: { runs: Record<string, number>; errors: Record<string, number> } | null
    events_engine: { batches: number; transitions: number; diagnoses: number; errors: number } | null
    realtime: { clients: number; dropped: number } | null
    rules_loaded: number
  }
  interface LogEntry { ts: string; level: string; origin: string; message_pt: string; detail: unknown }

  const DRIVER_PT: Record<string, string> = {
    simulator: 'Simulador',
    modbus_tcp: 'Modbus TCP',
    ethernet_ip: 'EtherNet/IP',
    UNKNOWN: 'Protocolo não identificado',
  }
  const SOURCES = [
    { id: 'app', label: 'Serviço' },
    { id: 'comm', label: 'Comunicação' },
    { id: 'audit', label: 'Auditoria' },
  ] as const
  type Source = (typeof SOURCES)[number]['id']

  let report = $state<Report | null>(null)
  let error = $state<string | null>(null)
  let source = $state<Source>('app')
  let level = $state<'' | 'WARNING' | 'ERROR'>('')
  let entries = $state<LogEntry[]>([])
  let openDetail = $state<Record<number, boolean>>({})

  async function get<T>(path: string): Promise<T> {
    const res = await fetch(`${API_BASE}${path}`, { cache: 'no-store', headers: { Accept: 'application/json' } })
    if (!res.ok) throw new Error(`Falha ao consultar (${res.status})`)
    return (await res.json()) as T
  }

  async function loadReport(): Promise<void> {
    try {
      report = await get<Report>('/system/health-report')
      error = null
    } catch (err) {
      error = errorMessage(err)
    }
  }

  async function loadLogs(): Promise<void> {
    const params = new URLSearchParams({ source, limit: '300' })
    if (level && source === 'app') params.set('level', level)
    try {
      entries = (await get<{ entries: LogEntry[] }>(`/system/logs?${params}`)).entries
      openDetail = {}
    } catch {
      entries = []
    }
  }

  $effect(() => {
    untrack(() => void loadReport())
    const timer = window.setInterval(() => void loadReport(), 10_000)
    return () => clearInterval(timer)
  })

  $effect(() => {
    void source
    void level
    untrack(() => void loadLogs())
  })

  function bytes(n: unknown): string {
    if (typeof n !== 'number' || !Number.isFinite(n)) return '—'
    if (n >= 1024 ** 3) return `${fmtNumber(n / 1024 ** 3, 1)} GB`
    if (n >= 1024 ** 2) return `${fmtNumber(n / 1024 ** 2, 1)} MB`
    return `${fmtNumber(n / 1024, 0)} kB`
  }

  function rows(stats: Record<string, unknown> | null, table: string): string {
    const r = (stats?.rows ?? {}) as Record<string, number>
    return r[table] != null ? fmtNumber(r[table], 0) : '—'
  }

  const csvHref = $derived(`${API_BASE}/system/logs.csv?source=${source}`)
</script>

<section class="sys" data-testid="system-logs">
  <header class="head">
    <div>
      <p class="label">Sistema</p>
      <h1 class="title">Saúde e registros</h1>
      <p class="sub">Como está cada parte do Forja Edge agora, e os registros do serviço, da comunicação e da auditoria.</p>
    </div>
  </header>

  {#if error}
    <EmptyState title="Não foi possível consultar a saúde do Edge" text={error} />
  {:else if !report}
    <div class="sk" aria-busy="true" aria-label="Carregando"></div>
  {:else}
    <div class="status" data-status={report.status} data-testid="health-status">
      <span class="icon" aria-hidden="true">
        {#if report.status === 'ok'}<CircleCheck size={28} />{:else if report.status === 'crit'}<OctagonAlert size={28} />{:else if report.status === 'warn'}<TriangleAlert size={28} />{:else}<Info size={28} />{/if}
      </span>
      <div>
        <b>{report.status_pt}</b>
        <span class="since num">Ligado há {fmtDuration(report.edge.uptime_s)} · versão {report.edge.version}</span>
      </div>
    </div>

    {#if report.findings.length}
      <ul class="findings" data-testid="health-findings">
        {#each report.findings as f, i (i)}
          <li data-severity={f.severity}><span class="area">{f.area}</span>{f.text_pt}</li>
        {/each}
      </ul>
    {/if}

    <Card title="Aquisição por equipamento" padded={false} testid="health-equipment">
      <div class="table-wrap">
        <table class="resp">
          <thead>
            <tr>
              <th scope="col">Equipamento</th>
              <th scope="col">Coleta</th>
              <th scope="col">Conexão</th>
              <th scope="col" class="r">Latência</th>
              <th scope="col" class="r">Leituras/min</th>
              <th scope="col" class="r">Falhas seguidas</th>
              <th scope="col" class="r">Reconexões</th>
              <th scope="col" class="r">Reinícios</th>
              <th scope="col">Última leitura válida</th>
            </tr>
          </thead>
          <tbody>
            {#each report.equipment as e (e.equipment_id)}
              <tr data-connection={e.connection}>
                <th scope="row">{e.name}<span class="sub2">{DRIVER_PT[e.driver] ?? e.driver}</span></th>
                <td data-label="Coleta">{e.collecting ? 'Ativa' : 'Pausada'}</td>
                <td data-label="Conexão"><span class="conn" data-connection={e.connection}>{e.connection_pt}</span></td>
                <td class="r num" data-label="Latência">{e.latency_ms != null ? `${fmtNumber(e.latency_ms, 1)} ms` : '—'}</td>
                <td class="r num" data-label="Leituras/min">{fmtNumber(e.samples_per_min, 0)}</td>
                <td class="r num" data-label="Falhas seguidas">{e.consecutive_errors}</td>
                <td class="r num" data-label="Reconexões">{e.reconnect_count}</td>
                <td class="r num" data-label="Reinícios">{e.restart_count}</td>
                <td class="num" data-label="Última leitura válida">{e.last_ok_utc ? fmtWhen(e.last_ok_utc, app.now) : 'nenhuma'}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </Card>

    <div class="grid">
      <Card title="Armazenamento" testid="health-storage">
        {#if report.storage.disk}
          {@const used = 1 - report.storage.disk.free_fraction}
          <p class="metric">Disco dos dados: <b class="num">{fmtNumber(report.storage.disk.free_fraction * 100, 0)}% livre</b> ({bytes(report.storage.disk.free_bytes)} de {bytes(report.storage.disk.total_bytes)})</p>
          <div class="bar" role="img" aria-label={`Disco ${fmtNumber(used * 100, 0)}% ocupado`}>
            <span class="fill" data-level={used > 0.9 ? 'crit' : used > 0.8 ? 'warn' : 'ok'} style:width={`${Math.min(100, used * 100)}%`}></span>
          </div>
        {/if}
        <dl class="kv">
          <div><dt>Historiador</dt><dd class="num">{bytes(report.historian?.size_bytes)} · {rows(report.historian, 'samples')} amostras</dd></div>
          <div><dt>Última amostra</dt><dd class="num">{report.historian?.last_sample_utc ? fmtWhen(String(report.historian.last_sample_utc), app.now) : '—'}</dd></div>
          <div><dt>Consolidado até</dt><dd class="num">{report.historian?.watermark_1m_utc ? fmtWhen(String(report.historian.watermark_1m_utc), app.now) : 'ainda não consolidado'}</dd></div>
          <div><dt>Banco de eventos</dt><dd class="num">{bytes(report.core?.size_bytes)} · {rows(report.core, 'events')} eventos · {rows(report.core, 'audit_log')} auditorias</dd></div>
        </dl>
      </Card>

      <Card title="Motor de eventos e tempo real" testid="health-engines">
        <dl class="kv">
          <div><dt>Regras carregadas</dt><dd class="num">{report.rules_loaded}</dd></div>
          <div><dt>Lotes analisados</dt><dd class="num">{fmtNumber(report.events_engine?.batches ?? 0, 0)}</dd></div>
          <div><dt>Mudanças de evento</dt><dd class="num">{fmtNumber(report.events_engine?.transitions ?? 0, 0)}</dd></div>
          <div><dt>Diagnósticos gerados</dt><dd class="num">{fmtNumber(report.events_engine?.diagnoses ?? 0, 0)}</dd></div>
          <div><dt>Erros no motor</dt><dd class="num">{report.events_engine?.errors ?? 0}</dd></div>
          <div><dt>Telas conectadas</dt><dd class="num">{report.realtime?.clients ?? 0}</dd></div>
          <div><dt>Atualizações descartadas</dt><dd class="num">{report.realtime?.dropped ?? 0}</dd></div>
          <div><dt>Consolidação do histórico</dt><dd class="num">{report.jobs?.runs.run_rollups ?? 0} execuções · {report.jobs?.errors.run_rollups ?? 0} erros</dd></div>
          <div><dt>Retenção</dt><dd class="num">{report.jobs?.runs.run_retention ?? 0} execuções · {report.jobs?.errors.run_retention ?? 0} erros</dd></div>
        </dl>
      </Card>
    </div>
  {/if}

  <Card title="Registros" testid="health-logs">
    {#snippet actions()}
      <a class="dl" href={csvHref} download data-testid="logs-export"><Download size={16} aria-hidden="true" /> Exportar CSV</a>
    {/snippet}
    <div class="tabs" role="tablist" aria-label="Fonte dos registros">
      {#each SOURCES as s (s.id)}
        <button type="button" role="tab" aria-selected={source === s.id} class="tab" onclick={() => (source = s.id)} data-testid={`logs-tab-${s.id}`}>{s.label}</button>
      {/each}
      {#if source === 'app'}
        <label class="lvl">Nível
          <select bind:value={level} data-testid="logs-level">
            <option value="">Todos</option>
            <option value="WARNING">Avisos e erros</option>
            <option value="ERROR">Só erros</option>
          </select>
        </label>
      {/if}
    </div>
    {#if entries.length === 0}
      <p class="hint">Nenhum registro.</p>
    {:else}
      <ol class="log" data-testid="logs-list" data-count={entries.length}>
        {#each entries as e, i (i)}
          <li data-level={e.level}>
            <span class="ts num" title={e.ts}>{fmtDateTime(e.ts)}</span>
            <span class="lv">{e.level}</span>
            <span class="msg">{e.message_pt}<span class="origin">{e.origin}</span></span>
            {#if e.detail && (typeof e.detail === 'string' ? e.detail : JSON.stringify(e.detail) !== '{}')}
              <button type="button" class="more" aria-expanded={openDetail[i] ?? false} onclick={() => (openDetail[i] = !openDetail[i])}>Detalhes técnicos</button>
              {#if openDetail[i]}<pre class="detail">{typeof e.detail === 'string' ? e.detail : JSON.stringify(e.detail, null, 2)}</pre>{/if}
            {/if}
          </li>
        {/each}
      </ol>
    {/if}
  </Card>
</section>

<style>
  .sys { display: flex; flex-direction: column; gap: var(--sp-5); min-width: 0; }
  .head .label { margin: 0 0 var(--sp-1); }
  .title { margin: 0; font: 600 var(--fs-h1) / var(--lh-h1) var(--font-ui); color: var(--text-1); }
  @media (min-width: 1024px) { .title { font-size: var(--fs-display); line-height: var(--lh-display); } }
  .sub { margin: var(--sp-1) 0 0; max-width: 72ch; color: var(--text-2); font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  .sk { height: 300px; border-radius: var(--r-4); background: var(--surf-2); opacity: 0.6; }
  .status { display: flex; align-items: center; gap: var(--sp-4); padding: var(--sp-4) var(--sp-5); border-radius: var(--r-4); border: 1px solid var(--border-1); background: var(--surf-1); animation: rise var(--dur-base) var(--ease-out) both; }
  .status b { display: block; color: var(--text-1); font: 600 var(--fs-h2) / var(--lh-h2) var(--font-ui); }
  .status .since { color: var(--text-3); font-size: var(--fs-mono-sm); }
  .status[data-status='ok'] { border-left: 4px solid var(--st-ok); } .status[data-status='ok'] .icon { color: var(--st-ok); }
  .status[data-status='info'] { border-left: 4px solid var(--st-info); } .status[data-status='info'] .icon { color: var(--st-info); }
  .status[data-status='warn'] { border-left: 4px solid var(--st-warn); } .status[data-status='warn'] .icon { color: var(--st-warn); }
  .status[data-status='crit'] { border-left: 4px solid var(--st-crit); } .status[data-status='crit'] .icon { color: var(--st-crit); }
  @keyframes rise { from { opacity: 0; transform: translateY(3px); } to { opacity: 1; transform: none; } }
  .findings { display: flex; flex-direction: column; gap: var(--sp-2); margin: 0; padding: 0; list-style: none; }
  .findings li { display: flex; flex-wrap: wrap; gap: var(--sp-2); align-items: baseline; padding: var(--sp-3) var(--sp-4); border-radius: var(--r-3); background: var(--surf-1); border: 1px solid var(--border-1); color: var(--text-1); font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  .findings li[data-severity='crit'] { border-left: 3px solid var(--st-crit); }
  .findings li[data-severity='warn'] { border-left: 3px solid var(--st-warn); }
  .findings li[data-severity='info'] { border-left: 3px solid var(--st-info); }
  .area { color: var(--text-3); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); text-transform: uppercase; letter-spacing: var(--ls-label); }
  .grid { display: grid; gap: var(--sp-4); grid-template-columns: minmax(0, 1fr); }
  @media (min-width: 1024px) { .grid { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); } }
  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  th, td { padding: var(--sp-2) var(--sp-4); border-bottom: 1px solid var(--border-1); text-align: left; }
  thead th { color: var(--text-3); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  tbody th { color: var(--text-1); font-weight: 500; }
  .sub2 { display: block; color: var(--text-3); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .r { text-align: right; }
  td.num { font-family: var(--font-mono); font-size: var(--fs-mono-sm); color: var(--text-1); }
  .conn[data-connection='CONNECTED'] { color: var(--st-ok); }
  .conn[data-connection='ERROR'] { color: var(--st-crit); }
  .metric { margin: 0 0 var(--sp-2); color: var(--text-2); font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  .metric b { color: var(--text-1); }
  .bar { height: 8px; border-radius: var(--r-pill); background: var(--surf-2); overflow: hidden; margin-bottom: var(--sp-3); }
  .fill { display: block; height: 100%; border-radius: var(--r-pill); background: var(--st-ok); transition: width var(--dur-draw) var(--ease-out); }
  .fill[data-level='warn'] { background: var(--st-warn); }
  .fill[data-level='crit'] { background: var(--st-crit-fill); }
  .kv { display: grid; gap: var(--sp-2); margin: 0; }
  .kv div { display: grid; grid-template-columns: 190px minmax(0, 1fr); gap: var(--sp-3); }
  dt { color: var(--text-3); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  dd { margin: 0; color: var(--text-1); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  dd.num { font-family: var(--font-mono); }
  .dl { display: inline-flex; align-items: center; gap: var(--sp-2); min-height: var(--touch); padding: 0 var(--sp-3); border: 1px solid var(--border-2); border-radius: var(--r-3); color: var(--text-1); text-decoration: none; font: 500 var(--fs-body) / 1 var(--font-ui); }
  .tabs { display: flex; flex-wrap: wrap; align-items: flex-end; gap: var(--sp-2); margin-bottom: var(--sp-3); }
  .tab { min-height: var(--touch); padding: 0 var(--sp-4); border: 1px solid var(--border-2); border-radius: var(--r-pill); background: var(--surf-1); color: var(--text-2); font: 500 var(--fs-body) / 1 var(--font-ui); cursor: pointer; }
  .tab[aria-selected='true'] { border-color: var(--accent); background: var(--accent-soft); color: var(--text-1); }
  .lvl { display: flex; flex-direction: column; gap: 4px; margin-left: auto; color: var(--text-3); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .lvl select { min-height: var(--touch); padding: 0 var(--sp-2); border: 1px solid var(--border-input); border-radius: var(--r-2); background: var(--surf-2); color: var(--text-1); font: 16px / 1 var(--font-ui); }
  .hint { margin: 0; color: var(--text-3); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .log { display: flex; flex-direction: column; margin: 0; padding: 0; list-style: none; max-height: 560px; overflow-y: auto; border: 1px solid var(--border-1); border-radius: var(--r-3); }
  .log li { display: grid; grid-template-columns: 190px 80px minmax(0, 1fr) auto; gap: var(--sp-3); align-items: start; padding: var(--sp-2) var(--sp-3); border-top: 1px solid var(--border-1); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); color: var(--text-1); }
  .log li:first-child { border-top: 0; }
  .ts { color: var(--text-3); font-size: var(--fs-mono-sm); }
  .lv { color: var(--text-2); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-mono); }
  li[data-level='WARNING'] .lv { color: var(--st-warn); }
  li[data-level='ERROR'] .lv, li[data-level='CRITICAL'] .lv { color: var(--st-crit); }
  .msg { overflow-wrap: anywhere; }
  .origin { display: block; color: var(--text-3); font-size: var(--fs-caption); }
  .more { min-height: var(--touch); padding: 0 var(--sp-2); border: 0; background: none; color: var(--accent-text); font: 500 var(--fs-caption) / 1 var(--font-ui); text-decoration: underline; cursor: pointer; }
  .detail { grid-column: 1 / -1; margin: 0; padding: var(--sp-2); border-radius: var(--r-2); background: var(--surf-2); color: var(--text-2); font: var(--fs-mono-sm) / var(--lh-mono-sm) var(--font-mono); white-space: pre-wrap; overflow-wrap: anywhere; }
  @media (max-width: 767px) {
    .kv div { grid-template-columns: minmax(0, 1fr); gap: 0; }
    .log li { grid-template-columns: minmax(0, 1fr) auto; }
    .log li .msg { grid-column: 1 / -1; }
    .lvl { margin-left: 0; }
  }
</style>
