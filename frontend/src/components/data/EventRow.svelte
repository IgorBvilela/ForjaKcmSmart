<script lang="ts">
  import ChevronRight from '@lucide/svelte/icons/chevron-right'
  import { severityTone, type EventView } from '../../lib/api'
  import { ageSince, fmtDuration, fmtWhen } from '../../lib/format'
  import { app } from '../../lib/state.svelte'
  import { TID } from '../../lib/testids'
  import Badge from '../ui/Badge.svelte'
  import StatusDot from '../ui/StatusDot.svelte'

  let {
    event,
    href,
    hasDiagnosis = null,
    index = 0,
  }: { event: EventView; href: string; hasDiagnosis?: boolean | null; index?: number } = $props()

  const tone = $derived(severityTone(event.severity))
  const duration = $derived.by(() => {
    if (event.end_utc) return fmtDuration(event.duration_s)
    const open = ageSince(event.start_utc, app.now)
    return `em aberto · ${fmtDuration(open)}`
  })
  const statusTone = $derived(
    event.status === 'OPEN' ? tone : event.status === 'ACKNOWLEDGED' ? 'info' : 'ghost',
  )
</script>

<a
  class="row"
  {href}
  data-testid={TID.events.row(event.id)}
  data-severity={event.severity}
  data-status={event.status}
  style:--i={index}
>
  <span class="mark"><StatusDot state={tone} size={10} hollow={!event.is_open} /></span>
  <span class="body">
    <span class="title-line">
      <span class="title">{event.title_pt}</span>
      {#if hasDiagnosis}<Badge tone="accent">Diagnóstico</Badge>{/if}
      {#if event.quality === 'SIMULATED'}<Badge tone="sim" hatch>Simulado</Badge>{/if}
    </span>
    <span class="summary">{event.summary_pt}</span>
    <span class="meta">
      <time datetime={event.start_utc} class="num">{fmtWhen(event.start_utc, app.now)}</time>
      <span class="sep" aria-hidden="true">·</span>
      <span>{duration}</span>
      <span class="sep" aria-hidden="true">·</span>
      <Badge tone={statusTone}>{event.status_pt}</Badge>
    </span>
  </span>
  <span class="chev" aria-hidden="true"><ChevronRight size={18} /></span>
</a>

<style>
  .row {
    display: grid;
    grid-template-columns: 20px minmax(0, 1fr) 20px;
    gap: var(--sp-3);
    align-items: start;
    padding: var(--sp-4) var(--sp-5);
    color: inherit;
    text-decoration: none;
    border-top: 1px solid var(--border-1);
    background: var(--surf-1);
    transition: background-color var(--dur-base) var(--ease-std);
    animation: rise var(--dur-screen) var(--ease-out) both;
    animation-delay: calc(var(--i, 0) * var(--stagger));
  }
  @keyframes rise {
    from { opacity: 0; transform: translateY(4px); }
    to { opacity: 1; transform: none; }
  }
  .row:first-child { border-top: 0; }
  .row:hover { background: var(--surf-2); }
  .mark { display: grid; place-items: center; height: var(--lh-body); }
  .body { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .title-line { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-2); }
  .title { color: var(--text-1); font: 600 var(--fs-body) / var(--lh-body) var(--font-ui); }
  .summary {
    color: var(--text-2);
    font: var(--fs-body) / var(--lh-body) var(--font-ui);
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--sp-2);
    color: var(--text-3);
    font: var(--fs-caption) / var(--lh-caption) var(--font-ui);
  }
  .meta .num { font-size: var(--fs-mono-sm); }
  .sep { color: var(--border-2); }
  .chev { color: var(--text-3); display: grid; place-items: center; height: var(--lh-body); }
  @media (max-width: 767px) {
    .row { padding: var(--sp-4); }
  }
</style>
