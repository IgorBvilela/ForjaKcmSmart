/** Cadastro de equipamentos e ficha técnica (src/forja/api/routers/equipment_admin.py). */
import { request, type EquipmentProfile } from './api'

const enc = encodeURIComponent

export type KnowledgeState =
  | 'FACT'
  | 'OFFICIAL_DOC'
  | 'MACHINE_DOC'
  | 'FIELD_CONFIRMED'
  | 'FIELD_OBSERVED'
  | 'FORJA_RULE'
  | 'TECHNICAL_OPINION'
  | 'HYPOTHESIS'
  | 'UNKNOWN'

export const KNOWLEDGE_PT: Record<KnowledgeState, string> = {
  FACT: 'Fato',
  OFFICIAL_DOC: 'Documento oficial',
  MACHINE_DOC: 'Documento da máquina',
  FIELD_CONFIRMED: 'Confirmado em campo',
  FIELD_OBSERVED: 'Observado em campo',
  FORJA_RULE: 'Regra Forja',
  TECHNICAL_OPINION: 'Opinião técnica',
  HYPOTHESIS: 'Hipótese',
  UNKNOWN: 'Desconhecido',
}

/** Ordem do mais forte para o mais fraco, para os seletores. */
export const KNOWLEDGE_ORDER: KnowledgeState[] = [
  'FACT',
  'OFFICIAL_DOC',
  'MACHINE_DOC',
  'FIELD_CONFIRMED',
  'FIELD_OBSERVED',
  'TECHNICAL_OPINION',
  'HYPOTHESIS',
  'UNKNOWN',
]

export type ComponentType = 'KCM' | 'MDU' | 'Scale' | 'SFT' | 'Encoder' | 'SIB' | 'Motor' | 'Anybus' | 'Other'

export const COMPONENT_PT: Record<ComponentType, string> = {
  KCM: 'Controlador KCM',
  MDU: 'MDU (acionamento)',
  Scale: 'Balança',
  SFT: 'Célula de pesagem (SFT)',
  Encoder: 'Encoder',
  SIB: 'SIB',
  Motor: 'Motor',
  Anybus: 'Interface Anybus',
  Other: 'Outro',
}

export interface Identity {
  name: string
  plant: string
  area: string
  line: string
  application: 'WBF' | 'LWF' | 'UNKNOWN'
  application_evidence: KnowledgeState
  notes_pt: string
}

export interface ControllerInfo {
  manufacturer: string
  model: string
  software_version: string
  kgr: string
  host_file: string
}

export interface HostInterface {
  type: string
  slot: string
  model: string
  part_number: string
  mac: string
  evidence: KnowledgeState
}

export interface Component {
  type: ComponentType
  model: string
  serial: string
  quantity: number | null
  evidence: KnowledgeState
  note_pt: string
}

export interface Datasheet {
  identity: Identity
  controller: ControllerInfo
  host_interface: HostInterface
  components: Component[]
}

export interface EquipmentAdminView {
  equipment_id: string
  profile: EquipmentProfile
  config_hash: string
  datasheet: Datasheet
  unknown_fields: string[]
  mapping: { mapping_id: string; driver: string; entries: number; readable: number }
  is_simulated: boolean
  is_example: boolean
}

export interface ArchivedEquipment {
  equipment_id: string
  name: string
  display_path: string
  archive_file: string
  is_example: boolean
}

export interface AlarmEntry {
  key: { manufacturer: string; controller: string; application: string; software_version: string; code: string }
  text: string
  title_pt: string
  meaning_pt: string
  evidence: string
  evidence_pt: string
  source: string
  note_pt: string
}

export interface AlarmCatalogView {
  equipment_id: string
  key: { manufacturer: string; controller: string; application: string; software_version: string }
  key_unknown: string[]
  alarms: AlarmEntry[]
  other_keys: AlarmEntry[]
  note_pt: string
}

export const equipmentApi = {
  datasheet: (id: string) => request<EquipmentAdminView>(`/equipments/${enc(id)}/datasheet`),
  saveDatasheet: (id: string, sheet: Datasheet, baseHash: string, user: string, reason: string) =>
    request<EquipmentAdminView>(`/equipments/${enc(id)}/datasheet`, {
      method: 'POST',
      body: JSON.stringify({ ...sheet, base_hash: baseHash, user, reason_pt: reason }),
    }),
  create: (id: string, identity: Identity, user: string, reason: string) =>
    request<EquipmentAdminView>('/equipments', {
      method: 'POST',
      body: JSON.stringify({ id, identity, user, reason_pt: reason }),
    }),
  archive: (id: string, confirmId: string, user: string, reason: string) =>
    request<{ equipment_id: string; archived: boolean }>(`/equipments/${enc(id)}/archive`, {
      method: 'POST',
      body: JSON.stringify({ confirm_id: confirmId, user, reason_pt: reason }),
    }),
  archived: () => request<{ count: number; equipments: ArchivedEquipment[] }>('/archived-equipments'),
  restore: (id: string, user: string, reason: string) =>
    request<EquipmentAdminView>(`/archived-equipments/${enc(id)}/restore`, {
      method: 'POST',
      body: JSON.stringify({ user, reason_pt: reason }),
    }),
  alarmCatalog: (id: string) => request<AlarmCatalogView>(`/equipments/${enc(id)}/alarm-catalog`),
}

/** Rótulo em português de um campo da ficha (usado em "o que falta levantar"). */
export const FIELD_PT: Record<string, string> = {
  'identity.plant': 'Planta',
  'identity.area': 'Área',
  'identity.line': 'Linha',
  'identity.application': 'Aplicação (WBF ou LWF)',
  'controller.manufacturer': 'Fabricante do controlador',
  'controller.model': 'Modelo do controlador',
  'controller.software_version': 'Versão de software do KCM',
  'controller.kgr': 'KGR',
  'controller.host_file': 'Host File',
  'host_interface.type': 'Tipo da interface Host',
  'host_interface.slot': 'Slot da interface Host',
  'host_interface.model': 'Modelo da interface Host',
  'host_interface.part_number': 'Part number da interface Host',
  'host_interface.mac': 'MAC da interface Host',
}

/** Sugestão de id a partir da área e do nome: só A-Z, 0-9 e _. */
export function suggestId(area: string, name: string): string {
  const clean = (s: string) =>
    s
      .normalize('NFD')
      .replace(/[̀-ͯ]/g, '')
      .toUpperCase()
      .replace(/[^A-Z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '')
  const parts = [area && area !== 'UNKNOWN' ? clean(area) : '', clean(name)].filter(Boolean)
  return parts.join('_').slice(0, 64)
}

export const EQUIPMENT_ID = /^[A-Z0-9][A-Z0-9_]{1,63}$/

export function isUnknown(value: string | null | undefined): boolean {
  return value == null || value === '' || value === 'UNKNOWN'
}

export function shown(value: string | null | undefined): string {
  return isUnknown(value) ? 'Desconhecido' : String(value)
}

const RESPONSIBLE_KEY = 'forja.responsavel'

/** Responsável lembrado neste navegador (o mesmo da Comunicação e do Comissionamento). */
export function rememberedResponsible(): string {
  try {
    return localStorage.getItem(RESPONSIBLE_KEY) ?? ''
  } catch {
    return ''
  }
}

export function rememberResponsible(name: string): void {
  try {
    localStorage.setItem(RESPONSIBLE_KEY, name)
  } catch {
    // armazenamento indisponível: o nome só não fica lembrado
  }
}

/** Mesmo padrão do backend para o responsável. */
export const RESPONSIBLE_PATTERN = /^[\p{L}\p{N}_ .@-]{1,64}$/u
