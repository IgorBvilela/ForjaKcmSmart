/** Cliente SSE (/api/v1/stream) e estado ao vivo por equipamento.
 *
 * snapshot → planta + live de todos; sample → merge por tag (≤ 2 Hz por equipamento);
 * event → versão de eventos (páginas refazem a consulta); status → conexão; heartbeat → relógio.
 * Edge offline quando passam mais de 12 s sem heartbeat. STALE é decidido pelo servidor: a cada
 * reconciliação (/plant e /live) o que vier de lá prevalece. Nunca interpolamos buracos.
 */
import {
  api,
  QUALITY_PT,
  isUsable,
  type ConnectionState,
  type DataSource,
  type EventBrief,
  type EventView,
  type LiveView,
  type PlantCard,
  type Quality,
  type TagView,
} from './api'

export interface LiveTag extends TagView {
  /** Date.now() no momento em que o dado chegou; a idade mostrada = age_s + decorrido. */
  receivedAt: number
}

export interface LiveEquipment {
  equipment_id: string
  name: string
  data_source: 'SIMULATED' | 'EQUIPMENT'
  connection: ConnectionState
  connection_pt: string
  is_stale: boolean
  stale_for_s: number | null
  last_read_utc: string | null
  last_ok_utc: string | null
  tags: Record<string, LiveTag>
  receivedAt: number
}

export interface SeriesPoint {
  t: number
  v: number | null
  q: Quality
}

export type EdgeState = 'connecting' | 'online' | 'reconnecting' | 'offline'

export const SERIES_MAX = 60
const HEARTBEAT_TIMEOUT_MS = 12_000
const PLANT_RECONCILE_MS = 15_000

interface SnapshotPayload {
  ts_utc: string
  last_id: number
  plant: PlantCard[]
  live: Record<string, LiveView>
}

interface SamplePayload {
  equipment_id: string
  ts_utc: string
  quality: Quality
  quality_pt: string
  latency_ms: number | null
  tags: Record<string, { value: number | null; quality: Quality; ts_utc: string; reason_pt: string | null }>
}

interface StatusPayload {
  equipment_id: string | null
  change: unknown
  status: {
    connection: ConnectionState
    connection_pt: string
    is_stale: boolean
    stale_for_s: number | null
    last_read_utc: string | null
    last_ok_utc: string | null
  } | null
}

interface EventPayload {
  kind: 'OPEN' | 'UPDATE' | 'CLOSE' | 'EVENT' | 'DIAGNOSIS' | 'UNKNOWN'
  event?: EventView
  event_id?: string
  equipment_id?: string
  diagnosis_id?: string
}

function toLiveEquipment(view: LiveView, receivedAt: number): LiveEquipment {
  const tags: Record<string, LiveTag> = {}
  for (const t of view.tags) tags[t.tag] = { ...t, receivedAt }
  return {
    equipment_id: view.equipment_id,
    name: view.name,
    data_source: view.data_source,
    connection: view.connection,
    connection_pt: view.connection_pt,
    is_stale: view.is_stale,
    stale_for_s: view.stale_for_s,
    last_read_utc: view.last_read_utc,
    last_ok_utc: view.last_ok_utc,
    tags,
    receivedAt,
  }
}

function sourceOf(cards: PlantCard[]): DataSource | null {
  if (cards.length === 0) return null
  const sim = cards.some((c) => c.data_source === 'SIMULATED')
  const real = cards.some((c) => c.data_source === 'EQUIPMENT')
  if (sim && real) return 'MIXED'
  return real ? 'EQUIPMENT' : 'SIMULATED'
}

export const DATA_SOURCE_PT: Record<DataSource, string> = {
  SIMULATED: 'DADOS SIMULADOS',
  EQUIPMENT: 'DADOS DO EQUIPAMENTO',
  MIXED: 'DADOS MISTOS (simulados e do equipamento)',
}

