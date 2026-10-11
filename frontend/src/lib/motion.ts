/** Microinterações de mudança de estado, só com Web Animations (transform e opacity).
 *  Nada acontece na primeira vez nem com movimento reduzido: o estado novo aparece direto. */

const EASE_OUT = 'cubic-bezier(0.2, 0, 0, 1)'

/** "Pop" do selo: entra de 0,6 com sobra de 1,15 e assenta em 1 (520 ms). */
const POP: Keyframe[] = [
  { transform: 'scale(0.6)', opacity: 0 },
  { transform: 'scale(1.15)', opacity: 1, offset: 0.55 },
  { transform: 'scale(0.96)', offset: 0.78 },
  { transform: 'scale(1)', opacity: 1 },
]

/** Brilho único do anel do cartão: acende e apaga (2,4 s). */
const FLASH: Keyframe[] = [{ opacity: 0 }, { opacity: 1, offset: 0.25 }, { opacity: 0 }]

function reducedMotion(): boolean {
  return typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches
}

function onChange(node: HTMLElement, value: unknown, play: (el: HTMLElement) => void) {
  let last = value
  return {
    update(next: unknown) {
      if (next !== last && !reducedMotion()) play(node)
      last = next
    },
  }
}

/** O elemento dá um "pop" quando `value` muda. */
export function popOnChange(node: HTMLElement, value: unknown) {
  return onChange(node, value, (el) => el.animate(POP, { duration: 520, easing: EASE_OUT }))
}

/** O elemento (um anel decorativo, opacidade 0 em repouso) acende uma vez quando `value` muda. */
export function flashOnChange(node: HTMLElement, value: unknown) {
  return onChange(node, value, (el) => el.animate(FLASH, { duration: 2400, easing: 'ease-in-out' }))
}
