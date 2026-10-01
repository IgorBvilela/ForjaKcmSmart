/** Formatação pt-BR: números com vírgula, idade relativa, duração, datas no fuso da máquina. */

const LOCALE = 'pt-BR'
const numberFormats = new Map<string, Intl.NumberFormat>()

function numberFormat(decimals: number, signed: boolean): Intl.NumberFormat {
  const key = `${decimals}:${signed ? 's' : 'n'}`
  let nf = numberFormats.get(key)
  if (!nf) {
    nf = new Intl.NumberFormat(LOCALE, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
      signDisplay: signed ? 'exceptZero' : 'auto',
    })
    numberFormats.set(key, nf)
  }
  return nf
}

/** Número pt-BR com casas fixas. Nulo, NaN e infinito viram travessão. */
export function fmtNumber(
  value: number | null | undefined,
  decimals = 1,
  opts: { signed?: boolean } = {},
): string {
  if (value == null || !Number.isFinite(value)) return '—'
  const d = Math.max(0, Math.min(6, Math.trunc(decimals)))
  return numberFormat(d, opts.signed ?? false).format(value)
}

/** Idade relativa curta: "agora" (< 2 s), "há 12 s", "há 3 min", "há 2 h", "há 3 d". */
export function fmtAge(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return 'sem leitura'
  const s = Math.max(0, Math.round(seconds))
  if (s < 2) return 'agora'
  if (s < 60) return `há ${s} s`
  const m = Math.floor(s / 60)
  if (m < 60) return `há ${m} min`
  const h = Math.floor(m / 60)
  if (h < 48) return `há ${h} h`
  return `há ${Math.floor(h / 24)} d`
}

/** Duração: "12 s", "3 min 20 s", "2 h 05 min", "3 d 4 h". */
export function fmtDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return '—'
  const s = Math.max(0, Math.round(seconds))
  if (s < 60) return `${s} s`
  const m = Math.floor(s / 60)
  const rs = s % 60
  if (m < 60) return rs ? `${m} min ${rs} s` : `${m} min`
  const h = Math.floor(m / 60)
  const rm = m % 60
  if (h < 24) return `${h} h ${String(rm).padStart(2, '0')} min`
  const d = Math.floor(h / 24)
  return `${d} d ${h % 24} h`
}

function toDate(iso: string | number | Date | null | undefined): Date | null {
  if (iso == null) return null
  const d = iso instanceof Date ? iso : new Date(iso)
  return Number.isNaN(d.getTime()) ? null : d
}

const timeWithSeconds = new Intl.DateTimeFormat(LOCALE, {
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
})
const timeShort = new Intl.DateTimeFormat(LOCALE, { hour: '2-digit', minute: '2-digit' })
const dateMedium = new Intl.DateTimeFormat(LOCALE, { day: 'numeric', month: 'short', year: 'numeric' })
const dateTimeMedium = new Intl.DateTimeFormat(LOCALE, {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

/** "14:32:18" (ou "14:32"). */
export function fmtTime(iso: string | number | Date | null | undefined, withSeconds = true): string {
  const d = toDate(iso)
  if (!d) return '—'
  return (withSeconds ? timeWithSeconds : timeShort).format(d)
}

/** Relógio do header: "14:32:18" ou "14:32". */
export function fmtClock(date: Date, withSeconds = true): string {
  return (withSeconds ? timeWithSeconds : timeShort).format(date)
}

/** "26 de abr. de 2026". */
export function fmtDate(iso: string | number | Date | null | undefined): string {
  const d = toDate(iso)
  return d ? dateMedium.format(d) : '—'
}

/** "26 de abr. de 2026, 14:32". */
export function fmtDateTime(iso: string | number | Date | null | undefined): string {
  const d = toDate(iso)
  return d ? dateTimeMedium.format(d) : '—'
}

/** Hoje mostra só a hora; outro dia mostra data e hora. */
export function fmtWhen(iso: string | null | undefined, nowMs: number): string {
  const d = toDate(iso)
  if (!d) return '—'
  const now = new Date(nowMs)
  const sameDay =
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  return sameDay ? timeWithSeconds.format(d) : dateTimeMedium.format(d)
}

/** Segundos desde um instante ISO até `nowMs`. */
export function ageSince(iso: string | null | undefined, nowMs: number): number | null {
  const d = toDate(iso)
  if (!d) return null
  return Math.max(0, (nowMs - d.getTime()) / 1000)
}

export type DeltaKind = 'pct' | 'points' | 'abs' | 'none'

export interface DeltaLike {
  delta: number | null
  delta_kind: DeltaKind
  unit?: string
}

/** Variação em português: "↓ 47,4 %", "↑ 35 pontos", "↑ 54 rpm"; sem variação vira "—". */
export function fmtDelta(item: DeltaLike): string {
  if (item.delta == null || !Number.isFinite(item.delta) || item.delta_kind === 'none') {
    return '—'
  }
  const abs = Math.abs(item.delta)
  // zero, ou tão perto de zero que o texto mostraria "0,0": não há variação a anunciar
  if (abs < (item.delta_kind === 'pct' || item.delta_kind === 'points' ? 0.05 : 0.005)) return '—'
  const arrow = item.delta > 0 ? '↑' : '↓'
  switch (item.delta_kind) {
    case 'pct':
      return `${arrow} ${fmtNumber(abs, 1)} %`
    case 'points':
      return `${arrow} ${fmtNumber(abs, abs < 10 ? 1 : 0)} pontos`
    case 'abs': {
      const decimals = abs >= 100 ? 0 : abs >= 10 ? 1 : 2
      return `${arrow} ${fmtNumber(abs, decimals)}${item.unit ? ` ${item.unit}` : ''}`
    }
  }
}

export function deltaDirection(delta: number | null | undefined): 'up' | 'down' | 'flat' {
  if (delta == null || !Number.isFinite(delta) || delta === 0) return 'flat'
  return delta > 0 ? 'up' : 'down'
}

/** Plural simples: "1 equipamento", "3 equipamentos". */
export function plural(n: number, singular: string, pluralForm: string): string {
  return `${fmtNumber(n, 0)} ${n === 1 ? singular : pluralForm}`
}
