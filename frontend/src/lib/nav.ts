/** Catálogo das telas e grupos da sidebar. Fase = quando a tela deixa de ser EmptyState. */
import type { Component } from 'svelte'
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
import Settings from '@lucide/svelte/icons/settings'
import DatabaseBackup from '@lucide/svelte/icons/database-backup'
import ScrollText from '@lucide/svelte/icons/scroll-text'
import Info from '@lucide/svelte/icons/info'
import Boxes from '@lucide/svelte/icons/boxes'
import { href, type EqScreen, type KnowledgeSub, type SystemSub, type ToolsSub } from './router'

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
  kind: 'plant' | 'eq' | 'knowledge' | 'tools' | 'system'
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
    label: 'Casos',
    icon: Library,
    kind: 'knowledge',
    to: () => href.knowledge('cases'),
  },
  simulator: eq('simulator', 'simulator', 'Simulador', SlidersHorizontal),
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
    icon: Settings,
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
} satisfies Record<string, NavItem>

const R = ROUTE_ITEMS

export const NAV_GROUPS: NavGroup[] = [
  { id: 'visao', label: 'Visão', items: [R.plant, R.dashboard] },
  { id: 'processo', label: 'Processo', items: [R.realtime, R.trends, R.history] },
  {
    id: 'inteligencia',
    label: 'Inteligência',
    items: [R.alerts, R.events, R.diagnostics, R.earlyWarning, R.cases],
  },
  {
    id: 'kcm',
    label: 'KCM',
    items: [R.kcmAlarms, R.kcmCommunication, R.kcmCommissioning, R.kcmDatasheet, R.kcmComponents],
  },
  {
    id: 'conhecimento',
    label: 'Conhecimento',
    items: [R.knowledgeDocuments, R.knowledgeManuals, R.knowledgeCases],
  },
  { id: 'ferramentas', label: 'Ferramentas', items: [R.simulator, R.toolsReports, R.toolsExports] },
  {
    id: 'sistema',
    label: 'Sistema',
    items: [R.systemEquipments, R.systemSettings, R.systemBackup, R.systemLogs, R.systemAbout],
  },
]

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
