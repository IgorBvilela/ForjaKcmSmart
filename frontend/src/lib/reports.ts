/** Fase M: backup, relatório por período e exportações (routers/backups.py e reports.py). */
import { API_BASE, request } from './api'

const enc = encodeURIComponent

export interface BackupItem {
  name: string
  path: string
  size_bytes: number
  valid: boolean
  error_pt?: string
  created_at_utc?: string
  app_version?: string
  files?: { kind: 'historian' | 'core' | 'config'; file_name: string; size_bytes: number }[]
  has_config?: boolean
  restore_command: string
  restore_config_command: string
}

export interface BackupList {
  auto: boolean
  schedule: string
  keep_last: number
  next_run_utc: string | null
  folder: string
  restore_note_pt: string
  count: number
  backups: BackupItem[]
}

export interface VerifyResult {
  name: string
  ok: boolean
  message_pt: string
}

export interface TagReport {
  tag: string
  label_pt: string
  unit: string
  decimals: number
  coverage: number
  coverage_pt: string
  average: number | null
  min: number | null
  max: number | null
  comm_error_points: number
  qualities: Record<string, number>
  resolution: string
}

export interface EventGroup {
  origin: 'RULE' | 'EARLY_WARNING'
  origin_pt: string
  type: string
  title_pt: string
  count: number
  duration_in_period_s: number
  worst_severity: 'INFO' | 'ATTENTION' | 'CRITICAL'
}

export interface ReportEvent {
  id: string
  origin: 'RULE' | 'EARLY_WARNING'
  origin_pt: string
  type: string
  title_pt: string
  severity: 'INFO' | 'ATTENTION' | 'CRITICAL'
  severity_pt: string
  status: string
  start_utc: string
  end_utc: string | null
  duration_in_period_s: number
  quality: string
  first_label_pt: string | null
  lead_s: number | null
  summary_pt: string
  acked_by: string | null
}

export interface KcmAlarmEpisode {
  code: string
  title_pt: string
  qualifier_pt: string
  times: number
  first_utc: string
  last_utc: string
}

export interface PeriodReport {
  equipment_id: string
  name: string
  display_path: string
  application: string
  data_source: 'SIMULATED' | 'EQUIPMENT'
  from_utc: string
  to_utc: string
  period_pt: string
  generated_at_utc: string
  timezone: string
  narrative_pt: string[]
  tags: TagReport[]
  event_groups: EventGroup[]
  events: ReportEvent[]
  events_total: number
  kcm_alarms: KcmAlarmEpisode[]
  caveats_pt: string[]
}

export const reportsApi = {
  backups: () => request<BackupList>('/backups'),
  createBackup: (user: string, reason: string) =>
    request<BackupItem>('/backups', { method: 'POST', body: JSON.stringify({ user, reason_pt: reason }) }),
  verifyBackup: (name: string) => request<VerifyResult>(`/backups/${enc(name)}/verify`),
  report: (id: string, from: string, to: string) =>
    request<PeriodReport>(`/equipments/${enc(id)}/report?from=${enc(from)}&to=${enc(to)}`),
  eventsCsvUrl: (id: string, from: string, to: string, dialect: 'br' | 'std') =>
    `${API_BASE}/equipments/${enc(id)}/events.csv?from=${enc(from)}&to=${enc(to)}&dialect=${dialect}`,
  logsCsvUrl: () => `${API_BASE}/system/logs.csv`,
}

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let v = n / 1024
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i += 1
  }
  return `${v.toLocaleString('pt-BR', { maximumFractionDigits: v < 10 ? 1 : 0 })} ${units[i]}`
}
