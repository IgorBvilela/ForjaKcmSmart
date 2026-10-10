/** Fase F: alertas, aviso antecipado e casos anteriores (src/forja/api/routers/intelligence.py). */
import { request, type EventView, type Quality, type Severity, type SourceRef, type StateTone } from './api'

const enc = encodeURIComponent

export type KcmAlarmState = 'ACTIVE' | 'NONE' | 'UNKNOWN' | 'NOT_MAPPED'

export interface KcmAlarm {
  state: KcmAlarmState
  state_pt: string
  source_pt: string
  note_pt: string
  code?: string | null
  title_pt?: string
  qualifier_pt?: string
  catalogued?: boolean
  since_utc?: string | null
  quality?: Quality
  quality_pt?: string
}

export interface AlertsResponse {
  equipment_id: string
  name: string
  data_source: 'SIMULATED' | 'EQUIPMENT'
  kcm_alarm: KcmAlarm
  forja_events: EventView[]
  early_warnings: EventView[]
  counts: {
    kcm_alarm: number
    forja_events: number
    forja_events_unacknowledged: number
    early_warnings: number
  }
  notes_pt: { kcm: string; forja: string; early_warning: string }
  generated_at_utc: string
}

export type EwState = 'ACTIVE' | 'CONFIRMING' | 'NORMAL' | 'INSUFFICIENT' | 'PENDING'
export type SignalVerdict = 'MET' | 'NOT_MET' | 'INSUFFICIENT'

export interface EwSignal {
  tag: string
  label_pt: string
  unit: string
  decimals: number
  kind: 'trend' | 'deviation' | 'stable' | 'near_reference' | 'state'
  kind_pt: string
  ref_tag: string | null
  ref_label_pt: string | null
  verdict: SignalVerdict | null
  verdict_pt: string
  text_pt: string
  limit_pt: string
  measured: number | null
  fit: number | null
  coverage: number | null
  before: number | null
  now: number | null
  spark: Array<number | null>
}

export interface EwRule {
  id: string
  version: number
  title_pt: string
  description_pt: string
  severity: Severity
  severity_pt: string
  state: EwState
  state_pt: string
  preview: boolean
  window_s: number
  window_pt: string
  recent_s: number
  recent_pt: string
  baseline: 'window_start' | 'before_window'
  baseline_pt: string
  evaluate_every_s: number
  evaluate_every_pt: string
  persist_evaluations: number
  clear_evaluations: number
  min_coverage: number
  met_streak: number
  last_evaluated_utc: string | null
  quality: Quality | null
  open_event_id: string | null
  open_since_utc: string | null
  signals: EwSignal[]
  threshold_basis: string
  threshold_note_pt: string
  sources: SourceRef[]
  applications: string[]
}

export interface EarlyWarningResponse {
  equipment_id: string
  name: string
  application: string
  disclaimer_pt: string
  available: boolean
  rules: EwRule[]
  active_count: number
  recent: EventView[]
  generated_at_utc: string
}

export interface CaseMeasurement {
  what_pt: string
  value: string
  nature_pt: string
  evidence: string
  evidence_pt: string
}

export interface FieldCase {
  id: string
  title_pt: string
  plant: string
  area: string
  equipment: string
  equipment_ids: string[]
  application: string
  period_pt: string
  evidence: string
  evidence_pt: string
  confirmed_cause: string
  cause_confirmed: boolean
  cause_pt: string
  observed_facts_pt: string[]
  interventions_pt: string[]
  measurements: CaseMeasurement[]
  calibration_reported_pt: string[]
  learned_rule_pt: string
  related_rules: string[]
  related_diagnostics: string[]
  sources: SourceRef[]
  notes_pt: string
}

export interface RecurrenceGroup {
  origin: 'RULE' | 'EARLY_WARNING'
  origin_pt: string
  type: string
  title_pt: string
  rule_id: string
  severity: Severity
  count: number
  open_count: number
  acknowledged_count: number
  first_start_utc: string
  last_start_utc: string
  last_event_id: string
  typical_duration_s: number | null
  first_changed: { tag: string; label_pt: string; count: number } | null
  resolutions: Record<string, number>
  narrative_pt: string[]
  recent_event_ids: string[]
}

export interface CasesResponse {
  equipment_id: string
  name: string
  application: string
  field_cases: FieldCase[]
  same_application_cases: FieldCase[]
  recurrence: RecurrenceGroup[]
  note_pt: string
  generated_at_utc: string
}

export const intelligenceApi = {
  alerts: (id: string) => request<AlertsResponse>(`/equipments/${enc(id)}/alerts`),
  earlyWarning: (id: string) => request<EarlyWarningResponse>(`/equipments/${enc(id)}/early-warning`),
  cases: (id: string) => request<CasesResponse>(`/equipments/${enc(id)}/cases`),
  knowledgeCases: () => request<{ count: number; cases: FieldCase[]; note_pt: string }>('/knowledge/cases'),
  /** Reconhecer na Forja: registra quem viu e quando (auditado). Não altera o KCM. */
  ack: (eventId: string, user: string, note: string) =>
    request<EventView>(`/events/${enc(eventId)}/ack`, {
      method: 'POST',
      body: JSON.stringify({ user, note_pt: note }),
    }),
}

export const EW_STATE_TONE: Record<EwState, StateTone> = {
  ACTIVE: 'warn',
  CONFIRMING: 'info',
  NORMAL: 'ok',
  INSUFFICIENT: 'unknown',
  PENDING: 'neutral',
}

export const KCM_ALARM_TONE: Record<KcmAlarmState, StateTone> = {
  ACTIVE: 'crit',
  NONE: 'ok',
  UNKNOWN: 'unknown',
  NOT_MAPPED: 'neutral',
}

export const VERDICT_TONE: Record<SignalVerdict, StateTone> = {
  MET: 'warn',
  NOT_MET: 'ok',
  INSUFFICIENT: 'unknown',
}

const USER_KEY = 'forja.ack.user'

/** Nome usado no último reconhecimento (conveniência local deste navegador). */
export function rememberedUser(): string {
  try {
    return localStorage.getItem(USER_KEY) ?? ''
  } catch {
    return ''
  }
}

export function rememberUser(name: string): void {
  try {
    localStorage.setItem(USER_KEY, name)
  } catch {
    // armazenamento indisponível: o nome só não fica lembrado
  }
}

/** Mesmo padrão do backend (AckBody.user). */
export const ACK_USER_PATTERN = /^[\p{L}\p{N}_ .@-]{1,64}$/u
