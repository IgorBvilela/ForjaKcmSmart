/** Comissionamento / validação em campo: tipos e chamadas (src/forja/api/routers/commissioning.py). */
import { API_BASE, ApiError, type Quality } from './api'

export type CheckResult = 'MATCH' | 'MISMATCH' | 'NOT_EXPOSED' | 'NOT_CHECKED'

export const RESULT_PT: Record<CheckResult, string> = {
  MATCH: 'Confere',
  MISMATCH: 'Diverge',
  NOT_EXPOSED: 'Não exposta pelo KCM',
  NOT_CHECKED: 'Não conferida',
}

export interface CommissioningHeader {
  technician: string
  authorized_by: string
  visit_date: string
  protocol_found: string
  kcm_software_version: string
  host_interface: string
  ip: string
  subnet_mask: string
  gateway: string
  mapping_id: string
  mapping_version: number | null
  host_counters_before: string
  host_counters_after: string
  notes_pt: string
}

export interface CommissioningSession {
  id: string
  equipment_id: string
  created_at_utc: string
  updated_at_utc: string
  status: 'OPEN' | 'CLOSED'
  status_pt?: string
  header: CommissioningHeader
  conclusion_pt: string
}

export interface CommissioningCheck {
  id: number | null
  session_id: string
  ts_utc: string
  tag: string
  label_pt: string
  unit: string
  address_text: string
  forja_value: number | null
  forja_raw_hex: string | null
  forja_quality: Quality | null
  kcm_value: number | null
  kcm_text: string
  difference: number | null
  result: CheckResult
  result_pt: string
  note_pt: string
  technician: string
}

export interface SessionDetail {
  session: CommissioningSession
  status_pt: string
  checks: CommissioningCheck[]
  summary: Record<CheckResult, number>
  covered_tags: string[]
  suggested_tags: string[]
}

export interface SessionList {
  equipment_id: string
  sessions: CommissioningSession[]
  suggested_tags: string[]
  prefill: Partial<CommissioningHeader>
}

export interface CheckInput {
  tag: string
  address_text: string
  forja_value: number | null
  forja_raw_hex: string | null
  forja_quality: Quality | null
  kcm_value: number | null
  kcm_text: string
  result: CheckResult
  note_pt: string
  technician: string
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
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
      const body = (await res.json()) as { error?: { code: string; message_pt: string; details: unknown } }
      if (body?.error) {
        code = body.error.code
        message = body.error.message_pt
        details = body.error.details
      }
    } catch {
      // corpo não era JSON
    }
    throw new ApiError(res.status, code, message, details)
  }
  return (await res.json()) as T
}

const enc = encodeURIComponent

export const commissioningApi = {
  list: (eq: string) => call<SessionList>(`/equipments/${enc(eq)}/commissioning`),
  open: (eq: string, header: CommissioningHeader) =>
    call<SessionDetail>(`/equipments/${enc(eq)}/commissioning`, {
      method: 'POST',
      body: JSON.stringify({ header }),
    }),
  get: (sid: string) => call<SessionDetail>(`/commissioning/${enc(sid)}`),
  header: (sid: string, header: CommissioningHeader, user: string) =>
    call<SessionDetail>(`/commissioning/${enc(sid)}/header`, {
      method: 'POST',
      body: JSON.stringify({ header, user }),
    }),
  check: (sid: string, check: CheckInput) =>
    call<{ check: CommissioningCheck }>(`/commissioning/${enc(sid)}/checks`, {
      method: 'POST',
      body: JSON.stringify(check),
    }),
  close: (sid: string, conclusion: string, countersAfter: string, technician: string) =>
    call<SessionDetail>(`/commissioning/${enc(sid)}/close`, {
      method: 'POST',
      body: JSON.stringify({
        conclusion_pt: conclusion,
        host_counters_after: countersAfter,
        technician,
      }),
    }),
  csvUrl: (sid: string) => `${API_BASE}/commissioning/${enc(sid)}/report.csv`,
}

/** "1.281,5" ou "1281.5" → 1281.5; vazio ou texto → null. */
export function parseNumberPt(text: string): number | null {
  const t = text.trim()
  if (!t) return null
  const normalized = t.includes(',') ? t.replace(/\./g, '').replace(',', '.') : t
  const n = Number(normalized)
  return Number.isFinite(n) ? n : null
}
