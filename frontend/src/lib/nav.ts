/** Os 7 grupos da sidebar (spec §46) e as rotas de cada item. Fase = quando a tela deixa de ser EmptyState. */
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

export const NAV_GROUPS: NavGroup[] = [
  {
    id: 'visao',
    label: 'Visão',
    items: [
      { slug: 'plant', label: 'Planta', icon: Factory, kind: 'plant', to: () => href.plant() },
      eq('dashboard', 'dashboard', 'Dashboard', LayoutDashboard),
    ],
  },
  {
    id: 'processo',
    label: 'Processo',
    items: [
      eq('realtime', 'realtime', 'Tempo Real', Activity),
      eq('trends', 'trends', 'Tendências', ChartLine),
      eq('history', 'history', 'Histórico', Archive),
    ],
  },
  {
    id: 'inteligencia',
    label: 'Inteligência',
    items: [
      eq('alerts', 'alerts', 'Alertas', Bell),
      eq('events', 'events', 'Eventos', List),
      eq('diagnostics', 'diagnostics', 'Diagnósticos', Stethoscope),
      eq('early-warning', 'early-warning', 'Aviso antecipado', Radar),
      eq('cases', 'cases', 'Casos anteriores', FolderClock),
    ],
  },
  {
    id: 'kcm',
    label: 'KCM',
    items: [
      eq('kcm/alarms', 'kcm-alarms', 'Alarmes', Siren),
      eq('kcm/communication', 'kcm-communication', 'Comunicação', Cable),
      eq('kcm/commissioning', 'kcm-commissioning', 'Comissionamento', ClipboardCheck),
      eq('kcm/datasheet', 'kcm-datasheet', 'Ficha Técnica', FileText),
      eq('kcm/components', 'kcm-components', 'Componentes', ComponentIcon),
    ],
  },
  {
    id: 'conhecimento',
    label: 'Conhecimento',
    items: [
      {
        slug: 'knowledge-documents',
        label: 'Documentos',
        icon: BookOpen,
        kind: 'knowledge',
        to: () => href.knowledge('documents'),
        phase: 'P',
        reason: 'Biblioteca de documentos locais com classificação da fonte.',
      },
      {
        slug: 'knowledge-manuals',
        label: 'Manuais',
        icon: BookText,
        kind: 'knowledge',
        to: () => href.knowledge('manuals'),
        phase: 'P',
        reason: 'Manuais do fabricante e da máquina, indexados por seção.',
      },
      {
        slug: 'knowledge-cases',
        label: 'Casos',
        icon: Library,
        kind: 'knowledge',
        to: () => href.knowledge('cases'),
      },
    ],
  },
  {
    id: 'ferramentas',
    label: 'Ferramentas',
    items: [
      eq('simulator', 'simulator', 'Simulador', SlidersHorizontal),
      {
        slug: 'tools-reports',
        label: 'Relatórios',
        icon: FileChartColumn,
        kind: 'tools',
        to: () => href.tools('reports'),
      },
      {
        slug: 'tools-exports',
        label: 'Exportações',
        icon: Download,
        kind: 'tools',
        to: () => href.tools('exports'),
      },
    ],
  },
  {
    id: 'sistema',
    label: 'Sistema',
    items: [
      {
        slug: 'system-equipments',
        label: 'Equipamentos',
        icon: Boxes,
        kind: 'system',
        to: () => href.system('equipments'),
      },
      {
        slug: 'system-settings',
        label: 'Configuração',
        icon: Settings,
        kind: 'system',
        to: () => href.system('settings'),
      },
      {
        slug: 'system-backup',
        label: 'Backup',
        icon: DatabaseBackup,
        kind: 'system',
        to: () => href.system('backup'),
      },
      {
        slug: 'system-logs',
        label: 'Saúde e logs',
        icon: ScrollText,
        kind: 'system',
        to: () => href.system('logs'),
      },
      { slug: 'system-about', label: 'Sobre', icon: Info, kind: 'system', to: () => href.system('about') },
    ],
  },
]

export const NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((g) => g.items)

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
