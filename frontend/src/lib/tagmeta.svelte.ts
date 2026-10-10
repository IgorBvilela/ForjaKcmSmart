/** Catálogo das variáveis (rótulo em português, unidade, casas). Carregado uma vez do backend. */
import { api, type TagMeta } from './api'

/** Ordem de leitura para a manutenção: processo primeiro, estado e alarmes depois, status brutos no fim. */
export const TAG_ORDER: readonly string[] = [
  'mass_flow',
  'setpoint',
  'drive_command',
  'belt_load',
  'rpm',
  'net_weight',
  'gross_weight',
  'vol_belt_load',
  'int_channel_pct',
  'motor_load_pct',
  'kcm_temp',
  'machine_state',
  'alarm_active',
  'alarm_code',
  'stop_by',
  'control_mode',
  'tare',
  'span',
  'cal_correlation',
  'sft_status',
  'sft_list',
  'mdu_status',
]

/** Seleção inicial das Tendências: o padrão "vazão × esforço × material × velocidade". */
export const DEFAULT_TREND_TAGS: readonly string[] = ['mass_flow', 'drive_command', 'belt_load', 'rpm']

export function sortTags(tags: string[]): string[] {
  const idx = (t: string) => {
    const i = TAG_ORDER.indexOf(t)
    return i < 0 ? TAG_ORDER.length : i
  }
  return [...tags].sort((a, b) => idx(a) - idx(b) || a.localeCompare(b))
}

class TagCatalog {
  byCode = $state<Record<string, TagMeta>>({})
  loaded = $state(false)
  #loading: Promise<void> | null = null

  ensure(): Promise<void> {
    if (this.loaded) return Promise.resolve()
    this.#loading ??= api
      .tags()
      .then((r) => {
        const next: Record<string, TagMeta> = {}
        for (const t of r.tags) next[t.code] = t
        this.byCode = next
        this.loaded = true
      })
      .catch(() => {
        this.#loading = null
      })
    return this.#loading
  }

  meta(code: string): TagMeta {
    return (
      this.byCode[code] ?? {
        code,
        label_pt: code,
        unit: '',
        kind: 'CONTINUOUS',
        decimals: 1,
        explanation_pt: '',
      }
    )
  }
}

export const tagCatalog = new TagCatalog()
