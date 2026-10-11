/** Medida de tempo por dosador e período (FORJA_RULE): dentro do normal, fora do normal e sem
 *  dados. Somente leitura; contrato em docs/contracts/CONTRATOS_Q.md (`GET /api/v1/time-split`). */

import { request } from './api'

export interface TimeSplitItem {
  id: string
  name: string
  reference_tag: string | null
  span_s: number
  normal_s: number
  out_s: number
  no_data_s: number
  normal_pct: number
  out_pct: number
  no_data_pct: number
  evidence_level: 'FORJA_RULE'
}

export interface TimeSplitResponse {
  from_utc: string
  to_utc: string
  definition_pt: string
  evidence_level: 'FORJA_RULE'
  equipments: TimeSplitItem[]
}

/** A medida de todos os dosadores, de `from` até `to` (sem `to`, até agora). */
export function plantTimeSplit(from: Date, to?: Date): Promise<TimeSplitResponse> {
  const params = new URLSearchParams({ from: from.toISOString() })
  if (to) params.set('to', to.toISOString())
  return request<TimeSplitResponse>(`/time-split?${params.toString()}`)
}

/** Meia-noite de hoje no relógio local: o começo do "hoje" do placar. */
export function startOfToday(now: Date = new Date()): Date {
  return new Date(now.getFullYear(), now.getMonth(), now.getDate())
}

/** Do pior para o melhor: quem ficou menos tempo dentro do normal primeiro; empate pelo nome. */
export function worstFirst(items: readonly TimeSplitItem[]): TimeSplitItem[] {
  return [...items].sort((a, b) => a.normal_pct - b.normal_pct || a.name.localeCompare(b.name, 'pt-BR'))
}

/** Porcentagem inteira que nunca arredonda para 0 ou 100 quando não é exatamente isso:
 *  99,6% de tempo normal com 0,4% fora não vira "100%". */
export function pctText(pct: number): string {
  if (!Number.isFinite(pct) || pct <= 0) return '0'
  if (pct >= 100) return '100'
  if (pct < 1) return '<1'
  if (pct > 99) return '99'
  return String(Math.round(pct))
}

/** Duração em horas e minutos: "14 h 13 min", "45 min", "<1 min", "0 min". */
export function hoursText(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return '0 min'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 1) return '<1 min'
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return h ? `${h} h ${String(m).padStart(2, '0')} min` : `${m} min`
}
