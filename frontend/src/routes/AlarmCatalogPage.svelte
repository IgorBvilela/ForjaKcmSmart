<script lang="ts">
  /** KCM › Alarmes: catálogo por chave composta (fabricante, controlador, aplicação, versão).
   *  O mesmo número pode significar outra coisa fora da chave; aqui nada é "universal". */
  import { untrack } from 'svelte'
  import { errorMessage } from '../lib/api'
  import { equipmentApi, isUnknown, shown, type AlarmCatalogView, type AlarmEntry } from '../lib/equipment'
  import { live } from '../lib/live.svelte'
  import { href } from '../lib/router'
  import Badge from '../components/ui/Badge.svelte'
  import Card from '../components/ui/Card.svelte'
  import Disclosure from '../components/ui/Disclosure.svelte'
  import EmptyState from '../components/ui/EmptyState.svelte'

  let { equipmentId }: { equipmentId: string } = $props()

  let view = $state<AlarmCatalogView | null>(null)
  let error = $state<string | null>(null)

  const name = $derived(live.cardOf(equipmentId)?.name ?? equipmentId)

  async function load(id: string): Promise<void> {
    try {
      const v = await equipmentApi.alarmCatalog(id)
      if (id !== equipmentId) return
      view = v
      error = null
    } catch (err) {
      if (id === equipmentId) error = errorMessage(err)
    }
  }

  $effect(() => {
    const id = equipmentId
    untrack(() => void load(id))
  })

  const KEY_PT: Record<string, string> = {
    manufacturer: 'Fabricante',
    controller: 'Controlador',
    application: 'Aplicação',
    software_version: 'Versão de software',
  }
  const tone = (e: string) => (e === 'MANUFACTURER_DOC' || e === 'MACHINE_DOC' || e === 'FIELD_CONFIRMED' ? 'ok' : e === 'HYPOTHESIS' ? 'warn' : 'info')
  const keyText = (a: AlarmEntry) =>
    [a.key.manufacturer, a.key.controller, a.key.application, a.key.software_version].map(shown).join(' · ')
</script>

{#snippet table(list: AlarmEntry[], withKey: boolean)}
  <table class="resp">
    <thead>
      <tr><th>Código</th><th>No KCM</th><th>Significado</th><th>Evidência</th>{#if withKey}<th>Chave</th>{/if}</tr>
    </thead>
    <tbody>
      {#each list as a (keyText(a) + a.key.code)}
        <tr>
          <th data-label="Código" class="mono">{a.key.code}</th>
          <td data-label="No KCM" class="mono">{a.text}</td>
          <td data-label="Significado" class="wide">
            <b>{a.title_pt}</b>
            {#if a.meaning_pt}<span class="meaning">{a.meaning_pt}</span>{/if}
            {#if a.note_pt}<span class="meaning">{a.note_pt}</span>{/if}
          </td>
          <td data-label="Evidência" class="wide">
            <Badge tone={tone(a.evidence)}>{a.evidence_pt}</Badge>
            {#if !isUnknown(a.source)}<span class="meaning">{a.source}</span>{/if}
          </td>
          {#if withKey}<td data-label="Chave" class="small wide">{keyText(a)}</td>{/if}
        </tr>
      {/each}
    </tbody>
  </table>
{/snippet}

<section class="alarms" data-testid="alarm-catalog">
  <header class="head">
    <p class="label">{name}</p>
    <h1 class="title">Alarmes do KCM</h1>
    <p class="sub">
      Catálogo por chave composta. O mesmo número pode significar outra coisa em outra aplicação ou
      versão de software: só vale o que casa com a chave deste equipamento.
    </p>
  </header>

  {#if error && !view}
    <EmptyState title="Não foi possível carregar o catálogo" text={error} />
  {:else if !view}
    <div class="sk" aria-busy="true" aria-label="Carregando catálogo"></div>
  {:else}
    <Card title="Chave deste equipamento" kicker="vem da ficha técnica" testid="alarm-key">
      <dl class="key">
        {#each Object.entries(view.key) as [k, v] (k)}
          <div><dt>{KEY_PT[k] ?? k}</dt><dd class:unknown={isUnknown(v)}>{shown(v)}</dd></div>
        {/each}
      </dl>
      {#if view.key_unknown.length}
        <p class="warn">
          Parte da chave é desconhecida. Só valem entradas catalogadas exatamente assim; confirme a
          informação no equipamento e atualize a <a class="inline" href={href.eq(equipmentId, 'kcm/datasheet')}>ficha técnica</a>.
        </p>
      {/if}
    </Card>

    <Card title="Alarmes catalogados para esta chave" kicker={`${view.alarms.length} entrada(s)`} padded={false} testid="alarm-list">
      {#if view.alarms.length === 0}
        <div class="pad">
          <EmptyState inline title="Nenhum alarme catalogado para esta chave" text="Quando o KCM informar um código, a Forja mostra 'não catalogado' em vez de inventar um significado." />
        </div>
      {:else}
        <div class="pad">{@render table(view.alarms, false)}</div>
      {/if}
    </Card>

    {#if view.other_keys.length}
      <Disclosure summary={`Outras chaves (${view.other_keys.length}): não valem para este equipamento`} testid="alarm-other">
        <div class="pad">{@render table(view.other_keys, true)}</div>
      </Disclosure>
    {/if}

    <p class="note">{view.note_pt}</p>
  {/if}
</section>

<style>
  .alarms { display: flex; flex-direction: column; gap: var(--sp-5); }
  .head .label { margin: 0 0 var(--sp-1); }
  .title { margin: 0; color: var(--text-1); font: 600 var(--fs-h1) / var(--lh-h1) var(--font-ui); }
  @media (min-width: 1024px) {
    .title { font-size: var(--fs-display); line-height: var(--lh-display); }
  }
  .sub { margin: var(--sp-1) 0 0; max-width: 72ch; color: var(--text-2); font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  .key { display: grid; gap: var(--sp-2) var(--sp-4); grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); margin: 0; }
  .key > div { display: flex; flex-direction: column; gap: 2px; }
  dt { color: var(--text-2); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  dd { margin: 0; color: var(--text-1); font: 600 var(--fs-body) / var(--lh-body) var(--font-ui); }
  dd.unknown { color: var(--text-2); font-weight: 500; }
  .warn { margin: var(--sp-3) 0 0; padding: var(--sp-2) var(--sp-3); border-radius: var(--r-3); background: var(--st-warn-bg); color: var(--text-1); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .inline { color: var(--accent-text); text-decoration: underline; }
  .pad { padding: var(--sp-4); }
  table { width: 100%; border-collapse: collapse; font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  th, td { padding: var(--sp-2); border-bottom: 1px solid var(--border-1); text-align: left; vertical-align: top; color: var(--text-1); }
  thead th { color: var(--text-2); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .mono { font-family: var(--font-mono); font-size: var(--fs-mono); }
  .meaning { display: block; margin-top: 2px; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .small { color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .note { margin: 0; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); max-width: 80ch; }
  .sk { height: 200px; border-radius: var(--r-4); background: var(--surf-2); opacity: 0.6; }
</style>
