/** Turnos da planta e resumo do turno para imprimir. Somente leitura; contrato em
 *  docs/contracts/CONTRATOS_Q.md (`GET /api/v1/shifts` e `GET /api/v1/shift-summary`). */

import { request, type DataSource, type Severity } from './api'
import type { TimeSplitItem } from './timesplit'

export interface ShiftInfo {
  index: number
  name: string
  start: string
  end: string
  crosses_midnight: boolean
}

export interface ShiftsResponse {
  timezone: string
  /** Hoje no relógio da planta (AAAA-MM-DD). */
  today: string
  shifts: ShiftInfo[]
  current: { index: number; date: string } | null
}

export interface ShiftEventRow {
  id: string
  start_utc: string
  end_utc: string | null
  title_pt: string
  severity: Severity
  severity_pt: string
  status: string
  origin: string
}

export interface KcmAlarmEpisode {
  code: string
  title_pt: string
  qualifier_pt: string
  times: number
  first_utc: string
  last_utc: string
}

export interface ShiftSummaryItem extends TimeSplitItem {
  data_source: 'SIMULATED' | 'EQUIPMENT'
  events: ShiftEventRow[]
  events_total: number
  early_warnings: number
  kcm_alarms: KcmAlarmEpisode[]
}

export interface ShiftSummary {
  from_utc: string
  to_utc: string
  definition_pt: string
  evidence_level: 'FORJA_RULE'
  timezone: string
  generated_at_utc: string
  in_progress: boolean
  shift: Omit<ShiftInfo, 'crosses_midnight'> | null
  date: string | null
  data_source: DataSource | null
  equipments: ShiftSummaryItem[]
}

export const shiftApi = {
  shifts: () => request<ShiftsResponse>('/shifts'),
  /** Turno `index` que começa em `date` (AAAA-MM-DD, no relógio da planta). */
  byShift: (index: number, date: string) =>
    request<ShiftSummary>(`/shift-summary?${new URLSearchParams({ shift: String(index), date })}`),
  byPeriod: (from: Date, to: Date) =>
    request<ShiftSummary>(
      `/shift-summary?${new URLSearchParams({ from: from.toISOString(), to: to.toISOString() })}`,
    ),
}

/** Valor de `<input type="datetime-local">` no relógio deste computador. */
export function localInputValue(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}
