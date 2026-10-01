import type { StateTone } from './api'

/** Item já traduzido da linha do tempo. Tom nunca é cobre (status não é ação). */
export interface TimelineItem {
  id: string
  ts_utc: string
  title: string
  text?: string | null
  tone: StateTone
  href?: string
  muted?: boolean
  meta?: string | null
}
