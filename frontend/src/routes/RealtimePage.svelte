<script lang="ts">
  /** Tempo Real: todas as variáveis mapeadas, com qualidade, idade e mini-tendência.
   *  Valor antigo (STALE) aparece desbotado com a idade; sem comunicação aparece como travessão
   *  com o motivo. O protagonista é a condição, não o número: o número fica aqui, completo. */
  import { untrack } from 'svelte'
  import { api, connectionTone, type AlarmLookupView, type RuntimeStatus } from '../lib/api'
  import { discreteText, rawStatusText } from '../lib/discrete'
  import { fmtAge, fmtNumber, fmtWhen } from '../lib/format'
  import { live } from '../lib/live.svelte'
  import { app } from '../lib/state.svelte'
  import { sortTags, tagCatalog } from '../lib/tagmeta.svelte'
  import Sparkline from '../components/data/Sparkline.svelte'
  import Card from '../components/ui/Card.svelte'
  import PageHeader from '../components/ui/PageHeader.svelte'
  import Disclosure from '../components/ui/Disclosure.svelte'
  import EmptyState from '../components/ui/EmptyState.svelte'
  import QualityBadge from '../components/ui/QualityBadge.svelte'
  import StatusDot from '../components/ui/StatusDot.svelte'

  let { equipmentId }: { equipmentId: string } = $props()

  let status = $state<RuntimeStatus | null>(null)
  let alarm = $state<AlarmLookupView | null>(null)
  let alarmCode = $state<string | null>(null)

  const eq = $derived(live.live[equipmentId])
  const name = $derived(eq?.name ?? live.cardOf(equipmentId)?.name ?? equipmentId)
  const tags = $derived(sortTags(Object.keys(eq?.tags ?? {})))
  const groups = $derived.by(() => {
    const cont: string[] = []
    const disc: string[] = []
    const raw: string[] = []
    for (const t of tags) {
      const kind = eq?.tags[t]?.kind ?? tagCatalog.meta(t).kind
      if (kind === 'STATUS_RAW') raw.push(t)
      else if (kind === 'DISCRETE') disc.push(t)
      else cont.push(t)
    }
    return [
      { id: 'processo', title: 'Processo', tags: cont },
      { id: 'estado', title: 'Estado e alarmes', tags: disc },
      { id: 'brutos', title: 'Status brutos (sem decodificação sem fonte)', tags: raw },
    ].filter((g) => g.tags.length)
  })

  async function loadStatus(id: string): Promise<void> {
    try {
      const s = await api.status(id)
      if (id === equipmentId) status = s
    } catch {
      // o estado do Edge aparece no banner global
    }
  }

  $effect(() => {
    const id = equipmentId
    untrack(() => {
      void tagCatalog.ensure()
      void live.reconcileLive(id)
      void loadStatus(id)
    })
    const timer = window.setInterval(() => void loadStatus(id), 5000)
    return () => clearInterval(timer)
  })

  // código de alarme ativo: consulta o catálogo pela chave composta do perfil
  $effect(() => {
    const t = eq?.tags['alarm_code']
    const code = t && t.is_usable && t.value != null && t.value !== 0 ? String(Math.trunc(t.value)) : null
    if (code === alarmCode) return
    alarmCode = code
    alarm = null
    if (code) {
      const id = equipmentId
      api
        .alarmLookup(id, code)
        .then((r) => {
          if (id === equipmentId && alarmCode === code) alarm = r
        })
        .catch(() => undefined)
    }
  })

  function valueText(tag: string): string {
    const t = eq?.tags[tag]
    if (!t || t.value == null) return '—'
    const kind = t.kind ?? tagCatalog.meta(tag).kind
    if (kind === 'STATUS_RAW') return rawStatusText(t.value, tag === 'mdu_status' ? 4 : 8)
    if (kind === 'DISCRETE') return discreteText(tag, t.value)
    return fmtNumber(t.value, t.decimals)
  }
</script>

