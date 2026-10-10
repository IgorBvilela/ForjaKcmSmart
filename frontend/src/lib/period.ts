/** Período de consulta (Tendências e Histórico): atalhos relativos a agora ou intervalo fixo.
 *  O período mora na URL (`?p=1h` ou `?from=…&to=…`) para o link poder ser compartilhado. */

export type PresetId = '15m' | '1h' | '6h' | '24h' | '7d' | '30d'

export const PRESETS: ReadonlyArray<{ id: PresetId; label: string; seconds: number }> = [
  { id: '15m', label: '15 min', seconds: 15 * 60 },
  { id: '1h', label: '1 h', seconds: 3600 },
  { id: '6h', label: '6 h', seconds: 6 * 3600 },
  { id: '24h', label: '24 h', seconds: 24 * 3600 },
  { id: '7d', label: '7 dias', seconds: 7 * 86400 },
  { id: '30d', label: '30 dias', seconds: 30 * 86400 },
]

export type Period = { kind: 'preset'; preset: PresetId } | { kind: 'custom'; from: number; to: number }

export const DEFAULT_PERIOD: Period = { kind: 'preset', preset: '1h' }

export function isPreset(v: string | null): v is PresetId {
  return PRESETS.some((p) => p.id === v)
}

/** Intervalo [from, to] em ms. Atalho = termina agora. */
export function resolvePeriod(p: Period, nowMs: number): { from: number; to: number } {
  if (p.kind === 'custom') return { from: p.from, to: p.to }
  const preset = PRESETS.find((x) => x.id === p.preset) ?? PRESETS[1]
  return { from: nowMs - preset.seconds * 1000, to: nowMs }
}

/** Atalho termina agora: a tela atualiza sozinha. Intervalo fixo não muda. */
export function isLive(p: Period): boolean {
  return p.kind === 'preset'
}

function pad(n: number): string {
  return String(n).padStart(2, '0')
}

/** ms → valor de <input type="datetime-local"> no fuso do navegador (o da planta). */
export function toLocalInput(ms: number): string {
  const d = new Date(ms)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** Valor de <input type="datetime-local"> → ms; inválido vira null. */
export function fromLocalInput(value: string): number | null {
  if (!value) return null
  const ms = new Date(value).getTime()
  return Number.isFinite(ms) ? ms : null
}

/** Lê o período da query string. */
export function periodFromSearch(search: string): Period {
  const sp = new URLSearchParams(search)
  const p = sp.get('p')
  if (isPreset(p)) return { kind: 'preset', preset: p }
  const from = Number(sp.get('from'))
  const to = Number(sp.get('to'))
  if (Number.isFinite(from) && Number.isFinite(to) && from > 0 && to > from) {
    return { kind: 'custom', from, to }
  }
  return DEFAULT_PERIOD
}

export function tagsFromSearch(search: string): string[] | null {
  const raw = new URLSearchParams(search).get('tags')
  if (!raw) return null
  const tags = raw.split(',').map((t) => t.trim()).filter((t) => /^[a-z_]{2,40}$/.test(t))
  return tags.length ? Array.from(new Set(tags)) : null
}

/** Query string com período e variáveis. */
export function searchFor(p: Period, tags: string[]): string {
  const sp = new URLSearchParams()
  if (p.kind === 'preset') sp.set('p', p.preset)
  else {
    sp.set('from', String(Math.round(p.from)))
    sp.set('to', String(Math.round(p.to)))
  }
  if (tags.length) sp.set('tags', tags.join(','))
  return `?${sp.toString()}`
}

export function periodLabel(p: Period): string {
  if (p.kind === 'preset') return `Últimos ${PRESETS.find((x) => x.id === p.preset)?.label ?? ''}`
  return 'Intervalo escolhido'
}
