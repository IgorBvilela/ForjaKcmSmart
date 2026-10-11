/** Tela Agora: contrato de GET /api/v1/situation e a frase pronta para o gerente copiar. */

import {
  request,
  type DataSource,
  type EventStatus,
  type EvidenceLevel,
  type Severity,
  type TagView,
} from './api'
import { fmtTime } from './format'

export type SituationGroup = 'problem' | 'no_data' | 'stopped' | 'normal'
export type SinceBasis = 'EVENT' | 'LAST_OK' | 'HISTORIAN' | 'BEFORE_WINDOW' | 'UNDETERMINED'
export type SituationTone = 'ok' | 'warn' | 'crit' | 'info'

export interface VoiceEvent {
  id: string
  title_pt: string
  severity: Severity
  severity_pt: string
  start_utc: string
  status: EventStatus
  status_pt: string
  acked_by: string | null
  origin: 'RULE' | 'EARLY_WARNING'
  origin_pt: string
}

export interface KcmVoice {
  state: 'ACTIVE'
  state_pt: string
  code: string | null
  title_pt: string | null
  catalogued: boolean
  source_pt: string
  since_utc: string | null
  since_basis: SinceBasis
  since_pt: string | null
}

export interface ChangedFirst {
  tag: string
  label_pt: string
  lead_s: number
  text_pt: string
  summary_pt: string
}

export interface NextCheckView {
  text_pt: string
  how_pt: string | null
  evidence_level: EvidenceLevel
  evidence_pt: string
}

export interface FocusView {
  event_id: string
  title_pt: string
  origin: 'RULE' | 'EARLY_WARNING'
  origin_pt: string
  severity: Severity
  start_utc: string
  status: EventStatus
  acked_by: string | null
  changed_first: ChangedFirst | null
  hypothesis_pt: string | null
  next_check: NextCheckView | null
  diagnosis_available: boolean
}

export interface SituationEntry {
  id: string
  name: string
  state_pt: string
  group: SituationGroup
  severity: Severity | null
  since_utc: string | null
  since_basis: SinceBasis | null
  reason_pt: string | null
  is_simulated: boolean
  data_source: 'SIMULATED' | 'EQUIPMENT'
  mass_flow: TagView | null
  voices: {
    kcm_alarm: KcmVoice | null
    forja_events: VoiceEvent[]
    early_warnings: VoiceEvent[]
    early_warning_confirming: number
  }
  focus: FocusView | null
}

export interface SituationSummary {
  total: number
  attention: number
  critical: number
  no_data: number
  stopped: number
  normal: number
  headline_pt: string
  tone: SituationTone
}

export interface SituationResponse {
  generated_at_utc: string
  data_source: DataSource
  data_source_pt: string
  summary: SituationSummary
  equipments: SituationEntry[]
}

export const situationApi = {
  get: () => request<SituationResponse>('/situation'),
}

/** "desde 14:32", "há mais de 24 h" ou "início não determinado". Nunca inventa um horário. */
export function sinceText(entry: SituationEntry): string | null {
  const basis = entry.since_basis
  if (basis == null) return null
  if (basis === 'BEFORE_WINDOW') return 'há mais de 24 h'
  if (basis === 'UNDETERMINED' || entry.since_utc == null) return 'início não determinado'
  const time = fmtTime(entry.since_utc, false)
  return basis === 'LAST_OK' ? `sem leitura desde ${time}` : `desde ${time}`
}

/** Frase pronta para o gerente copiar, montada só com os dados da tela (sem IA). */
export function readyPhrase(entry: SituationEntry): string {
  const parts: string[] = []
  const since = sinceText(entry)
  const focus = entry.focus
  const kcm = entry.voices.kcm_alarm
  if (focus) {
    parts.push(`${entry.name}: ${focus.title_pt}${since ? `, ${since}` : ''}.`)
    if (focus.changed_first) parts.push(`${focus.changed_first.label_pt} saiu do padrão primeiro.`)
    if (focus.next_check) parts.push(`Primeira verificação: ${focus.next_check.text_pt}`)
  } else if (kcm) {
    const what = kcm.title_pt ? ` (${kcm.title_pt})` : ''
    parts.push(`${entry.name}: alarme do KCM ${kcm.code ?? ''}${what} ativo${since ? `, ${since}` : ''}.`)
  }
  if (focus && kcm) parts.push(`Alarme do KCM ${kcm.code ?? ''} também ativo.`)
  return parts.join(' ').replace(/\s+/g, ' ').trim()
}
