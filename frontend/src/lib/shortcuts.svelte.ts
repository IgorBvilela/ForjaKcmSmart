/** Atalhos de teclado de 1 a 4 para as entradas do menu principal. Podem ser desligados na
 *  página Mais (WCAG 2.2, critério 2.1.4), com a escolha guardada no navegador, e não agem
 *  enquanto se digita num campo. */

const LS_KEY = 'forja.atalhos'
const KEYS = ['1', '2', '3', '4']
/** Campos em que tecla de número não é digitação (marcar, escolher, deslizar). */
const NOT_TYPING = new Set(['checkbox', 'radio', 'button', 'submit', 'reset', 'range', 'color', 'file'])

function read(): boolean {
  try {
    return localStorage.getItem(LS_KEY) !== 'off'
  } catch {
    return true
  }
}

class Shortcuts {
  enabled = $state(read())

  set(on: boolean): void {
    this.enabled = on
    try {
      localStorage.setItem(LS_KEY, on ? 'on' : 'off')
    } catch {
      // armazenamento indisponível: vale só nesta aba
    }
  }
}

export const shortcuts = new Shortcuts()

/** O foco está num lugar onde a tecla é texto (campo, área de texto, lista, texto editável). */
export function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable) return true
  if (target instanceof HTMLInputElement) return !NOT_TYPING.has(target.type)
  return target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement
}

/** Liga o atalho: `go(i)` abre a entrada i (0 a 3) do menu principal. Devolve o desligador. */
export function installShortcuts(go: (index: number) => void): () => void {
  const onKey = (e: KeyboardEvent) => {
    if (!shortcuts.enabled || e.repeat || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return
    if (isTyping(e.target)) return
    const index = KEYS.indexOf(e.key)
    if (index < 0) return
    e.preventDefault()
    go(index)
  }
  window.addEventListener('keydown', onKey)
  return () => window.removeEventListener('keydown', onKey)
}
