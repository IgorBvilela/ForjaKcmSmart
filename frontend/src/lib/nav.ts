/** Catálogo das telas, menu principal (4 entradas e Mais) e grupos da página Mais.
 *  Fase = quando a tela deixa de ser EmptyState. */
import type { Component } from 'svelte'
import Gauge from '@lucide/svelte/icons/gauge'
import FileCog from '@lucide/svelte/icons/file-cog'
import Factory from '@lucide/svelte/icons/factory'
import LayoutDashboard from '@lucide/svelte/icons/layout-dashboard'
import Activity from '@lucide/svelte/icons/activity'
import ChartLine from '@lucide/svelte/icons/chart-line'
import Archive from '@lucide/svelte/icons/archive'
import Bell from '@lucide/svelte/icons/bell'
import List from '@lucide/svelte/icons/list'
import Stethoscope from '@lucide/svelte/icons/stethoscope'
import Radar from '@lucide/svelte/icons/radar'
import FolderClock from '@lucide/svelte/icons/folder-clock'
import Siren from '@lucide/svelte/icons/siren'
import Cable from '@lucide/svelte/icons/cable'
import ClipboardCheck from '@lucide/svelte/icons/clipboard-check'
import FileText from '@lucide/svelte/icons/file-text'
import ComponentIcon from '@lucide/svelte/icons/component'
import BookOpen from '@lucide/svelte/icons/book-open'
import BookText from '@lucide/svelte/icons/book-text'
import Library from '@lucide/svelte/icons/library'
import SlidersHorizontal from '@lucide/svelte/icons/sliders-horizontal'
import FileChartColumn from '@lucide/svelte/icons/file-chart-column'
import Download from '@lucide/svelte/icons/download'
import Printer from '@lucide/svelte/icons/printer'
import Settings from '@lucide/svelte/icons/settings'
import DatabaseBackup from '@lucide/svelte/icons/database-backup'
import ScrollText from '@lucide/svelte/icons/scroll-text'
import Info from '@lucide/svelte/icons/info'
import Boxes from '@lucide/svelte/icons/boxes'
import Tv from '@lucide/svelte/icons/tv'
import { hasEqTabs } from './eqtabs'
import {
  href,
  type EqScreen,
  type KnowledgeSub,
  type Route,
  type SystemSub,
  type ToolsSub,
} from './router'

/** Fases do plano que ainda não têm tela. Para o usuário, cada uma vira o nome da etapa. */
export type FuturePhase = 'P'

/** Nome legível da etapa (o que o usuário lê no lugar de "fase P"). */
export const PHASE_NAMES: Record<FuturePhase, string> = {
  P: 'Biblioteca de documentos e manuais',
}

export function phaseName(phase: FuturePhase | string | undefined | null): string | null {
  if (!phase) return null
  return (PHASE_NAMES as Record<string, string>)[phase] ?? null
}

export interface NavItem {
  slug: string
  label: string
  icon: Component<{ size?: number | string; strokeWidth?: number | string; class?: string }>
  /** Monta o href. Itens por equipamento precisam do id selecionado. */
  to: (equipmentId: string | null) => string | null
  /** Fase em que a tela ganha backend. Ausente = já funciona. */
  phase?: FuturePhase
  /** Motivo curto para o estado vazio. */
  reason?: string
  kind: 'now' | 'plant' | 'eq' | 'knowledge' | 'tools' | 'system' | 'more' | 'tv'
  screen?: EqScreen
}

export interface NavGroup {
  id: string
  label: string
  items: NavItem[]
}

function eq(screen: EqScreen, slug: string, label: string, icon: NavItem['icon'], extra: Partial<NavItem> = {}): NavItem {
  return {
    slug,
    label,
    icon,
    kind: 'eq',
    screen,
    to: (id) => (id ? href.eq(id, screen) : null),
    ...extra,
  }
}

