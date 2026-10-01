/** Cliente tipado da API local (/api/v1). Tipos espelham os routers em src/forja/api/routers. */

export type Quality = 'GOOD' | 'SIMULATED' | 'UNCERTAIN' | 'STALE' | 'COMM_ERROR' | 'BAD'
export type ConnectionState =
  | 'DISCONNECTED'
  | 'CONNECTING'
  | 'HANDSHAKE'
  | 'CONNECTED'
  | 'ERROR'
  | 'RECONNECTING'
  | 'NOT_CONFIGURED'
export type DataSource = 'SIMULATED' | 'EQUIPMENT' | 'MIXED'
export type Severity = 'INFO' | 'ATTENTION' | 'CRITICAL'
export type EventStatus = 'OPEN' | 'ACKNOWLEDGED' | 'RESOLVED' | 'EXPIRED'
export type EvidenceLevel =
  | 'MANUFACTURER_DOC'
  | 'MACHINE_DOC'
  | 'FIELD_CONFIRMED'
  | 'FIELD_OBSERVED'
  | 'FORJA_RULE'
  | 'TECHNICAL_OPINION'
  | 'HYPOTHESIS'
export type DeltaKind = 'pct' | 'points' | 'abs' | 'none'

export interface TagView {
  tag: string
  label_pt: string
  unit: string
  kind: 'CONTINUOUS' | 'DISCRETE' | 'STATUS_RAW' | null
  decimals: number
  explanation_pt: string
  value: number | null
  ts_utc: string | null
  age_s: number | null
  source: string
  reason_pt: string | null
  raw_hex: string | null
  quality: Quality
  quality_pt: string
  is_usable: boolean
}

export interface EquipmentSummary {
  id: string
  name: string
  display_path: string
  application: string
  application_evidence: string
  is_example: boolean
  driver: string
  data_source: 'SIMULATED' | 'EQUIPMENT'
  needs_configuration: boolean
  mapping_profile: string
}

export interface EventBrief {
  id: string
  type: string
  title_pt: string
  severity: Severity
  severity_pt: string
  status: EventStatus
  start_utc: string
  end_utc: string | null
  summary_pt: string
}

export interface PlantCard extends EquipmentSummary {
  state_pt: string
  connection: ConnectionState
  connection_pt: string
  is_stale: boolean
  last_read_utc: string | null
  last_event: EventBrief | null
  open_event_count: number
  active_anomaly_pt: string | null
  mass_flow: TagView | null
}

export interface PlantResponse {
  data_source: DataSource
  data_source_pt: string
  generated_at_utc: string
  count: number
  cards: PlantCard[]
}

export interface LiveView {
  equipment_id: string
  name: string
  data_source: 'SIMULATED' | 'EQUIPMENT'
  connection: ConnectionState
  connection_pt: string
  is_stale: boolean
  stale_for_s: number | null
  last_read_utc: string | null
  last_ok_utc: string | null
  generated_at_utc: string
  tags: TagView[]
}

export interface RuntimeStatus {
  equipment_id: string
  driver: string
  support_state: string
  support_state_pt: string
  connection: ConnectionState
  connection_pt: string
  last_read_utc: string | null
  last_ok_utc: string | null
  latency_ms: number | null
  consecutive_errors: number
  reconnect_count: number
  restart_count: number
  samples_per_min: number
  is_stale: boolean
  stale_for_s: number | null
  detail_pt: string
}

export interface ComponentInfo {
  type: string
  model: string
  serial: string
  quantity: number | null
  evidence: string
  note_pt: string
}

export interface EquipmentProfile {
  schema_version: number
  id: string
  name: string
  plant: string
  area: string
  line: string
  application: string
  application_evidence: string
  controller: {
    manufacturer: string
    model: string
    software_version: string
    kgr: string
    host_file: string
  }
  host_interface: {
    type: string
    slot: string
    model: string
    part_number: string
    mac: string
    evidence: string
  }
  communication: {
    driver: string
    protocol: string
    ip: string
    subnet: string
    gateway: string
    port: number | string
    unit_id: number | string
    poll_interval_s: number
    timeout_s: number
    connect_timeout_s: number
    stale_after_s: number
    max_block_size: number | string
    options: Record<string, unknown>
  }
  mapping_profile: string
  components: ComponentInfo[]
  is_example: boolean
  reference_values: Record<string, number>
  notes_pt: string
}

