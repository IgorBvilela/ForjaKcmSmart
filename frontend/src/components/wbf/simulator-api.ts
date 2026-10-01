/**
 * Cliente mínimo das rotas que o simulador e o dosador consomem.
 *
 * Fica em components/wbf/ até o cliente compartilhado (`src/lib/api.ts`, bloco B) existir; aí a
 * SimulatorPage troca o import e este arquivo some. Só 127.0.0.1 (mesma origem); nada sai da máquina.
 * Formatos conferidos em src/forja/api/routers/{equipments,simulator}.py e api/errors.py.
 */

export type QualityCode = 'GOOD' | 'SIMULATED' | 'UNCERTAIN' | 'STALE' | 'COMM_ERROR' | 'BAD'

export interface LiveTag {
  tag: string
  label_pt: string
  unit: string
  kind: 'CONTINUOUS' | 'DISCRETE' | null
  decimals: number
  explanation_pt: string
  value: number | null
  ts_utc: string | null
  age_s: number | null
  source: string | null
  reason_pt: string | null
  quality: QualityCode
  quality_pt: string
  is_usable: boolean
}

export interface LiveView {
  equipment_id: string
  name: string
  data_source: 'SIMULATED' | 'EQUIPMENT'
  connection: string
  connection_pt: string
  is_stale: boolean
  stale_for_s: number | null
  last_read_utc: string | null
  last_ok_utc: string | null
  generated_at_utc: string
  tags: LiveTag[]
}

export interface ScenarioView {
  code: string
  title_pt: string
  description_pt: string
}

export interface SimulatorControls {
  equipment_id: string
  scenario: string
  time_scale: number
  seed: number
  overrides: Record<string, number>
  scenario_started_mono_ns: number | null
}

export interface SimulatorView {
  equipment_id: string
  controls: SimulatorControls
  scenarios: ScenarioView[]
  sliders: string[]
  note_pt: string
}

export interface ReferenceValues {
  setpoint_ref?: number
  belt_load_ref?: number
  rpm_ref?: number
}

export interface EquipmentView {
  profile: {
    id: string
    name: string
    is_example: boolean
    reference_values: ReferenceValues | null
    communication: { driver: string; [k: string]: unknown }
    [k: string]: unknown
  }
  mapping: Record<string, unknown>
}

/** Erro já no formato do envelope da API ({error:{code,message_pt}}). */
export class ApiFailure extends Error {
  constructor(
    public status: number,
    public code: string,
    public messagePt: string,
  ) {
    super(messagePt)
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`/api/v1${path}`, {
      ...init,
      headers: { Accept: 'application/json', ...(init?.body ? { 'Content-Type': 'application/json' } : {}), ...(init?.headers ?? {}) },
    })
  } catch {
    throw new ApiFailure(0, 'EDGE_OFFLINE', 'Sem resposta do Edge local.')
  }
  if (!res.ok) {
    let code = `HTTP_${res.status}`
    let message = 'Falha na requisição.'
    try {
      const body = (await res.json()) as { error?: { code?: string; message_pt?: string } }
      code = body.error?.code ?? code
      message = body.error?.message_pt ?? message
    } catch {
      /* corpo não-JSON: mantém o genérico */
    }
    throw new ApiFailure(res.status, code, message)
  }
  return (await res.json()) as T
}

export const simulatorApi = {
  live: (id: string) => call<LiveView>(`/equipments/${encodeURIComponent(id)}/live`),
  equipment: (id: string) => call<EquipmentView>(`/equipments/${encodeURIComponent(id)}`),
  get: (id: string) => call<SimulatorView>(`/simulator/${encodeURIComponent(id)}`),
  setScenario: (id: string, scenario: string) =>
    call<SimulatorView>(`/simulator/${encodeURIComponent(id)}/scenario`, {
      method: 'POST',
      body: JSON.stringify({ scenario }),
    }),
  setControls: (id: string, overrides: Record<string, number>) =>
    call<SimulatorView>(`/simulator/${encodeURIComponent(id)}/controls`, {
      method: 'POST',
      body: JSON.stringify({ overrides }),
    }),
  clearControls: (id: string) =>
    call<SimulatorView>(`/simulator/${encodeURIComponent(id)}/controls`, { method: 'DELETE' }),
}

/** Lê /app/eq/{id}/simulator da URL atual. Fallback quando a página não recebe `equipmentId`. */
export function equipmentIdFromUrl(pathname: string = location.pathname): string | null {
  const m = /\/app\/eq\/([^/]+)\//.exec(pathname)
  return m ? decodeURIComponent(m[1]) : null
}

/** Número pt-BR (vírgula decimal) com as casas da tag. */
export function formatValue(value: number | null, decimals: number): string {
  if (value == null || !Number.isFinite(value)) return '—'
  return new Intl.NumberFormat('pt-BR', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value)
}

/** Idade relativa curta: "há 12 s", "há 3 min". */
export function formatAge(ageS: number | null): string {
  if (ageS == null || !Number.isFinite(ageS)) return ''
  if (ageS < 60) return `há ${Math.round(ageS)} s`
  if (ageS < 3600) return `há ${Math.round(ageS / 60)} min`
  return `há ${Math.round(ageS / 3600)} h`
}

export function tagMap(live: LiveView | null): Record<string, LiveTag> {
  const out: Record<string, LiveTag> = {}
  for (const t of live?.tags ?? []) out[t.tag] = t
  return out
}
