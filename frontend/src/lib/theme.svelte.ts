/** Tema da interface: segue o tema do Windows (padrão) ou fica fixo em escuro ou claro, com a
 *  escolha guardada neste navegador (página Mais, seção Aparência). `public/tema-inicial.js`
 *  aplica a mesma regra antes da primeira pintura; aqui o tema acompanha a troca do Windows, a
 *  escolha feita em outra aba e a escolha da página Mais. A impressão é sempre clara (tokens). */

import { flushSync } from 'svelte'

export type ThemeChoice = 'system' | 'dark' | 'light'
export type Theme = 'dark' | 'light'

const LS_KEY = 'forja.tema'
const LIGHT_QUERY = '(prefers-color-scheme: light)'
/** Cor da barra do navegador: a do cabeçalho do app em cada tema. */
const THEME_COLOR: Record<Theme, string> = { dark: '#1F1F1F', light: '#FFFFFF' }

function readChoice(): ThemeChoice {
  try {
    const v = localStorage.getItem(LS_KEY)
    return v === 'dark' || v === 'light' ? v : 'system'
  } catch {
    return 'system'
  }
}

function systemTheme(): Theme {
  return typeof matchMedia !== 'undefined' && matchMedia(LIGHT_QUERY).matches ? 'light' : 'dark'
}

function apply(t: Theme): void {
  document.documentElement.dataset.theme = t
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', THEME_COLOR[t])
}

type WithTransition = Document & {
  startViewTransition?: (update: () => void) => { finished: Promise<void> }
}

/** O tema novo nasce num círculo a partir do controle tocado. Sem View Transitions ou com
 *  movimento reduzido, troca na hora. */
function reveal(update: () => void, origin?: Element | null): void {
  const doc = document as WithTransition
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches
  if (!doc.startViewTransition || reduced) {
    update()
    return
  }
  const w = window.innerWidth
  const h = window.innerHeight
  let x = w / 2
  let y = h / 2
  if (origin) {
    const r = origin.getBoundingClientRect()
    x = r.left + r.width / 2
    y = r.top + r.height / 2
  }
  const root = document.documentElement
  root.style.setProperty('--tema-x', `${Math.round(x)}px`)
  root.style.setProperty('--tema-y', `${Math.round(y)}px`)
  root.style.setProperty('--tema-r', `${Math.ceil(Math.hypot(Math.max(x, w - x), Math.max(y, h - y)))}px`)
  root.classList.add('tema-troca')
  const transition = doc.startViewTransition(() => flushSync(update))
  void transition.finished.finally(() => root.classList.remove('tema-troca'))
}

class ThemeState {
  choice = $state<ThemeChoice>(readChoice())
  system = $state<Theme>(systemTheme())
  current = $derived<Theme>(this.choice === 'system' ? this.system : this.choice)

  /** Guarda a escolha neste navegador e aplica; `origin` é o controle tocado (para o círculo). */
  set(choice: ThemeChoice, origin?: Element | null): void {
    try {
      if (choice === 'system') localStorage.removeItem(LS_KEY)
      else localStorage.setItem(LS_KEY, choice)
    } catch {
      // armazenamento indisponível: vale só nesta aba
    }
    const next: Theme = choice === 'system' ? this.system : choice
    const update = () => {
      this.choice = choice
      apply(next)
    }
    if (next === this.current) update()
    else reveal(update, origin)
  }
}

export const theme = new ThemeState()

/** Aplica o tema e o mantém em dia com o Windows e com as outras abas. Devolve o desligador. */
export function installTheme(): () => void {
  apply(theme.current)
  const mq = matchMedia(LIGHT_QUERY)
  const onSystem = () => {
    theme.system = mq.matches ? 'light' : 'dark'
    apply(theme.current)
  }
  const onStorage = (e: StorageEvent) => {
    if (e.key !== LS_KEY && e.key !== null) return
    theme.choice = readChoice()
    apply(theme.current)
  }
  mq.addEventListener('change', onSystem)
  window.addEventListener('storage', onStorage)
  return () => {
    mq.removeEventListener('change', onSystem)
    window.removeEventListener('storage', onStorage)
  }
}
