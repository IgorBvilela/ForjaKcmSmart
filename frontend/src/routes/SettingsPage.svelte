<script lang="ts">
  /** Sistema › Configuração: o que o Edge está usando (forja.yaml) e onde fica cada pasta.
   *  Só leitura; para mudar, edita-se o arquivo e reinicia o serviço. */
  import { onMount } from 'svelte'
  import { errorMessage, request } from '../lib/api'
  import Card from '../components/ui/Card.svelte'
  import PageHeader from '../components/ui/PageHeader.svelte'
  import EmptyState from '../components/ui/EmptyState.svelte'

  interface Settings {
    edge: { name: string; bind_host: string; bind_port: number; timezone: string }
    historian: Record<string, number | boolean | null>
    events: { pre_window_s: number; post_window_s: number; buffer_s: number }
    backup: { auto: boolean; schedule: string; keep_last: number }
    logging: { level: string; rotate_mb: number; keep: number }
    paths: Record<string, string>
    interface_url: string
    equipments: number
    version: string
    note_pt: string
    users_note_pt: string
  }

  let data = $state<Settings | null>(null)
  let error = $state<string | null>(null)

  onMount(async () => {
    try {
      data = await request<Settings>('/system/settings')
    } catch (err) {
      error = errorMessage(err)
    }
  })

  const PATH_PT: Record<string, string> = {
    home: 'Pasta de dados',
    config: 'Configuração',
    knowledge: 'Base de conhecimento',
    data: 'Bancos',
    logs: 'Logs',
    backups: 'Backups',
  }
  const days = (v: number | boolean | null | undefined) =>
    v == null ? 'sem limite' : typeof v === 'number' ? `${v} dia(s)` : String(v)
</script>

<section class="set" data-testid="settings">
  <PageHeader kicker="Sistema" title="Configuração" lead="O que este Edge usa agora e onde fica cada pasta." />

  {#if error && !data}
    <EmptyState title="Não foi possível carregar a configuração" text={error} />
  {:else if !data}
    <div class="sk" aria-busy="true" aria-label="Carregando configuração"></div>
  {:else}
    <p class="note" data-testid="settings-note">{data.note_pt}</p>
    <div class="cards">
      <Card title="Edge" testid="settings-edge">
        <dl class="dl">
          <div><dt>Nome</dt><dd>{data.edge.name}</dd></div>
          <div><dt>Endereço da interface</dt><dd class="mono">{data.interface_url}</dd></div>
          <div><dt>Fuso da planta</dt><dd>{data.edge.timezone}</dd></div>
          <div><dt>Equipamentos</dt><dd>{data.equipments}</dd></div>
          <div><dt>Versão</dt><dd class="mono">{data.version}</dd></div>
        </dl>
      </Card>
      <Card title="Histórico" testid="settings-historian">
        <dl class="dl">
          <div><dt>Leituras brutas</dt><dd>{days(data.historian.raw_retention_days)}</dd></div>
          <div><dt>Brutas do simulador</dt><dd>{days(data.historian.raw_simulated_retention_days)}</dd></div>
          <div><dt>Resumo por minuto</dt><dd>{days(data.historian.rollup_1m_retention_days)}</dd></div>
          <div><dt>Resumo por hora</dt><dd>{days(data.historian.rollup_1h_retention_days)}</dd></div>
          <div><dt>Leitura forçada</dt><dd>a cada {data.historian.forced_sample_every_s} s</dd></div>
          <div><dt>Limite do banco</dt><dd>{data.historian.max_historian_gb} GB</dd></div>
        </dl>
      </Card>
      <Card title="Eventos e backup" testid="settings-events">
        <dl class="dl">
          <div><dt>Janela antes do evento</dt><dd>{data.events.pre_window_s} s</dd></div>
          <div><dt>Janela depois</dt><dd>{data.events.post_window_s} s</dd></div>
          <div><dt>Backup automático</dt><dd>{data.backup.auto ? `todo dia às ${data.backup.schedule}, guarda ${data.backup.keep_last}` : 'desligado'}</dd></div>
          <div><dt>Log</dt><dd>{data.logging.level}, {data.logging.rotate_mb} MB × {data.logging.keep}</dd></div>
        </dl>
      </Card>
      <Card title="Pastas" testid="settings-paths">
        <dl class="dl">
          {#each Object.entries(data.paths) as [k, v] (k)}
            <div><dt>{PATH_PT[k] ?? k}</dt><dd class="mono">{v}</dd></div>
          {/each}
        </dl>
      </Card>
    </div>
    <Card title="Usuários e permissões" testid="settings-users">
      <p class="text">{data.users_note_pt}</p>
    </Card>
  {/if}
</section>

<style>
  .set { display: flex; flex-direction: column; gap: var(--sp-5); }
  .note { margin: 0; padding: var(--sp-3) var(--sp-4); border: 1px solid var(--st-info); border-radius: var(--r-3); background: var(--st-info-bg); color: var(--text-1); font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  .cards { display: grid; gap: var(--sp-4); grid-template-columns: 1fr; }
  @media (min-width: 1024px) { .cards { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
  .dl { display: flex; flex-direction: column; margin: 0; }
  .dl > div {
    display: grid;
    grid-template-columns: minmax(9em, 40%) minmax(0, 1fr);
    gap: var(--sp-3);
    padding: var(--sp-2) 0;
    border-top: 1px solid var(--border-1);
  }
  .dl > div:first-child { border-top: 0; }
  dt { color: var(--text-2); font: 500 var(--fs-caption) / var(--lh-body) var(--font-ui); }
  dd { margin: 0; color: var(--text-1); font: var(--fs-body) / var(--lh-body) var(--font-ui); overflow-wrap: anywhere; }
  .mono { font-family: var(--font-mono); font-size: var(--fs-mono-sm); }
  .text { margin: 0; color: var(--text-1); font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  .sk { height: 220px; border-radius: var(--r-4); background: var(--surf-2); opacity: 0.6; }
</style>
