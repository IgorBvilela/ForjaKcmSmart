/** Planta: o título vem do caminho de exibição dos perfis ("GTEX — PHA — Dosador" → "GTEX — PHA"). */
import type { PlantCard } from './api'

export function plantTitle(cards: readonly PlantCard[], fallback = 'Planta'): string {
  const prefixes = new Set<string>()
  for (const c of cards) {
    const suffix = ` — ${c.name}`
    if (c.display_path.endsWith(suffix)) {
      const p = c.display_path.slice(0, -suffix.length)
      if (p) prefixes.add(p)
    }
  }
  return prefixes.size ? [...prefixes].join(' · ') : fallback
}