export interface EquipmentDetail {
  profile: EquipmentProfile
  mapping: {
    mapping_id: string
    version: number
    driver: string
    source: string
    entries: number
    readable: number
    unknown: number
    tags: string[]
  }
}

export interface HistoryPoint {
  ts_utc: string
  value: number | null
  quality: Quality
  min: number | null
  max: number | null
  n: number
}

export interface HistorySeries {
  equipment_id: string
  tag: string
  resolution: string
  bucket_s: number
  points: HistoryPoint[]
  gap_count: number
  stale_count: number
  downsampled: boolean
}

export interface HistoryResponse {
  equipment_id: string
  from_utc: string
  to_utc: string
  max_points: number
  interpolated: false
  series: HistorySeries[]
}

export interface SourceRef {
  id: string
  kind:
    | 'rule'
    | 'case'
    | 'document'
    | 'field_observation'
    | 'manufacturer_doc'
    | 'machine_doc'
    | 'opinion'
  title: string
  reference: string
  evidence_level: EvidenceLevel
}

export interface WhatChangedItem {
  tag: string
  label_pt: string
  unit: string
  before: number | null
  now: number | null
  delta: number | null
  delta_kind: DeltaKind
  changed_first: boolean
  ts_start_utc: string | null
  text_pt: string
}

export interface TimelinePoint {
  ts_utc: string
  text_pt: string
  kind: 'forja' | 'kcm' | 'human'
  tag: string | null
}

export interface EventContext {
  pre_window_s: number
  post_window_s: number
  what_changed: WhatChangedItem[]
  timeline: TimelinePoint[]
  gap_count: number
  stale_count: number
  comm_error_count: number
  pre_sample_count: number
  during_sample_count: number
  post_sample_count: number
  pre_samples?: unknown[]
  during_samples?: unknown[]
  post_samples?: unknown[]
}

export interface EventView {
  schema_version: string
  id: string
  equipment_id: string
  type: string
  title_pt: string
  start_utc: string
  end_utc: string | null
  severity: Severity
  severity_pt: string
  summary_pt: string
  rule_id: string
  rule_version: number
  context: EventContext
  sources: SourceRef[]
  quality: Quality
  quality_pt: string
  status: EventStatus
  status_pt: string
  acked_by: string | null
  acked_at_utc: string | null
  resolution: {
    resolved_at_utc: string
    resolved_by: string
    resolution_class: string
    note_pt: string
  } | null
  dedupe_key: string
  diagnosis_ref: string | null
  is_open: boolean
  duration_s: number | null
}

export interface EventsResponse {
  equipment_id: string
  count: number
  events: EventView[]
}

export interface EvidenceItem {
  id: string
  text_pt: string
  tag: string | null
  value: number | null
  unit: string | null
  quality: Quality | null
  evidence_level: EvidenceLevel
  ts_utc: string | null
}

export interface Hypothesis {
  id: string
  text_pt: string
  evidence_level: EvidenceLevel
  rationale_pt: string
  verification_ids: string[]
  source_ids: string[]
}

export interface NextCheck {
  id: string
  order: number
  text_pt: string
  how_pt: string
  safety_pt: string
  evidence_level: EvidenceLevel
  source_ids: string[]
}

export interface Diagnosis {
  diagnosis_schema_version: string
  diagnosis_id: string
  event_id: string
  equipment_id: string
  generated_at_utc: string
  engine_version: string
  summary: { title_pt: string; text_pt: string; internal_code: string; severity: Severity }
  evidence: EvidenceItem[]
  what_changed: WhatChangedItem[]
  hypotheses: Hypothesis[]
  next_checks: NextCheck[]
  sources: SourceRef[]
  caveats: { text_pt: string }[]
  evidence_summary: {
    weakest_level: EvidenceLevel | null
    strongest_level: EvidenceLevel | null
    counts: Record<string, number>
    note_pt: string
  }
}

export interface About {
  name: string
  edge_name: string
  version: string
  diagnosis_schema_version: string
  read_only: true
  data_source: DataSource
  data_source_pt: string
  uptime_s: number
  started_at_utc: string | null
  python: string
  sqlite: string
  equipment_count: number
  dev_mode: boolean
  docs_url: string | null
  timezone: string
}