/** Catálogo de todas as telas com rota. Títulos e estados vazios saem daqui; o menu só aponta. */
export const ROUTE_ITEMS = {
  now: { slug: 'now', label: 'Agora', icon: Gauge, kind: 'now', to: () => href.now() },
  plant: { slug: 'plant', label: 'Planta', icon: Factory, kind: 'plant', to: () => href.plant() },
  dashboard: eq('dashboard', 'dashboard', 'Dashboard', LayoutDashboard),
  realtime: eq('realtime', 'realtime', 'Tempo Real', Activity),
  trends: eq('trends', 'trends', 'Tendências', ChartLine),
  history: eq('history', 'history', 'Histórico', Archive),
  alerts: eq('alerts', 'alerts', 'Alertas', Bell),
  events: eq('events', 'events', 'Eventos', List),
  diagnostics: eq('diagnostics', 'diagnostics', 'Diagnósticos', Stethoscope),
  earlyWarning: eq('early-warning', 'early-warning', 'Aviso antecipado', Radar),
  cases: eq('cases', 'cases', 'Casos anteriores', FolderClock),
  kcmAlarms: eq('kcm/alarms', 'kcm-alarms', 'Alarmes', Siren),
  kcmCommunication: eq('kcm/communication', 'kcm-communication', 'Comunicação', Cable),
  kcmCommissioning: eq('kcm/commissioning', 'kcm-commissioning', 'Comissionamento', ClipboardCheck),
  kcmDatasheet: eq('kcm/datasheet', 'kcm-datasheet', 'Ficha Técnica', FileText),
  kcmComponents: eq('kcm/components', 'kcm-components', 'Componentes', ComponentIcon),
  knowledgeDocuments: {
    slug: 'knowledge-documents',
    label: 'Documentos',
    icon: BookOpen,
    kind: 'knowledge',
    to: () => href.knowledge('documents'),
    phase: 'P',
    reason: 'Biblioteca de documentos locais com classificação da fonte.',
  },
  knowledgeManuals: {
    slug: 'knowledge-manuals',
    label: 'Manuais',
    icon: BookText,
    kind: 'knowledge',
    to: () => href.knowledge('manuals'),
    phase: 'P',
    reason: 'Manuais do fabricante e da máquina, indexados por seção.',
  },
  knowledgeCases: {
    slug: 'knowledge-cases',
    label: 'Casos de campo',
    icon: Library,
    kind: 'knowledge',
    to: () => href.knowledge('cases'),
  },
  simulator: eq('simulator', 'simulator', 'Simulador', SlidersHorizontal),
  toolsShiftSummary: {
    slug: 'tools-shift-summary',
    label: 'Resumo do turno',
    icon: Printer,
    kind: 'tools',
    to: () => href.tools('shift-summary'),
  },
  toolsReports: {
    slug: 'tools-reports',
    label: 'Relatórios',
    icon: FileChartColumn,
    kind: 'tools',
    to: () => href.tools('reports'),
  },
  toolsExports: {
    slug: 'tools-exports',
    label: 'Exportações',
    icon: Download,
    kind: 'tools',
    to: () => href.tools('exports'),
  },
  systemEquipments: {
    slug: 'system-equipments',
    label: 'Equipamentos',
    icon: Boxes,
    kind: 'system',
    to: () => href.system('equipments'),
  },
  systemSettings: {
    slug: 'system-settings',
    label: 'Configuração',
    icon: FileCog,
    kind: 'system',
    to: () => href.system('settings'),
  },
  systemBackup: {
    slug: 'system-backup',
    label: 'Backup',
    icon: DatabaseBackup,
    kind: 'system',
    to: () => href.system('backup'),
  },
  systemLogs: {
    slug: 'system-logs',
    label: 'Saúde e logs',
    icon: ScrollText,
    kind: 'system',
    to: () => href.system('logs'),
  },
  systemAbout: { slug: 'system-about', label: 'Sobre', icon: Info, kind: 'system', to: () => href.system('about') },
  tv: { slug: 'tv', label: 'Modo TV', icon: Tv, kind: 'tv', to: () => href.tv() },
  more: { slug: 'more', label: 'Mais', icon: Settings, kind: 'more', to: () => href.more() },
} satisfies Record<string, NavItem>

const R = ROUTE_ITEMS

/** Menu principal: quatro entradas. A engrenagem (Mais) fica no pé do menu. */
export const MAIN_MENU: readonly NavItem[] = [R.now, R.plant, R.dashboard, R.kcmCommunication]
export const MORE_ITEM: NavItem = R.more

/** Página Mais: o resto, em grupos. Nada some; só sai da frente. */
export const GEAR_GROUPS: readonly NavGroup[] = [
  {
    id: 'dosador',
    label: 'Do dosador',
    items: [R.kcmDatasheet, R.kcmComponents, R.kcmAlarms, R.kcmCommissioning],
  },
  { id: 'dados', label: 'Dados', items: [R.toolsShiftSummary, R.toolsReports, R.toolsExports] },
  {
    id: 'sistema',
    label: 'Sistema',
    items: [R.systemEquipments, R.systemBackup, R.systemLogs, R.systemSettings, R.tv, R.systemAbout],
  },
  { id: 'demonstracao', label: 'Demonstração', items: [R.simulator] },
  { id: 'conhecimento', label: 'Conhecimento', items: [R.knowledgeCases] },
]

/** Entrada do menu acesa na rota atual. As telas da página Mais acendem a engrenagem. */
export function menuSlugFor(route: Route): string {
  switch (route.name) {
    case 'now':
      return R.now.slug
    case 'plant':
      return R.plant.slug
    case 'eq':
      if (route.screen === 'kcm/communication') return R.kcmCommunication.slug
      return hasEqTabs(route.screen) ? R.dashboard.slug : R.more.slug
    case 'more':
    case 'knowledge':
    case 'tools':
    case 'system':
      return R.more.slug
    default:
      return ''
  }
}

/** Todas as telas, na ordem do catálogo. Não depende de como o menu está agrupado. */
export const NAV_ITEMS: NavItem[] = Object.values(ROUTE_ITEMS)

export function navItemForEqScreen(screen: EqScreen): NavItem | undefined {
  return NAV_ITEMS.find((i) => i.kind === 'eq' && i.screen === screen)
}

export function navItemBySlug(slug: string): NavItem | undefined {
  return NAV_ITEMS.find((i) => i.slug === slug)
}

export function knowledgeItem(sub: KnowledgeSub): NavItem | undefined {
  return navItemBySlug(`knowledge-${sub}`)
}
export function toolsItem(sub: ToolsSub): NavItem | undefined {
  return navItemBySlug(`tools-${sub}`)
}
export function systemItem(sub: SystemSub): NavItem | undefined {
  return navItemBySlug(`system-${sub}`)
}
