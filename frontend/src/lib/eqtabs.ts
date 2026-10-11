/** Abas do dosador: Visão, Variáveis, Gráficos e Ocorrências, cada uma apontando para rotas que
 *  já existem. Comunicação e as telas de configuração do dosador ficam fora das abas. */
import type { EqScreen } from './router'

export type TabId = 'visao' | 'variaveis' | 'graficos' | 'ocorrencias'

export interface EqTab {
  id: TabId
  label: string
  screens: readonly EqScreen[]
  home: EqScreen
}

export const EQ_TABS: readonly EqTab[] = [
  { id: 'visao', label: 'Visão', screens: ['dashboard'], home: 'dashboard' },
  { id: 'variaveis', label: 'Variáveis', screens: ['realtime'], home: 'realtime' },
  { id: 'graficos', label: 'Gráficos', screens: ['trends', 'history'], home: 'trends' },
  {
    id: 'ocorrencias',
    label: 'Ocorrências',
    screens: ['alerts', 'events', 'diagnostics', 'early-warning', 'cases'],
    home: 'alerts',
  },
]

export const EQ_SUBTABS: Partial<Record<TabId, readonly { label: string; screen: EqScreen }[]>> = {
  graficos: [
    { label: 'Gráfico', screen: 'trends' },
    { label: 'Tabela', screen: 'history' },
  ],
  ocorrencias: [
    { label: 'Alertas', screen: 'alerts' },
    { label: 'Eventos', screen: 'events' },
    { label: 'Diagnósticos', screen: 'diagnostics' },
    { label: 'Aviso antecipado', screen: 'early-warning' },
    { label: 'Casos anteriores', screen: 'cases' },
  ],
}

const TAB_SCREENS: ReadonlySet<EqScreen> = new Set(EQ_TABS.flatMap((t) => t.screens))

/** Telas do dosador que mostram as abas. */
export function hasEqTabs(screen: EqScreen): boolean {
  return TAB_SCREENS.has(screen)
}

export function activeTab(screen: EqScreen): TabId {
  return EQ_TABS.find((t) => t.screens.includes(screen))?.id ?? 'visao'
}
