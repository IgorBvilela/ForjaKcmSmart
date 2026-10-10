/** Central de Comunicação: tipos e chamadas (rotas em src/forja/api/routers/communication.py).
 *  Nada aqui manda comando ao KCM: teste só lê; coleta liga a LEITURA periódica da Forja. */
import { API_BASE, ApiError, type DriverInfo, type EquipmentProfile, type Quality } from './api'

export type DriverName = 'simulator' | 'modbus_tcp' | 'ethernet_ip' | 'UNKNOWN'
export type DataTypeName =
  | 'int8'
  | 'uint8'
  | 'int16'
  | 'uint16'
  | 'int32'
  | 'uint32'
  | 'float32'
  | 'float64'
  | 'bool'
  | 'bitfield16'
  | 'bitfield32'
  | 'string'
export type EndiannessName = 'big' | 'little' | 'big_word_swap' | 'little_word_swap'

export interface Validation {
  validated_at_utc: string
  validated_by: string
  forja_value: number | string
  kcm_value: number | string
  matched: boolean
  note_pt: string
}

export interface MappingEntryDto {
  semantic_tag: string
  protocol_address: string | Record<string, unknown>
  datatype: DataTypeName | 'UNKNOWN'
  endianness: EndiannessName | 'UNKNOWN'
  scale: { factor: number; offset: number } | 'UNKNOWN'
  unit: string | null
  confirmed: boolean
  source: string
  evidence: string
  validation: Validation | null
  valid_min: number | null
  valid_max: number | null
  notes_pt: string
}

export interface MappingDto {
  schema_version: number
  mapping_id: string
  version: number
  equipment_id: string
  driver: string
  source: string
  confirmed_by: string | null
  entries: MappingEntryDto[]
  notes_pt: string
}

export interface CommState {
  code:
    | 'NOT_CONFIGURED'
    | 'PROTOCOL_UNKNOWN'
    | 'UNSUPPORTED'
    | 'NEEDS_CONFIGURATION'
    | 'SIMULATED'
    | 'DRIVER_AVAILABLE'
    | 'EXPERIMENTAL'
    | 'READ_TEST_OK'
    | 'READ_TEST_FAILED'
    | 'COMM_ERROR'
    | 'COLLECTING'
  label_pt: string
  tone: 'ok' | 'warn' | 'crit' | 'info' | 'unknown' | 'sim'
}

export interface ReadTestRecord {
  id: number
  equipment_id: string
  ts_utc: string
  driver: string
  final_stage: string
  success: boolean
  latency_ms: number | null
  fingerprint: string
  user: string
}

export interface CommView {
  equipment_id: string
  name: string
  is_example: boolean
  profile: EquipmentProfile
  config_hash: string
  mapping: MappingDto
  mapping_shared: boolean
  editable_mapping: MappingDto
  editable_mapping_exists: boolean
  fingerprint: string
  drivers: Record<string, DriverInfo>
  state: CommState
  collection: { enabled: boolean; label_pt: string }
  runtime: {
    connection: string
    connection_pt: string
    detail_pt: string
    latency_ms: number | null
    consecutive_errors: number
    last_ok_utc: string | null
  }
  last_test: ReadTestRecord | null
  last_test_matches: boolean
  read_only: true
  collection_paused_by_change?: boolean
}

export interface ValidationResult {
  ok: boolean
  errors: string[]
  warnings: string[]
  blocks: Array<{ block_id: string; area: string; address: number | string; count: number; tags: string[] }>
  requests_per_cycle: number
  fingerprint: string
}

export interface ReadTestTagRow {
  tag: string
  label_pt: string
  unit: string
  address_pt: string
  block_id: string | null
  datatype: string
  endianness_pt: string
  raw_hex: string | null
  value: number | null
  value_pt: string | null
  quality: Quality | null
  quality_pt: string | null
  reason_pt: string | null
  confirmed: boolean
}

export interface ReadTestResult {
  stages: Array<[string, string, string]>
  final: string
  final_pt: string | null
  success: boolean
  latency_ms: number | null
  error_pt: string | null
  warnings: string[]
  fingerprint: string
  test_id?: number
  detail: {
    tags: ReadTestTagRow[]
    blocks: ValidationResult['blocks']
  }
}

