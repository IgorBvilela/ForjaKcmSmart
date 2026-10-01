<script lang="ts">
  /** Header: alternador da sidebar, marca, seletor de equipamento, estado do Edge (toque abre a
   *  explicação), selo Somente leitura e relógio. Alvos de 44 px em toque e abaixo de 1024 px. */
  import Menu from '@lucide/svelte/icons/menu'
  import PanelLeftClose from '@lucide/svelte/icons/panel-left-close'
  import PanelLeftOpen from '@lucide/svelte/icons/panel-left-open'
  import Server from '@lucide/svelte/icons/server'
  import { fmtClock, fmtDate } from '../../lib/format'
  import { live } from '../../lib/live.svelte'
  import { href } from '../../lib/router'
  import { app } from '../../lib/state.svelte'
  import { TID } from '../../lib/testids'
  import StatusDot from '../ui/StatusDot.svelte'
  import Tooltip from '../ui/Tooltip.svelte'
  import EquipmentSelect from './EquipmentSelect.svelte'
  import ReadOnlyBadge from './ReadOnlyBadge.svelte'

  const edgeTone = $derived(
    live.edge === 'online' ? 'ok' : live.edge === 'offline' ? 'crit' : 'warn',
  )
  const edgeText = $derived(
    live.edge === 'online'
      ? 'ONLINE'
      : live.edge === 'offline'
        ? 'OFFLINE'
        : live.edge === 'reconnecting'
          ? 'RECONECTANDO'
          : 'CONECTANDO',
  )
  /** Celular: sem texto. Ícone de serviço + ponto; o nome acessível e o toque dizem o resto. */
  const edgeShortPt = $derived(
    live.edge === 'online'
      ? 'Edge respondendo'
      : live.edge === 'offline'
        ? 'Edge sem resposta'
        : 'Edge conectando',
  )
  /** Este sinal fala do Forja Edge (este programa), não do KCM. O chip "Conectado" do dashboard
   *  fala do equipamento. Dois sinais, duas explicações. */
  const edgeTitle = $derived(
    live.edge === 'online'
      ? 'O Forja Edge (este programa) está respondendo. Não significa que o KCM está conectado.'
      : live.edge === 'offline'
        ? 'O Forja Edge (este programa) parou de responder há mais de 12 s. Os valores na tela são os últimos recebidos. Não diz nada sobre o KCM.'
        : 'Aguardando o Forja Edge (este programa) responder.',
  )
  const edgeTitleMobile = $derived(
    live.edge === 'online'
      ? 'Edge respondendo: este programa está no ar. Não significa que o KCM está conectado.'
      : live.edge === 'offline'
        ? 'Edge sem resposta: este programa parou de responder. Os valores na tela são os últimos recebidos.'
        : 'Edge conectando: aguardando este programa responder.',
  )
  const toggleLabel = $derived(
    app.isNarrow ? 'Abrir menu' : app.sidebarCollapsed ? 'Expandir menu' : 'Recolher menu',
  )
</script>

