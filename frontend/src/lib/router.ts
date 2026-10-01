/** Roteador próprio sobre a History API. Rotas do contrato B, sob /app. */

export const APP_BASE = '/app'

export const EQ_SCREENS = [
  'dashboard',
  'realtime',
  'trends',
  'history',
  'alerts',
  'events',
  'diagnostics',
  'early-warning',
  'cases',
  'simulator',
  'kcm/alarms',
  'kcm/communication',
  'kcm/datasheet',
  'kcm/components',
] as const
export type EqScreen = (typeof EQ_SCREENS)[number]

export type KnowledgeSub = 'documents' | 'manuals' | 'cases'
export type ToolsSub = 'reports' | 'exports'
export type SystemSub = 'settings' | 'backup' | 'logs' | 'about'

export type Route =
  | { name: 'plant' }
  | { name: 'eq'; id: string; screen: EqScreen; eventId?: string }
  | { name: 'knowledge'; sub: KnowledgeSub }
  | { name: 'tools'; sub: ToolsSub }
  | { name: 'system'; sub: SystemSub }
  | { name: 'dev'; sub: string }
  | { name: 'notfound'; path: string }

const EQ_ID = /^[A-Z0-9][A-Z0-9_]{1,63}$/
const EVENT_ID = /^[A-Za-z0-9_-]{1,64}$/

function isEqScreen(s: string): s is EqScreen {
  return (EQ_SCREENS as readonly string[]).includes(s)
}

function oneOf<T extends string>(value: string | undefined, allowed: readonly T[]): T | null {
  return value != null && (allowed as readonly string[]).includes(value) ? (value as T) : null
}

/** Caminhos que devem virar /app/plant (raiz do servidor e raiz do app). */
export function normalizePath(pathname: string): string | null {
  const p = pathname.replace(/\/+$/, '')
  if (p === '' || p === APP_BASE || p === `${APP_BASE}/index.html`) return `${APP_BASE}/plant`
  return null
}

export function parseRoute(pathname: string): Route {
  const notFound: Route = { name: 'notfound', path: pathname }
  const p = pathname.replace(/\/+$/, '')
  if (p === '' || p === APP_BASE) return { name: 'plant' }
  if (!p.startsWith(`${APP_BASE}/`)) return notFound
  let segs: string[]
  try {
    segs = p.slice(APP_BASE.length + 1).split('/').map(decodeURIComponent)
  } catch {
    return notFound
  }
  switch (segs[0]) {
    case 'plant':
      return segs.length === 1 ? { name: 'plant' } : notFound
    case 'eq': {
      const id = segs[1]
      if (!id || !EQ_ID.test(id)) return notFound
      const rest = segs.slice(2)
      if (rest.length === 0) return { name: 'eq', id, screen: 'dashboard' }
      if (rest[0] === 'kcm' && rest.length === 2) {
        const screen = `kcm/${rest[1]}`
        return isEqScreen(screen) ? { name: 'eq', id, screen } : notFound
      }
      if (rest[0] === 'events' && rest.length === 2 && EVENT_ID.test(rest[1])) {
        return { name: 'eq', id, screen: 'events', eventId: rest[1] }
      }
      if (rest.length === 1 && isEqScreen(rest[0])) return { name: 'eq', id, screen: rest[0] }
      return notFound
    }
    case 'knowledge': {
      const sub = oneOf(segs[1], ['documents', 'manuals', 'cases'] as const)
      return sub && segs.length === 2 ? { name: 'knowledge', sub } : notFound
    }
    case 'tools': {
      const sub = oneOf(segs[1], ['reports', 'exports'] as const)
      return sub && segs.length === 2 ? { name: 'tools', sub } : notFound
    }
    case 'system': {
      const sub = oneOf(segs[1], ['settings', 'backup', 'logs', 'about'] as const)
      return sub && segs.length === 2 ? { name: 'system', sub } : notFound
    }
    case 'dev':
      return { name: 'dev', sub: segs.slice(1).join('/') }
    default:
      return notFound
  }
}

export const href = {
  plant: () => `${APP_BASE}/plant`,
  eq: (id: string, screen: EqScreen = 'dashboard') =>
    `${APP_BASE}/eq/${encodeURIComponent(id)}/${screen}`,
  event: (id: string, eventId: string) =>
    `${APP_BASE}/eq/${encodeURIComponent(id)}/events/${encodeURIComponent(eventId)}`,
  knowledge: (sub: KnowledgeSub) => `${APP_BASE}/knowledge/${sub}`,
  tools: (sub: ToolsSub) => `${APP_BASE}/tools/${sub}`,
  system: (sub: SystemSub) => `${APP_BASE}/system/${sub}`,
}

/** Slug estável usado em `sidebar-link-<rota>` e no título do documento. */
export function routeSlug(route: Route): string {
  switch (route.name) {
    case 'plant':
      return 'plant'
    case 'eq':
      return route.screen.replace('/', '-')
    case 'knowledge':
      return `knowledge-${route.sub}`
    case 'tools':
      return `tools-${route.sub}`
    case 'system':
      return `system-${route.sub}`
    case 'dev':
      return `dev-${route.sub.replace('/', '-')}`
    default:
      return 'notfound'
  }
}

const NAV_EVENT = 'forja:navigate'

export function navigate(path: string, opts: { replace?: boolean } = {}): void {
  const current = location.pathname + location.search
  if (path !== current) {
    if (opts.replace) history.replaceState(null, '', path)
    else history.pushState(null, '', path)
  }
  window.dispatchEvent(new CustomEvent(NAV_EVENT))
}

export function onNavigate(cb: (pathname: string) => void): () => void {
  const handler = () => cb(location.pathname)
  window.addEventListener('popstate', handler)
  window.addEventListener(NAV_EVENT, handler)
  return () => {
    window.removeEventListener('popstate', handler)
    window.removeEventListener(NAV_EVENT, handler)
  }
}

/** Links internos (`/app/...`) navegam sem recarregar. Arquivos servidos (licenças) seguem normais. */
export function installLinkInterceptor(root: HTMLElement): () => void {
  const handler = (e: MouseEvent) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) {
      return
    }
    const target = e.target as Element | null
    const anchor = target?.closest('a[href]') as HTMLAnchorElement | null
    if (!anchor || anchor.target === '_blank' || anchor.hasAttribute('download')) return
    const url = new URL(anchor.href, location.href)
    if (url.origin !== location.origin) return
    if (!url.pathname.startsWith(`${APP_BASE}/`)) return
    if (/\.[a-z0-9]{2,5}$/i.test(url.pathname)) return
    e.preventDefault()
    navigate(url.pathname + url.search)
  }
  root.addEventListener('click', handler)
  return () => root.removeEventListener('click', handler)
}