class LiveStore {
  plant = $state<PlantCard[]>([])
  live = $state<Record<string, LiveEquipment>>({})
  series = $state<Record<string, Record<string, SeriesPoint[]>>>({})
  edge = $state<EdgeState>('connecting')
  lastHeartbeatAt = $state<number | null>(null)
  /** Incrementa a cada transição de evento; páginas observam e refazem a consulta. */
  eventsVersion = $state(0)
  /** Incrementa quando um diagnóstico é publicado. */
  diagnosisVersion = $state(0)
  lastEventChange = $state<{ kind: string; event: EventBrief; equipment_id: string } | null>(null)
  plantError = $state<string | null>(null)
  #explicitSource = $state<DataSource | null>(null)
  dataSource: DataSource | null = $derived(this.#explicitSource ?? sourceOf(this.plant))
  /** Equipamento para links sem seleção: o primeiro perfil real; só se não houver, um de exemplo. */
  defaultEquipmentId: string | null = $derived(
    this.plant.find((c) => !c.is_example)?.id ?? this.plant[0]?.id ?? null,
  )

  #es: EventSource | null = null
  #watchdog: number | undefined
  #reconcile: number | undefined
  #plantRefreshTimer: number | undefined
  #started = false

  start(): void {
    if (this.#started) return
    this.#started = true
    this.#open()
    this.#watchdog = window.setInterval(() => this.#checkHeartbeat(), 2000)
    this.#reconcile = window.setInterval(() => void this.refreshPlant(), PLANT_RECONCILE_MS)
    void this.refreshPlant()
  }

  stop(): void {
    this.#es?.close()
    this.#es = null
    if (this.#watchdog) clearInterval(this.#watchdog)
    if (this.#reconcile) clearInterval(this.#reconcile)
    if (this.#plantRefreshTimer) clearTimeout(this.#plantRefreshTimer)
    this.#started = false
  }

  #open(): void {
    const es = new EventSource('/api/v1/stream')
    this.#es = es
    es.addEventListener('snapshot', (e) => this.#onSnapshot(JSON.parse((e as MessageEvent).data)))
    es.addEventListener('sample', (e) => this.#onSample(JSON.parse((e as MessageEvent).data)))
    es.addEventListener('status', (e) => this.#onStatus(JSON.parse((e as MessageEvent).data)))
    es.addEventListener('event', (e) => this.#onEvent(JSON.parse((e as MessageEvent).data)))
    es.addEventListener('heartbeat', () => this.#onHeartbeat())
    es.onerror = () => {
      // EventSource reconecta sozinho; até lá o estado é "reconectando". Offline vem do watchdog.
      if (this.edge === 'online') this.edge = 'reconnecting'
    }
  }

  #onSnapshot(s: SnapshotPayload): void {
    const now = Date.now()
    this.plant = s.plant
    const next: Record<string, LiveEquipment> = {}
    for (const [id, view] of Object.entries(s.live)) {
      next[id] = toLiveEquipment(view, now)
      for (const t of view.tags) {
        if (t.ts_utc) this.#push(id, t.tag, { t: Date.parse(t.ts_utc), v: t.value, q: t.quality })
      }
    }
    this.live = next
    this.edge = 'online'
    this.lastHeartbeatAt = now
  }

  #onSample(p: SamplePayload): void {
    const eq = this.live[p.equipment_id]
    if (!eq) return
    const now = Date.now()
    for (const [tag, s] of Object.entries(p.tags)) {
      const cur = eq.tags[tag]
      if (cur) {
        cur.value = s.value
        cur.quality = s.quality
        cur.quality_pt = QUALITY_PT[s.quality] ?? s.quality
        cur.is_usable = isUsable(s.quality)
        cur.ts_utc = s.ts_utc
        cur.reason_pt = s.reason_pt
        cur.age_s = 0
        cur.receivedAt = now
      } else {
        eq.tags[tag] = {
          tag,
          label_pt: tag,
          unit: '',
          kind: null,
          decimals: 1,
          explanation_pt: '',
          value: s.value,
          ts_utc: s.ts_utc,
          age_s: 0,
          source: '',
          reason_pt: s.reason_pt,
          raw_hex: null,
          quality: s.quality,
          quality_pt: QUALITY_PT[s.quality] ?? s.quality,
          is_usable: isUsable(s.quality),
          receivedAt: now,
        }
      }
      this.#push(p.equipment_id, tag, { t: Date.parse(s.ts_utc), v: s.value, q: s.quality })
    }
    eq.last_read_utc = p.ts_utc
    eq.receivedAt = now
    eq.is_stale = false
    if (isUsable(p.quality)) eq.last_ok_utc = p.ts_utc

    const card = this.plant.find((c) => c.id === p.equipment_id)
    if (card) {
      card.last_read_utc = p.ts_utc
      card.is_stale = false
      const mf = p.tags['mass_flow']
      if (mf && card.mass_flow) {
        card.mass_flow.value = mf.value
        card.mass_flow.quality = mf.quality
        card.mass_flow.quality_pt = QUALITY_PT[mf.quality] ?? mf.quality
        card.mass_flow.is_usable = isUsable(mf.quality)
        card.mass_flow.ts_utc = mf.ts_utc
        card.mass_flow.reason_pt = mf.reason_pt
        card.mass_flow.age_s = 0
      }
    }
  }

  #onStatus(p: StatusPayload): void {
    if (!p.equipment_id || !p.status) return
    const eq = this.live[p.equipment_id]
    if (eq) {
      eq.connection = p.status.connection
      eq.connection_pt = p.status.connection_pt
      eq.is_stale = p.status.is_stale
      eq.stale_for_s = p.status.stale_for_s
    }
    const card = this.plant.find((c) => c.id === p.equipment_id)
    if (card) {
      card.connection = p.status.connection
      card.connection_pt = p.status.connection_pt
      card.is_stale = p.status.is_stale
    }
    this.queuePlantRefresh()
  }

  #onEvent(p: EventPayload): void {
    if (p.kind === 'DIAGNOSIS') {
      this.diagnosisVersion += 1
    } else {
      this.eventsVersion += 1
      if (p.event) {
        this.lastEventChange = { kind: p.kind, event: p.event, equipment_id: p.event.equipment_id }
      }
    }
    this.queuePlantRefresh()
  }

  #onHeartbeat(): void {
    this.lastHeartbeatAt = Date.now()
    if (this.edge !== 'online') this.edge = 'online'
  }

  #checkHeartbeat(): void {
    if (this.lastHeartbeatAt == null) return
    if (Date.now() - this.lastHeartbeatAt > HEARTBEAT_TIMEOUT_MS) this.edge = 'offline'
  }

  #push(eq: string, tag: string, point: SeriesPoint): void {
    if (!Number.isFinite(point.t)) return
    const byTag = (this.series[eq] ??= {})
    const arr = (byTag[tag] ??= [])
    const last = arr[arr.length - 1]
    if (last && last.t === point.t) {
      last.v = point.v
      last.q = point.q
      return
    }
    arr.push(point)
    if (arr.length > SERIES_MAX) arr.splice(0, arr.length - SERIES_MAX)
  }

  /** Reconsulta /plant em até 400 ms (coalesce várias transições seguidas). */
  queuePlantRefresh(): void {
    if (this.#plantRefreshTimer) return
    this.#plantRefreshTimer = window.setTimeout(() => {
      this.#plantRefreshTimer = undefined
      void this.refreshPlant()
    }, 400)
  }

  async refreshPlant(): Promise<void> {
    try {
      const r = await api.plant()
      this.plant = r.cards
      this.#explicitSource = r.data_source
      this.plantError = null
    } catch (err) {
      this.plantError = err instanceof Error ? err.message : 'Falha ao consultar a planta.'
    }
  }

  /** Reconcilia o live de um equipamento com o servidor (STALE é decidido lá). */
  async reconcileLive(equipmentId: string): Promise<void> {
    try {
      const view = await api.live(equipmentId)
      this.live[equipmentId] = toLiveEquipment(view, Date.now())
    } catch {
      // sem resposta: o watchdog do heartbeat cuida do estado do Edge
    }
  }

  /** Semeia a mini-tendência com pontos do histórico (mantém os mais novos já recebidos).
   *
   *  O `/history` devolve bucket sem linha como GAP (`value: null`, COMM_ERROR). No rabo da janela
   *  isso costuma ser só atraso de gravação do historiador (amostras ainda em memória quando a
   *  página pediu o histórico), não falta de comunicação. O presente vem do stream: por isso os
   *  nulos do rabo e os nulos já cobertos por pontos ao vivo são descartados. Nenhum valor é
   *  inventado: um GAP real no meio da janela continua GAP. */
  seedSeries(equipmentId: string, tag: string, points: SeriesPoint[]): void {
    const byTag = (this.series[equipmentId] ??= {})
    const existing = byTag[tag] ?? []
    const liveStart = existing.length ? existing[0].t : Infinity
    const seeded = points.filter((p) => Number.isFinite(p.t) && !(p.v == null && p.t >= liveStart))
    let end = seeded.length
    while (end > 0 && seeded[end - 1].v == null) end -= 1
    const trimmed = seeded.slice(0, end)
    const newest = trimmed.length ? trimmed[trimmed.length - 1].t : -Infinity
    const merged = [...trimmed, ...existing.filter((p) => p.t > newest)]
    byTag[tag] = merged.slice(-SERIES_MAX)
  }

  seriesFor(equipmentId: string | null, tag: string): SeriesPoint[] {
    if (!equipmentId) return []
    return this.series[equipmentId]?.[tag] ?? []
  }

  tagOf(equipmentId: string | null, tag: string): LiveTag | undefined {
    if (!equipmentId) return undefined
    return this.live[equipmentId]?.tags[tag]
  }

  cardOf(equipmentId: string | null): PlantCard | undefined {
    if (!equipmentId) return undefined
    return this.plant.find((c) => c.id === equipmentId)
  }

  /** Idade em segundos no instante `nowMs` (passe `app.now` para ficar reativo). */
  ageOf(tag: { age_s: number | null; receivedAt?: number } | null | undefined, nowMs: number): number | null {
    if (!tag || tag.age_s == null) return null
    const since = tag.receivedAt ? Math.max(0, (nowMs - tag.receivedAt) / 1000) : 0
    return tag.age_s + since
  }
}

export const live = new LiveStore()