<header class="hdr" data-testid={TID.header.root}>
  <div class="hdr-left">
    <button
      type="button"
      class="icon-btn"
      data-testid={TID.header.menuToggle}
      aria-label={toggleLabel}
      aria-expanded={app.isNarrow ? app.drawerOpen : !app.sidebarCollapsed}
      aria-controls="sidebar"
      onclick={() => app.toggleSidebar()}
    >
      {#if app.isNarrow}
        <Menu size={20} aria-hidden="true" />
      {:else if app.sidebarCollapsed}
        <PanelLeftOpen size={20} aria-hidden="true" />
      {:else}
        <PanelLeftClose size={20} aria-hidden="true" />
      {/if}
    </button>

    <a class="brand" href={href.plant()} aria-label="Forja KCM Intelligence, ir para a planta">
      <svg class="mono" viewBox="0 0 32 32" width="32" height="32" aria-hidden="true">
        <rect width="32" height="32" rx="7" fill="var(--accent)" />
        <rect x="8" y="7" width="3.2" height="18" fill="var(--on-accent)" />
        <rect x="8" y="7" width="10" height="3" fill="var(--on-accent)" />
        <rect x="8" y="14" width="7.5" height="3" fill="var(--on-accent)" />
        <rect x="20.5" y="7" width="3.2" height="18" fill="var(--on-accent)" />
        <rect x="20.5" y="22" width="4.5" height="3" fill="var(--on-accent)" />
      </svg>
      <span class="wordmark">
        <span class="wm-1">FORJA <strong>KCM</strong></span>
        <span class="wm-2">Intelligence</span>
      </span>
    </a>
  </div>

  <div class="hdr-center">
    <EquipmentSelect />
  </div>

  <div class="hdr-right">
    <span class="online" class:icon={app.isMobile} data-testid={TID.header.online} data-state={live.edge}>
      {#if app.isMobile}
        <Tooltip label={edgeShortPt} text={edgeTitleMobile} align="end">
          <Server size={18} strokeWidth={1.75} aria-hidden="true" />
          <StatusDot state={edgeTone} pulse={live.edge === 'online'} size={8} />
        </Tooltip>
      {:else}
        <Tooltip label={`Forja Edge: ${edgeShortPt}`} text={edgeTitle} align="end">
          <StatusDot state={edgeTone} pulse={live.edge === 'online'} size={8} />
          <span class="online-text">{edgeText}</span>
        </Tooltip>
      {/if}
    </span>
    {#if !app.isMobile}
      <ReadOnlyBadge />
    {/if}
    <time class="clock" data-testid={TID.header.clock} datetime={new Date(app.now).toISOString()}>
      <span class="clock-date">{fmtDate(app.now)}</span>
      <span class="clock-time num">{fmtClock(new Date(app.now), !app.isNarrow)}</span>
    </time>
  </div>
</header>

<style>
  .hdr {
    position: sticky;
    top: 0;
    z-index: 20;
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: var(--sp-4);
    height: var(--header-h);
    padding: 0 var(--sp-6) 0 var(--sp-4);
    background: var(--surf-1);
    border-bottom: 1px solid var(--border-1);
  }
  .hdr-left { display: flex; align-items: center; gap: var(--sp-3); min-width: 0; }
  .hdr-center { display: flex; justify-content: center; min-width: 0; }
  .hdr-right { display: flex; align-items: center; gap: var(--sp-3); justify-content: flex-end; }

  .icon-btn {
    display: grid;
    place-items: center;
    width: 40px;
    height: 40px;
    border: 0;
    border-radius: var(--r-3);
    background: transparent;
    color: var(--text-2);
    cursor: pointer;
    transition:
      background-color var(--dur-base) var(--ease-std),
      color var(--dur-base) var(--ease-std);
  }
  .icon-btn:hover { background: var(--surf-2); color: var(--text-1); }

  .brand {
    display: flex;
    align-items: center;
    gap: var(--sp-3);
    min-height: var(--touch);
    color: inherit;
    text-decoration: none;
    border-radius: var(--r-2);
    padding-right: var(--sp-2);
  }
  .mono { flex: none; }
  .wordmark { display: flex; flex-direction: column; line-height: 1; }
  .wm-1 {
    font: 600 15px / 16px var(--font-ui);
    letter-spacing: 0.02em;
    color: var(--text-1);
  }
  .wm-1 strong { color: var(--accent-text); font-weight: 600; }
  .wm-2 {
    font: 500 var(--fs-label) / 12px var(--font-ui);
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--text-3);
  }

  .online {
    display: inline-flex;
    align-items: center;
    color: var(--text-2);
    font: 600 var(--fs-label) / var(--lh-label) var(--font-ui);
    letter-spacing: var(--ls-label);
    white-space: nowrap;
  }
  .online :global(.tip-btn) { gap: var(--sp-2); }
  .online[data-state='online'] .online-text { color: var(--st-ok); }
  .online[data-state='offline'] .online-text { color: var(--st-crit); }
  /* celular: ícone de serviço com o ponto de estado encostado no canto, num alvo de 44 px */
  .online.icon :global(.tip-btn) {
    position: relative;
    width: var(--touch);
    min-height: var(--touch);
    padding: 0;
    justify-content: center;
    gap: 0;
    color: var(--text-2);
  }
  .online.icon :global(.dot) {
    position: absolute;
    right: 9px;
    top: 10px;
    box-shadow: 0 0 0 2px var(--surf-1);
  }

  /* data em fonte da interface; só a hora é número (mono) */
  .clock {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    color: var(--text-2);
    white-space: nowrap;
  }
  .clock-date { color: var(--text-3); font: var(--fs-caption) / 14px var(--font-ui); }
  .clock-time { color: var(--text-1); font-size: var(--fs-mono); line-height: 16px; }

  @media (max-width: 1279px) {
    .wordmark { display: none; }
    .hdr { gap: var(--sp-3); }
    .brand { min-width: var(--touch); justify-content: center; padding: 0; }
  }
  @media (max-width: 1023px), (pointer: coarse) {
    .icon-btn { width: var(--touch); height: var(--touch); }
  }
  @media (max-width: 1023px) {
    .clock-date { display: none; }
    .hdr-right { gap: var(--sp-2); }
  }
  @media (max-width: 767px) {
    .hdr {
      grid-template-columns: auto minmax(0, 1fr) auto;
      padding: 0 var(--sp-2);
      gap: var(--sp-2);
    }
    .hdr-left { gap: var(--sp-2); }
    .hdr-center { justify-content: stretch; }
  }
  /* celular estreito: o seletor precisa de ~250 px para "nome · estado" inteiro; a marca sai
     do header (mora no topo do drawer) e o relógio também */
  @media (max-width: 479px) {
    .clock { display: none; }
    .brand { display: none; }
  }
</style>