export interface DriverInfo {
  name: string
  state: string
  state_pt: string
  library: string
  version: string
  reason_pt: string
}

export interface DriversResponse {
  drivers: Record<string, DriverInfo>
  equipments: Array<{
    equipment_id: string
    driver: string
    protocol: string
    ip_known: boolean
    needs_configuration: boolean
    support_state: string
    support_state_pt: string
    driver_state: string
    message_pt: string
    connection: ConnectionState | null
    connection_pt: string | null
  }>
  read_only: true
}

export interface SimulatorView {
  equipment_id: string
  controls: unknown
  scenarios: Array<{ code: string; title_pt: string; description_pt: string }>
  sliders: string[]
  note_pt: string
}

/** Erro normalizado: código interno + texto em português pronto para a tela. */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    public readonly message_pt: string,
    public readonly details: unknown = null,
  ) {
    super(message_pt)
    this.name = 'ApiError'
  }
}

export const API_BASE = '/api/v1'

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (init.body != null) headers['Content-Type'] = 'application/json'
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, { ...init, cache: 'no-store', headers })
  } catch {
    throw new ApiError(0, 'NETWORK', 'Sem resposta do serviço local. O Edge está em execução?')
  }
  if (!res.ok) {
    let code = `HTTP_${res.status}`
    let message = 'Erro ao consultar o serviço local.'
    let details: unknown = null
    try {
      const body = (await res.json()) as {
        error?: { code: string; message_pt: string; details: unknown }
      }
      if (body?.error) {
        code = body.error.code
        message = body.error.message_pt
        details = body.error.details
      }
    } catch {
      // corpo não era JSON: fica a mensagem padrão
    }
    throw new ApiError(res.status, code, message, details)
  }
  return (await res.json()) as T
}

function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v != null && v !== '') sp.set(k, String(v))
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

export function isNotFound(err: unknown): boolean {
  return err instanceof ApiError && err.status === 404
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message_pt
  if (err instanceof Error) return err.message
  return 'Erro inesperado.'
}

export const api = {
  about: () => request<About>('/system/about'),
  plant: () => request<PlantResponse>('/plant'),
  equipments: () => request<{ equipments: EquipmentSummary[]; count: number }>('/equipments'),
  equipment: (id: string) => request<EquipmentDetail>(`/equipments/${encodeURIComponent(id)}`),
  status: (id: string) => request<RuntimeStatus>(`/equipments/${encodeURIComponent(id)}/status`),
  live: (id: string) => request<LiveView>(`/equipments/${encodeURIComponent(id)}/live`),
  history: (
    id: string,
    tags: string[],
    opts: { from?: string; to?: string; maxPoints?: number } = {},
  ) =>
    request<HistoryResponse>(
      `/equipments/${encodeURIComponent(id)}/history${qs({
        tags: tags.join(','),
        from: opts.from,
        to: opts.to,
        maxPoints: opts.maxPoints,
      })}`,
    ),
  events: (id: string, opts: { limit?: number; open_only?: boolean } = {}) =>
    request<EventsResponse>(
      `/equipments/${encodeURIComponent(id)}/events${qs({
        limit: opts.limit ?? 50,
        open_only: opts.open_only,
      })}`,
    ),
  event: (eventId: string) => request<EventView>(`/events/${encodeURIComponent(eventId)}`),
  /** Diagnóstico do evento; `null` quando ainda não existe (404 DIAGNOSIS_NOT_FOUND). */
  diagnosis: async (eventId: string): Promise<Diagnosis | null> => {
    try {
      return await request<Diagnosis>(`/events/${encodeURIComponent(eventId)}/diagnosis`)
    } catch (err) {
      if (err instanceof ApiError && err.code === 'DIAGNOSIS_NOT_FOUND') return null
      throw err
    }
  },
  drivers: () => request<DriversResponse>('/communication/drivers'),
  simulator: (id: string) => request<SimulatorView>(`/simulator/${encodeURIComponent(id)}`),
  setScenario: (id: string, scenario: string) =>
    request<SimulatorView>(`/simulator/${encodeURIComponent(id)}/scenario`, {
      method: 'POST',
      body: JSON.stringify({ scenario }),
    }),
  setControls: (id: string, overrides: Record<string, number>) =>
    request<SimulatorView>(`/simulator/${encodeURIComponent(id)}/controls`, {
      method: 'POST',
      body: JSON.stringify({ overrides }),
    }),
  clearControls: (id: string) =>
    request<SimulatorView>(`/simulator/${encodeURIComponent(id)}/controls`, { method: 'DELETE' }),
}