export interface CommLogEntry {
  ts_utc: string
  equipment_id: string
  level: string
  kind: string
  message_pt: string
  detail: Record<string, unknown>
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

export const commApi = {
  view: (id: string) => call<CommView>(`/communication/${enc(id)}`),
  validate: (id: string, communication: EquipmentProfile['communication'], mapping: MappingDto) =>
    call<ValidationResult>(`/communication/${enc(id)}/validate`, {
      method: 'POST',
      body: JSON.stringify({ communication, mapping }),
    }),
  testRead: (profile: EquipmentProfile, mapping: MappingDto, user: string) =>
    call<ReadTestResult>('/communication/test-read', {
      method: 'POST',
      body: JSON.stringify({ profile, mapping, user }),
    }),
  saveMapping: (id: string, mapping: MappingDto, baseVersion: number | null, user: string, reason: string) =>
    call<CommView>(`/communication/${enc(id)}/mapping`, {
      method: 'POST',
      body: JSON.stringify({ mapping, base_version: baseVersion, user, reason_pt: reason }),
    }),
  saveConfig: (
    id: string,
    body: {
      communication: EquipmentProfile['communication']
      host_interface?: EquipmentProfile['host_interface']
      controller?: EquipmentProfile['controller']
      mapping_profile?: string
      base_hash: string
      user: string
      reason_pt: string
    },
  ) => call<CommView>(`/communication/${enc(id)}/config`, { method: 'POST', body: JSON.stringify(body) }),
  setCollection: (id: string, active: boolean, user: string, reason: string) =>
    call<CommView>(`/communication/${enc(id)}/collection`, {
      method: 'POST',
      body: JSON.stringify({ active, user, reason_pt: reason }),
    }),
  readTests: (id: string) => call<{ tests: ReadTestRecord[] }>(`/communication/${enc(id)}/read-tests`),
  log: (id: string, limit = 100) =>
    call<{ entries: CommLogEntry[] }>(`/communication/${enc(id)}/log?limit=${limit}`),
}

/** Rótulos dos campos técnicos (o código fica no title; o texto é o que a manutenção lê). */
export const DATATYPE_PT: Record<DataTypeName, string> = {
  int8: 'Inteiro 8 bits (com sinal)',
  uint8: 'Inteiro 8 bits (sem sinal)',
  int16: 'Inteiro 16 bits (com sinal)',
  uint16: 'Inteiro 16 bits (sem sinal)',
  int32: 'Inteiro 32 bits (com sinal)',
  uint32: 'Inteiro 32 bits (sem sinal)',
  float32: 'Real 32 bits (float)',
  float64: 'Real 64 bits (double)',
  bool: 'Liga/desliga (bool)',
  bitfield16: 'Palavra de status 16 bits',
  bitfield32: 'Palavra de status 32 bits',
  string: 'Texto',
}

export const ENDIANNESS_PT: Record<EndiannessName, string> = {
  big: 'ABCD (big-endian)',
  little: 'DCBA (little-endian)',
  big_word_swap: 'CDAB (palavras trocadas)',
  little_word_swap: 'BADC (bytes trocados)',
}

export const MODBUS_AREAS: Array<{ value: string; label: string }> = [
  { value: 'holding', label: 'Holding register (03)' },
  { value: 'input', label: 'Input register (04)' },
  { value: 'coil', label: 'Coil (01)' },
  { value: 'discrete', label: 'Discrete input (02)' },
]

/** Porta padrão do PROTOCOLO (norma), oferecida como sugestão; nunca preenchida sozinha. */
export const PROTOCOL_DEFAULT_PORT: Partial<Record<DriverName, number>> = {
  modbus_tcp: 502,
  ethernet_ip: 44818,
}

export function isRealDriver(d: string): d is 'modbus_tcp' | 'ethernet_ip' {
  return d === 'modbus_tcp' || d === 'ethernet_ip'
}

export function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}
