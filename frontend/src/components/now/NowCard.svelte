<script lang="ts">
  /** Dosador que pede atenção: desde quando, o que mudou primeiro e o que verificar primeiro. */
  import Activity from '@lucide/svelte/icons/activity'
  import Check from '@lucide/svelte/icons/check'
  import CircleAlert from '@lucide/svelte/icons/circle-alert'
  import Copy from '@lucide/svelte/icons/copy'
  import Radar from '@lucide/svelte/icons/radar'
  import AckForm from '../data/AckForm.svelte'
  import EvidenceBadge from '../data/EvidenceBadge.svelte'
  import Badge from '../ui/Badge.svelte'
  import { severityTone, type EventStatus, type EventView } from '../../lib/api'
  import { copyText } from '../../lib/clipboard'
  import { ageSince, fmtAge } from '../../lib/format'
  import { href } from '../../lib/router'
  import { readyPhrase, sinceText, type SituationEntry } from '../../lib/situation'

  let { entry, now }: { entry: SituationEntry; now: number } = $props()

  let acked = $state<{ status: EventStatus; acked_by: string | null } | null>(null)
  let copied = $state(false)

  const focus = $derived(entry.focus)
  const kcm = $derived(entry.voices.kcm_alarm)
  const tone = $derived(entry.severity ? severityTone(entry.severity) : 'warn')
  const since = $derived(sinceText(entry))
  const age = $derived(
    entry.since_basis === 'EVENT' || entry.since_basis === 'HISTORIAN'
      ? fmtAge(ageSince(entry.since_utc, now))
      : null,
  )
  const ackEvent = $derived(
    focus
      ? {
          id: focus.event_id,
          status: acked?.status ?? focus.status,
          acked_by: acked?.acked_by ?? focus.acked_by,
        }
      : null,
  )

  async function copyPhrase(): Promise<void> {
    copied = await copyText(readyPhrase(entry))
    if (copied) setTimeout(() => (copied = false), 2200)
  }

  function onAck(updated: EventView): void {
    acked = { status: updated.status, acked_by: updated.acked_by }
  }
</script>

