/** Valores discretos em palavras (mesma convenção da tag semântica usada pelo backend em
 *  events/what_changed.py). Fora do mapa: número inteiro, nunca inventado. */
import { fmtNumber } from './format'

const MACHINE_STATE: Record<number, string> = { 0: 'Parado', 1: 'Em operação', 2: 'Em alarme' }
const YES_NO: Record<number, string> = { 0: 'não', 1: 'sim' }
const CONTROL_MODE: Record<number, string> = { 0: 'volumétrico', 1: 'gravimétrico' }

export function discreteText(tag: string, value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—'
  const code = Number.isInteger(value) ? value : null
  if (code != null) {
    if (tag === 'machine_state' && MACHINE_STATE[code]) return MACHINE_STATE[code]
    if (tag === 'alarm_active' && YES_NO[code]) return YES_NO[code]
    if (tag === 'control_mode' && CONTROL_MODE[code]) return CONTROL_MODE[code]
    if (tag === 'alarm_code') return code === 0 ? 'nenhum alarme' : `código ${code}`
    if (tag === 'stop_by') return code === 0 ? 'nenhum' : `código ${code}`
  }
  return fmtNumber(value, code != null ? 0 : 2)
}

/** Status bruto (SFT, MDU): hexadecimal como veio, sem decodificar sem fonte. */
export function rawStatusText(value: number | null | undefined, digits = 8): string {
  if (value == null || !Number.isFinite(value)) return '—'
  const n = Math.trunc(value)
  if (n < 0) return fmtNumber(value, 0)
  return `0x${n.toString(16).toUpperCase().padStart(digits, '0')}`
}