<section class="rt" data-testid="realtime">
  <PageHeader kicker={name} title="Tempo Real" lead="Cada variável com a qualidade e a idade da leitura.">
    {#snippet more()}
      <p>Aparecem todas as variáveis mapeadas. Valor antigo nunca aparece como atual: ele leva a idade ao lado.</p>
    {/snippet}
  </PageHeader>

  <Card padded testid="realtime-status">
    <dl class="status">
      <div>
        <dt>Conexão</dt>
        <dd>
          <StatusDot state={connectionTone(eq?.connection ?? status?.connection)} hollow={(eq?.connection ?? status?.connection) !== 'CONNECTED'} />
          {eq?.connection_pt ?? status?.connection_pt ?? '—'}
        </dd>
      </div>
      <div>
        <dt>Última leitura</dt>
        <dd class="num">{fmtWhen(eq?.last_read_utc ?? status?.last_read_utc ?? null, app.now)}</dd>
      </div>
      <div>
        <dt>Latência</dt>
        <dd class="num">{status?.latency_ms != null ? `${fmtNumber(status.latency_ms, 1)} ms` : '—'}</dd>
      </div>
      <div>
        <dt>Leituras por minuto</dt>
        <dd class="num">{status ? fmtNumber(status.samples_per_min, 0) : '—'}</dd>
      </div>
      <div>
        <dt>Falhas seguidas</dt>
        <dd class="num">{status ? status.consecutive_errors : '—'}</dd>
      </div>
      <div>
        <dt>Reconexões</dt>
        <dd class="num">{status ? status.reconnect_count : '—'}</dd>
      </div>
    </dl>
    {#if status?.detail_pt}<p class="detail">{status.detail_pt}</p>{/if}
  </Card>

  {#if !eq}
    <EmptyState title="Aguardando dados ao vivo" text="Conectando ao fluxo de tempo real do Forja Edge." />
  {:else if tags.length === 0}
    <EmptyState
      title="Nenhuma variável lida ainda"
      text="Quando a aquisição deste equipamento produzir leituras, elas aparecem aqui com qualidade e idade."
    />
  {:else}
    {#each groups as g (g.id)}
      <Card title={g.title} padded={false} testid={`realtime-group-${g.id}`}>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">Variável</th>
                <th scope="col" class="r">Valor</th>
                <th scope="col">Qualidade</th>
                <th scope="col">Idade</th>
                {#if g.id === 'processo'}<th scope="col" class="spark-col">Últimos pontos</th>{/if}
              </tr>
            </thead>
            <tbody>
              {#each g.tags as tag (tag)}
                {@const t = eq.tags[tag]}
                {@const age = live.ageOf(t, app.now)}
                <tr data-testid={`realtime-row-${tag}`} data-quality={t.quality}>
                  <th scope="row">
                    <span class="lbl">{t.label_pt !== tag ? t.label_pt : tagCatalog.meta(tag).label_pt}</span>
                    {#if t.explanation_pt}<span class="exp">{t.explanation_pt}</span>{/if}
                    {#if tag === 'alarm_code' && alarm}
                      <span class="alarm" data-catalogued={alarm.catalogued}>
                        {alarm.title_pt} · {alarm.qualifier_pt}
                      </span>
                    {/if}
                  </th>
                  <td class="r val num" class:stale={t.quality === 'STALE'} class:none={!t.is_usable && t.quality !== 'STALE'}>
                    {valueText(tag)}{#if t.unit && t.value != null && g.id === 'processo'}<span class="unit"> {t.unit}</span>{/if}
                    {#if t.reason_pt && !t.is_usable}<span class="why">{t.reason_pt}</span>{/if}
                  </td>
                  <td><QualityBadge quality={t.quality} qualityPt={t.quality_pt} ageS={age} reasonPt={t.reason_pt} /></td>
                  <td class="num age">{fmtAge(age)}</td>
                  {#if g.id === 'processo'}
                    <td class="spark-col">
                      <Sparkline points={live.seriesFor(equipmentId, tag)} faded={!t.is_usable} height={28} showWindow={false} label={`Mini-tendência de ${t.label_pt}`} />
                    </td>
                  {/if}
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </Card>
    {/each}

    <Disclosure summary="Detalhes técnicos" testid="realtime-tech">
      <div class="table-wrap">
        <table class="tech">
          <thead>
            <tr><th scope="col">Tag</th><th scope="col">Qualidade</th><th scope="col">Origem</th><th scope="col">Bruto (hex)</th><th scope="col">Horário (UTC)</th></tr>
          </thead>
          <tbody>
            {#each tags as tag (tag)}
              {@const t = eq.tags[tag]}
              <tr>
                <td class="num">{tag}</td>
                <td class="num">{t.quality}</td>
                <td class="num src">{t.source || '—'}</td>
                <td class="num">{t.raw_hex ?? '—'}</td>
                <td class="num">{t.ts_utc ?? '—'}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </Disclosure>
  {/if}
</section>

<style>
  .rt { display: flex; flex-direction: column; gap: var(--sp-5); min-width: 0; }
  .status {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: var(--sp-3) var(--sp-5);
    margin: 0;
  }
  .status dt { color: var(--text-3); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .status dd {
    display: flex;
    align-items: center;
    gap: var(--sp-2);
    margin: 2px 0 0;
    color: var(--text-1);
    font: 500 var(--fs-body) / var(--lh-body) var(--font-ui);
  }
  .status dd.num { font-family: var(--font-mono); }
  .detail { margin: var(--sp-3) 0 0; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }

  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  th, td { padding: var(--sp-3) var(--sp-4); border-bottom: 1px solid var(--border-1); text-align: left; vertical-align: middle; }
  tbody tr:last-child th, tbody tr:last-child td { border-bottom: 0; }
  thead th { color: var(--text-3); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  tbody th { font-weight: 400; min-width: 180px; }
  .lbl { display: block; color: var(--text-1); font-weight: 500; }
  .exp { display: block; color: var(--text-3); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); max-width: 46ch; }
  .alarm { display: block; margin-top: 2px; color: var(--st-warn); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .r { text-align: right; }
  .val { color: var(--text-1); font-size: 18px; font-weight: 600; white-space: nowrap; }
  .val.stale { color: var(--q-stale); }
  .val.none { color: var(--text-3); }
  .unit { color: var(--text-3); font-size: var(--fs-mono-sm); font-weight: 400; }
  .why { display: block; color: var(--text-3); font: 400 var(--fs-caption) / var(--lh-caption) var(--font-ui); white-space: normal; }
  .age { color: var(--text-2); white-space: nowrap; font-size: var(--fs-mono-sm); }
  .spark-col { width: 180px; min-width: 140px; }
  .tech td { font-size: var(--fs-mono-sm); color: var(--text-2); }
  .src { overflow-wrap: anywhere; }
  @media (max-width: 767px) {
    th, td { padding: var(--sp-2) var(--sp-3); }
    .spark-col { display: none; }
    tbody th { min-width: 140px; }
  }
</style>