/** Rótulos de qualidade (espelham Quality.label_pt no domínio). */
export const QUALITY_PT: Record<Quality, string> = {
  GOOD: 'Validado',
  SIMULATED: 'Simulado',
  UNCERTAIN: 'Não validado',
  STALE: 'Valor antigo',
  COMM_ERROR: 'Sem comunicação',
  BAD: 'Inválido',
}

/** Quanto maior, pior (espelha Quality.rank). */
export const QUALITY_RANK: Record<Quality, number> = {
  GOOD: 0,
  SIMULATED: 1,
  UNCERTAIN: 2,
  STALE: 3,
  BAD: 4,
  COMM_ERROR: 5,
}

export function isUsable(q: Quality | null | undefined): boolean {
  return q === 'GOOD' || q === 'SIMULATED' || q === 'UNCERTAIN'
}

export function worstQuality(qualities: Array<Quality | null | undefined>): Quality {
  let worst: Quality | null = null
  for (const q of qualities) {
    if (!q) continue
    if (worst == null || QUALITY_RANK[q] > QUALITY_RANK[worst]) worst = q
  }
  return worst ?? 'COMM_ERROR'
}

/** Rótulos de nível de evidência (espelham EvidenceLevel.label_pt). */
export const EVIDENCE_PT: Record<EvidenceLevel, string> = {
  MANUFACTURER_DOC: 'Documentado pelo fabricante',
  MACHINE_DOC: 'Documento da máquina',
  FIELD_CONFIRMED: 'Confirmado em campo',
  FIELD_OBSERVED: 'Observado em campo',
  FORJA_RULE: 'Regra Forja',
  TECHNICAL_OPINION: 'Opinião técnica',
  HYPOTHESIS: 'Hipótese',
}

export const EVIDENCE_STRENGTH: Record<EvidenceLevel, number> = {
  MANUFACTURER_DOC: 7,
  MACHINE_DOC: 6,
  FIELD_CONFIRMED: 5,
  FIELD_OBSERVED: 4,
  FORJA_RULE: 3,
  TECHNICAL_OPINION: 2,
  HYPOTHESIS: 1,
}

export const SOURCE_KIND_PT: Record<SourceRef['kind'], string> = {
  rule: 'Regra',
  case: 'Caso',
  document: 'Documento',
  field_observation: 'Observação de campo',
  manufacturer_doc: 'Documento do fabricante',
  machine_doc: 'Documento da máquina',
  opinion: 'Opinião técnica',
}

/** Estados da planta em português (espelham plant.py) → tom visual. */
export type StateTone = 'ok' | 'warn' | 'crit' | 'info' | 'neutral' | 'unknown'

export function stateTone(statePt: string | null | undefined): StateTone {
  switch (statePt) {
    case 'Normal':
      return 'ok'
    case 'Atenção':
      return 'warn'
    case 'Crítico':
      return 'crit'
    case 'Sem comunicação':
      return 'info'
    case 'Parado':
      return 'neutral'
    default:
      return 'unknown'
  }
}

export function severityTone(sev: Severity | null | undefined): StateTone {
  if (sev === 'CRITICAL') return 'crit'
  if (sev === 'ATTENTION') return 'warn'
  return 'info'
}

export function connectionTone(c: ConnectionState | null | undefined): StateTone {
  if (c === 'CONNECTED') return 'ok'
  if (c == null || c === 'NOT_CONFIGURED') return 'unknown'
  return 'info'
}

/** Glifo para o texto da opção do seletor (texto puro, sem cor). */
export function stateGlyph(statePt: string | null | undefined): string {
  switch (stateTone(statePt)) {
    case 'ok':
      return '●'
    case 'warn':
      return '▲'
    case 'crit':
      return '✕'
    case 'info':
      return '○'
    case 'neutral':
      return '■'
    default:
      return '?'
  }
}
