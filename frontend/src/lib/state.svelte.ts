/** Estado do shell: rota atual, equipamento selecionado, sidebar/drawer, viewport, relógio. */
import { navigate, normalizePath, onNavigate, parseRoute, type Route } from './router'

const LS_SIDEBAR = 'forja.sidebar'
const LS_EQ = 'forja.equipment'

function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function writeStorage(key: string, value: string | null): void {
  try {
    if (value == null) localStorage.removeItem(key)
    else localStorage.setItem(key, value)
  } catch {
    // armazenamento indisponível: estado só em memória
  }
}

function media(query: string): MediaQueryList | null {
  return typeof matchMedia === 'function' ? matchMedia(query) : null
}

class AppState {
  path = $state('/app/plant')
  route: Route = $derived(parseRoute(this.path))
  lastEquipmentId = $state<string | null>(readStorage(LS_EQ))
  /** Equipamento da rota, ou o último visitado (para montar links da sidebar). */
  equipmentId: string | null = $derived(
    this.route.name === 'eq' ? this.route.id : this.lastEquipmentId,
  )

  /** < 768 px: celular. Selo Somente leitura migra para a faixa. */
  isMobile = $state(false)
  /** < 1024 px: sidebar vira drawer com scrim. */
  isNarrow = $state(false)
  /** < 1440 px (inclui 1366×768): sidebar recolhida por padrão; 1920 abre. */
  isCompact = $state(false)
  reducedMotion = $state(false)

  sidebarCollapsed = $state(false)
  drawerOpen = $state(false)

  /** Relógio reativo (1 Hz). Lido por quem mostra idade ou hora. */
  now = $state(Date.now())

  #ticker: number | undefined
  #cleanups: Array<() => void> = []
  #started = false

  start(): void {
    if (this.#started) return
    this.#started = true

    const fixed = normalizePath(location.pathname)
    if (fixed) history.replaceState(null, '', fixed)
    this.#setPath(location.pathname)
    this.#cleanups.push(onNavigate((p) => this.#setPath(p)))

    this.#watch('(max-width: 767px)', (m) => (this.isMobile = m))
    this.#watch('(max-width: 1023px)', (m) => {
      this.isNarrow = m
      if (!m) this.drawerOpen = false
    })
    this.#watch('(max-width: 1439px)', (m) => (this.isCompact = m))
    this.#watch('(prefers-reduced-motion: reduce)', (m) => (this.reducedMotion = m))

    const stored = readStorage(LS_SIDEBAR)
    this.sidebarCollapsed = stored == null ? this.isCompact : stored === 'collapsed'

    this.#ticker = window.setInterval(() => (this.now = Date.now()), 1000)
  }

  stop(): void {
    for (const c of this.#cleanups) c()
    this.#cleanups = []
    if (this.#ticker) clearInterval(this.#ticker)
    this.#started = false
  }

  #watch(query: string, apply: (matches: boolean) => void): void {
    const mq = media(query)
    if (!mq) return
    apply(mq.matches)
    const handler = (e: MediaQueryListEvent) => apply(e.matches)
    mq.addEventListener('change', handler)
    this.#cleanups.push(() => mq.removeEventListener('change', handler))
  }

  #setPath(pathname: string): void {
    this.path = pathname
    const r = parseRoute(pathname)
    if (r.name === 'eq' && r.id !== this.lastEquipmentId) {
      this.lastEquipmentId = r.id
      writeStorage(LS_EQ, r.id)
    }
    this.drawerOpen = false
  }

  go(path: string, opts: { replace?: boolean } = {}): void {
    navigate(path, opts)
  }

  toggleSidebar(): void {
    if (this.isNarrow) {
      this.drawerOpen = !this.drawerOpen
      return
    }
    this.sidebarCollapsed = !this.sidebarCollapsed
    writeStorage(LS_SIDEBAR, this.sidebarCollapsed ? 'collapsed' : 'open')
  }

  closeDrawer(): void {
    this.drawerOpen = false
  }
}

export const app = new AppState()
