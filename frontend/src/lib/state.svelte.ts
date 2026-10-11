/** Estado do shell: rota atual, equipamento selecionado, drawer, viewport, relógio. */
import { navigate, normalizePath, onNavigate, parseRoute, type Route } from './router'

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
  path = $state('/app/now')
  route: Route = $derived(parseRoute(this.path))
  lastEquipmentId = $state<string | null>(readStorage(LS_EQ))
  /** Equipamento da rota, ou o último visitado (para montar links da sidebar). */
  equipmentId: string | null = $derived(
    this.route.name === 'eq' ? this.route.id : this.lastEquipmentId,
  )

  /** < 768 px: celular. Selo Somente leitura migra para a faixa. */
  isMobile = $state(false)
  /** < 1024 px: o menu vira drawer com scrim. */
  isNarrow = $state(false)
  /** ≥ 1280 px: dashboard em 12 colunas, 6 indicadores numa linha, tiles compactos. */
  isDesktop = $state(false)
  /** Sem hover (toque). */
  noHover = $state(false)
  reducedMotion = $state(false)

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
    this.#watch('(min-width: 1280px)', (m) => (this.isDesktop = m))
    this.#watch('(hover: none)', (m) => (this.noHover = m))
    this.#watch('(prefers-reduced-motion: reduce)', (m) => (this.reducedMotion = m))

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

  /** Abre e fecha o menu no celular e no tablet; no desktop o trilho está sempre à vista. */
  toggleDrawer(): void {
    if (this.isNarrow) this.drawerOpen = !this.drawerOpen
  }

  closeDrawer(): void {
    this.drawerOpen = false
  }
}

export const app = new AppState()
