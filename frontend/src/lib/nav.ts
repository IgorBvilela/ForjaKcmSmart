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
import { href, type EqScreen, type KnowledgeSub, type SystemSub, type ToolsSub } from './router'

/** Fases do plano que ainda não têm tela. Para o usuário, cada uma vira o nome da etapa. */
export type FuturePhase = 'E' | 'F' | 'G' | 'L' | 'M'

/** Nome legível da etapa (o que o usuário lê no lugar de "fase E"). */
export const PHASE_NAMES: Record<FuturePhase, string> = {
  E: 'Tendências e histórico',
  F: 'Alertas e diagnóstico avançado',
  G: 'Comunicação com o KCM',
  L: 'Saúde e registros',
  M: 'Relatórios, backup e usuários',
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
      eq('realtime', 'realtime', 'Tempo Real', Activity, {
        phase: 'E',
        reason: 'Tabela ao vivo de todas as variáveis mapeadas, com qualidade e idade por tag.',
      }),
      eq('trends', 'trends', 'Tendências', ChartLine, {
        phase: 'E',
        reason: 'Gráficos por variável com janela de tempo, buracos explícitos e sem interpolação.',
      }),
      eq('history', 'history', 'Histórico', Archive, {
        phase: 'E',
        reason: 'Consulta ao historiador por período, com exportação dos pontos brutos.',
      }),
    ],
  },
  {
    id: 'inteligencia',
    label: 'Inteligência',
    items: [
      eq('alerts', 'alerts', 'Alertas', Bell, {
        phase: 'F',
        reason: 'Lista de condições abertas com reconhecimento auditado.',
      }),
      eq('events', 'events', 'Eventos', List),
      eq('diagnostics', 'diagnostics', 'Diagnósticos', Stethoscope),
      eq('early-warning', 'early-warning', 'Early Warning', Radar, {
        phase: 'F',
        reason: 'Sinais fracos antes do alarme: tendência de desvio em relação ao padrão do equipamento.',
      }),
      eq('cases', 'cases', 'Casos anteriores', FolderClock, {
        phase: 'F',
        reason: 'Casos de campo deste equipamento, com o que foi verificado e o que se confirmou.',
      }),
    ],
  },
  {
    id: 'kcm',
    label: 'KCM',
    items: [
      eq('kcm/alarms', 'kcm-alarms', 'Alarmes', Siren, {
        phase: 'G',
        reason: 'Catálogo de alarmes por chave composta (fabricante, controlador, aplicação, versão).',
      }),
      eq('kcm/communication', 'kcm-communication', 'Comunicação', Cable, {
        phase: 'G',
        reason: 'Assistente de comunicação e teste somente leitura. Leitura direta do KCM via Host/Anybus.',
      }),
      eq('kcm/datasheet', 'kcm-datasheet', 'Ficha Técnica', FileText, {
        phase: 'G',
        reason: 'Perfil do equipamento com classificação de cada informação (FACT, FIELD_OBSERVED, UNKNOWN).',
      }),
      eq('kcm/components', 'kcm-components', 'Componentes', ComponentIcon, {
        phase: 'G',
        reason: 'KCM, MDU, SFT, SIB, encoder, motor e Anybus com a evidência de cada um.',
      }),
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
        phase: 'M',
        reason: 'Biblioteca de documentos locais com classificação da fonte.',
      },
      {
        slug: 'knowledge-manuals',
        label: 'Manuais',
        icon: BookText,
        kind: 'knowledge',
        to: () => href.knowledge('manuals'),
        phase: 'M',
        reason: 'Manuais do fabricante e da máquina, indexados por seção.',
      },
      {
        slug: 'knowledge-cases',
        label: 'Casos',
        icon: Library,
        kind: 'knowledge',
        to: () => href.knowledge('cases'),
        phase: 'F',
        reason: 'Biblioteca de casos de campo de todos os equipamentos.',
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
        phase: 'M',
        reason: 'Relatório por período com eventos, diagnósticos e qualidade dos dados.',
      },
      {
        slug: 'tools-exports',
        label: 'Exportações',
        icon: Download,
        kind: 'tools',
        to: () => href.tools('exports'),
        phase: 'M',
        reason: 'Exportação de séries e eventos em CSV, sempre com a qualidade ao lado do valor.',
      },
    ],
  },
  {
    id: 'sistema',
    label: 'Sistema',
    items: [
      {
        slug: 'system-settings',
        label: 'Configuração',
        icon: Settings,
        kind: 'system',
        to: () => href.system('settings'),
        phase: 'M',
        reason: 'Preferências do Edge, usuários e permissões.',
      },
      {
        slug: 'system-backup',
        label: 'Backup',
        icon: DatabaseBackup,
        kind: 'system',
        to: () => href.system('backup'),
        phase: 'M',
        reason: 'Cópia e restauração dos bancos locais.',
      },
      {
        slug: 'system-logs',
        label: 'Logs',
        icon: ScrollText,
        kind: 'system',
        to: () => href.system('logs'),
        phase: 'L',
        reason: 'Logs do serviço e saúde detalhada (historiador, bus, motor de eventos).',
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