<article class="card" data-tone={tone} data-testid={`now-card-${entry.id}`}>
  <header class="head">
    <Badge {tone} size="md">{focus ? entry.state_pt : 'Alarme do KCM'}</Badge>
    <h3 class="name">{entry.name}</h3>
    {#if since}<span class="since">{age ? `${since} · ${age}` : since}</span>{/if}
  </header>

  {#if focus}
    <p class="title" data-testid="now-focus-title">{focus.title_pt}</p>
    <dl class="facts">
      <div class="fact" data-testid="now-changed-first">
        <dt>Mudou primeiro</dt>
        <dd>
          {#if focus.changed_first}
            {focus.changed_first.label_pt}
            <span class="sub">{focus.changed_first.text_pt}</span>
          {:else if focus.origin === 'EARLY_WARNING'}
            Tendência da janela inteira; os sinais estão no Aviso antecipado.
          {:else}
            Nenhuma variável saiu do padrão antes da abertura.
          {/if}
        </dd>
      </div>
      <div class="fact check" data-testid={focus.next_check ? 'now-next-check' : 'now-next-check-pending'}>
        <dt>Verificar primeiro</dt>
        <dd>
          {#if focus.next_check}
            <span class="what">{focus.next_check.text_pt}</span>
            <EvidenceBadge level={focus.next_check.evidence_level} />
          {:else}
            <span class="pending">Diagnóstico em preparação.</span>
          {/if}
        </dd>
      </div>
    </dl>
    {#if focus.hypothesis_pt}<p class="hyp">{focus.hypothesis_pt}</p>{/if}
  {/if}

  <ul class="origins" aria-label="De onde veio">
    {#if kcm}
      <li class="origin kcm" data-testid="now-origin-kcm">
        <CircleAlert size={14} aria-hidden="true" />
        Alarme do KCM {kcm.code ?? ''}{kcm.title_pt ? ` · ${kcm.title_pt}` : ''}
      </li>
    {/if}
    {#each entry.voices.forja_events as ev (ev.id)}
      <li class="origin forja" data-testid="now-origin-forja">
        <Activity size={14} aria-hidden="true" /> Evento da Forja · {ev.title_pt}
      </li>
    {/each}
    {#each entry.voices.early_warnings as ev (ev.id)}
      <li class="origin ew" data-testid="now-origin-ew">
        <Radar size={14} aria-hidden="true" /> Aviso antecipado · {ev.title_pt}
      </li>
    {/each}
  </ul>

  <div class="actions">
    {#if focus}
      <a class="btn" href={href.event(entry.id, focus.event_id)}>Ver diagnóstico</a>
    {:else}
      <a class="btn" href={href.eq(entry.id)}>Abrir o dosador</a>
    {/if}
    <button class="btn ghost" type="button" onclick={copyPhrase} data-testid="now-copy">
      {#if copied}
        <span class="pop"><Check size={16} aria-hidden="true" /></span> Frase copiada
      {:else}
        <Copy size={16} aria-hidden="true" /> Copiar frase
      {/if}
    </button>
    {#if ackEvent}
      <div class="ack-slot"><AckForm event={ackEvent} ondone={onAck} /></div>
    {:else}
      <p class="note">Reconhecer o alarme é feito no próprio KCM.</p>
    {/if}
  </div>
</article>

<style>
  .card {
    display: flex;
    flex-direction: column;
    gap: var(--sp-3);
    padding: var(--sp-4);
    border: 1px solid var(--border-1);
    border-left: 3px solid var(--st-warn);
    border-radius: var(--r-3);
    background: var(--surf-1);
    animation: rise var(--dur-screen) var(--ease-out) both;
  }
  .card[data-tone='crit'] { border-left-color: var(--st-crit); }
  @keyframes rise {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: none; }
  }
  .head { display: flex; align-items: center; gap: var(--sp-2) var(--sp-3); flex-wrap: wrap; }
  .name { margin: 0; color: var(--text-1); font: 600 var(--fs-h2) / var(--lh-h2) var(--font-ui); }
  .since { color: var(--text-2); font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  .title { margin: 0; color: var(--text-1); font: 600 var(--fs-body-lg) / var(--lh-body-lg) var(--font-ui); }
  .facts { display: flex; flex-direction: column; gap: var(--sp-2); margin: 0; }
  .fact { display: grid; grid-template-columns: 150px minmax(0, 1fr); gap: var(--sp-1) var(--sp-3); }
  dt {
    padding-top: 3px;
    color: var(--text-3);
    font: 500 var(--fs-label) / var(--lh-label) var(--font-ui);
    letter-spacing: var(--ls-label);
    text-transform: uppercase;
  }
  dd { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--sp-1) var(--sp-2); margin: 0; color: var(--text-1); font: var(--fs-body-lg) / var(--lh-body-lg) var(--font-ui); }
  .sub { flex-basis: 100%; color: var(--text-2); font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  .check .what { font-weight: 600; }
  .pending { color: var(--text-2); }
  .hyp { margin: 0; color: var(--text-2); font: italic var(--fs-body) / var(--lh-body) var(--font-ui); }
  .origins { display: flex; flex-wrap: wrap; gap: var(--sp-2); margin: 0; padding: 0; list-style: none; }
  .origin {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 10px;
    border-radius: var(--r-1);
    color: var(--text-1);
    font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui);
  }
  .origin.kcm { border: 1px solid color-mix(in srgb, var(--st-crit) 55%, transparent); background: var(--st-crit-bg); }
  .origin.forja { border: 1px solid var(--border-2); border-left: 3px solid var(--st-warn); background: var(--surf-2); }
  .origin.ew { border: 1px dashed var(--border-input); background: var(--surf-2); }
  .actions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-2); }
  .ack-slot:has(:global(form)) { flex-basis: 100%; }
  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--sp-2);
    min-height: var(--touch);
    padding: 0 var(--sp-4);
    border: 1px solid var(--border-2);
    border-radius: var(--r-3);
    background: var(--surf-2);
    color: var(--text-1);
    font: 600 var(--fs-body) / 1.2 var(--font-ui);
    text-decoration: none;
    cursor: pointer;
    transition: background-color var(--dur-micro) var(--ease-std), transform var(--dur-micro) var(--ease-std);
  }
  .btn:hover { background: var(--surf-3); }
  .btn:active { transform: scale(0.97); }
  .btn.ghost { background: transparent; }
  .pop { display: inline-flex; color: var(--st-ok); animation: pop 420ms var(--ease-out); }
  @keyframes pop {
    0% { transform: scale(0.4); opacity: 0; }
    60% { transform: scale(1.18); opacity: 1; }
    100% { transform: scale(1); }
  }
  .note { margin: 0; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  @media (max-width: 560px) {
    .fact { grid-template-columns: minmax(0, 1fr); }
  }
</style>
