<script lang="ts">
  /** Sistema › Backup: rotina automática, backup agora (bancos + configuração), conferência e o
   *  comando de restauração de cada backup (restaurar exige o serviço parado). */
  import { onMount } from 'svelte'
  import Check from '@lucide/svelte/icons/check'
  import Copy from '@lucide/svelte/icons/copy'
  import DatabaseBackup from '@lucide/svelte/icons/database-backup'
  import { errorMessage } from '../lib/api'
  import { RESPONSIBLE_PATTERN, rememberResponsible, rememberedResponsible } from '../lib/equipment'
  import { fmtDateTime, fmtWhen } from '../lib/format'
  import { fmtBytes, reportsApi, type BackupItem, type BackupList, type VerifyResult } from '../lib/reports'
  import { app } from '../lib/state.svelte'
  import Badge from '../components/ui/Badge.svelte'
  import Card from '../components/ui/Card.svelte'
  import PageHeader from '../components/ui/PageHeader.svelte'
  import Disclosure from '../components/ui/Disclosure.svelte'
  import EmptyState from '../components/ui/EmptyState.svelte'

  let data = $state<BackupList | null>(null)
  let error = $state<string | null>(null)
  let responsible = $state('')
  let reason = $state('')
  let creating = $state(false)
  let createError = $state<string | null>(null)
  let created = $state<string | null>(null)
  let verifying = $state<string | null>(null)
  let verified = $state<Record<string, VerifyResult>>({})
  let copied = $state<string | null>(null)

  async function load(): Promise<void> {
    try {
      data = await reportsApi.backups()
      error = null
    } catch (err) {
      error = errorMessage(err)
    }
  }

  onMount(() => {
    responsible = rememberedResponsible()
    void load()
  })

  async function createNow(): Promise<void> {
    createError = null
    if (!RESPONSIBLE_PATTERN.test(responsible.trim())) {
      createError = 'Informe o responsável (letras, números, espaço, ponto, @ ou hífen).'
      return
    }
    creating = true
    try {
      const item = await reportsApi.createBackup(responsible.trim(), reason.trim())
      rememberResponsible(responsible.trim())
      created = item.name
      reason = ''
      await load()
    } catch (err) {
      createError = errorMessage(err)
    } finally {
      creating = false
    }
  }

  async function verify(item: BackupItem): Promise<void> {
    verifying = item.name
    try {
      verified = { ...verified, [item.name]: await reportsApi.verifyBackup(item.name) }
    } catch (err) {
      verified = { ...verified, [item.name]: { name: item.name, ok: false, message_pt: errorMessage(err) } }
    } finally {
      verifying = null
    }
  }

  async function copy(text: string, key: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(text)
      copied = key
      setTimeout(() => {
        if (copied === key) copied = null
      }, 1800)
    } catch {
      copied = null
    }
  }

  const KIND_PT: Record<string, string> = { historian: 'histórico', core: 'registros', config: 'configuração' }
</script>

<section class="bk" data-testid="backup">
  <PageHeader kicker="Sistema" title="Backup" lead="Cópia dos bancos e da configuração, com conferência de integridade.">
    {#snippet more()}
      <p>O backup lê os bancos com o serviço funcionando. Restaurar exige o serviço parado.</p>
    {/snippet}
  </PageHeader>

  {#if error && !data}
    <EmptyState title="Não foi possível carregar os backups" text={error} />
  {:else if !data}
    <div class="sk" aria-busy="true" aria-label="Carregando backups"></div>
  {:else}
    <div class="top">
      <Card title="Rotina automática" kicker="config/forja.yaml" testid="backup-schedule">
        {#if data.auto}
          <p class="big"><Badge tone="ok">Ligada</Badge> todo dia às <span class="num">{data.schedule}</span></p>
          <p class="muted">Guarda os {data.keep_last} backups mais recentes; os mais antigos são apagados.</p>
          {#if data.next_run_utc}<p class="muted">Próximo: {fmtDateTime(data.next_run_utc)}</p>{/if}
        {:else}
          <p class="big"><Badge tone="warn">Desligada</Badge></p>
          <p class="muted">Ligue em config/forja.yaml (backup.auto) e reinicie o serviço.</p>
        {/if}
        <p class="muted">Pasta: <span class="mono path">{data.folder}</span></p>
      </Card>
      <Card title="Backup agora" kicker="bancos e configuração" testid="backup-create">
        <label class="field"><span class="label">Responsável</span><input bind:value={responsible} maxlength="64" autocomplete="name" data-testid="backup-responsible" /></label>
        <label class="field"><span class="label">Motivo (opcional)</span><input bind:value={reason} maxlength="2000" placeholder="ex.: antes da atualização" /></label>
        {#if createError}<p class="err" role="alert">{createError}</p>{/if}
        <button class="btn primary" type="button" disabled={creating} onclick={createNow} data-testid="backup-create-submit">
          <DatabaseBackup size={16} aria-hidden="true" /> {creating ? 'Copiando e conferindo…' : 'Fazer backup agora'}
        </button>
      </Card>
    </div>

    <Card title="Backups guardados" kicker={`${data.count} na pasta`} testid="backup-list">
      {#if data.backups.length === 0}
        <EmptyState inline title="Nenhum backup ainda" text="Faça o primeiro agora ou aguarde a rotina automática." />
      {:else}
        <ul class="list">
          {#each data.backups as b, i (b.name)}
            <li class="item" class:fresh={b.name === created} data-testid="backup-{b.name}" style:--i={i}>
              <div class="item-head">
                <p class="item-title">
                  {#if b.created_at_utc}{fmtDateTime(b.created_at_utc)}{:else}{b.name}{/if}
                  {#if b.created_at_utc}<span class="muted">· {fmtWhen(b.created_at_utc, app.now)}</span>{/if}
                </p>
                <span class="badges">
                  {#if !b.valid}<Badge tone="crit">Manifesto ilegível</Badge>{/if}
                  {#if b.has_config}<Badge tone="info">com configuração</Badge>{/if}
                  {#if verified[b.name]}
                    <Badge tone={verified[b.name].ok ? 'ok' : 'crit'}>{verified[b.name].ok ? 'Íntegro' : 'Com problema'}</Badge>
                  {/if}
                </span>
              </div>
              <p class="muted">
                {fmtBytes(b.size_bytes)}
                {#if b.files}· {b.files.map((f) => KIND_PT[f.kind] ?? f.kind).join(', ')}{/if}
                {#if b.app_version}· versão {b.app_version}{/if}
              </p>
              {#if b.error_pt}<p class="err">{b.error_pt}</p>{/if}
              {#if verified[b.name]}<p class="muted" data-testid="backup-verify-result">{verified[b.name].message_pt}</p>{/if}
              <div class="actions">
                <button class="btn ghost" type="button" disabled={verifying !== null || !b.valid} onclick={() => verify(b)} data-testid="backup-verify-{b.name}">
                  {verifying === b.name ? 'Conferindo…' : 'Conferir integridade'}
                </button>
                <button class="btn ghost" type="button" onclick={() => copy(b.path, `p-${b.name}`)}>
                  {#if copied === `p-${b.name}`}<Check size={16} aria-hidden="true" /> Copiado{:else}<Copy size={16} aria-hidden="true" /> Copiar caminho da pasta{/if}
                </button>
              </div>
              <Disclosure summary="Como restaurar este backup" size="sm">
                <p class="muted">{data.restore_note_pt}</p>
                <pre class="cmd">{b.restore_command}</pre>
                <button class="btn ghost" type="button" onclick={() => copy(b.restore_command, `c-${b.name}`)}>
                  {copied === `c-${b.name}` ? 'Comando copiado' : 'Copiar comando'}
                </button>
                {#if b.has_config}
                  <p class="muted">Para trazer de volta também a configuração (a atual fica guardada antes):</p>
                  <pre class="cmd">{b.restore_config_command}</pre>
                {/if}
              </Disclosure>
            </li>
          {/each}
        </ul>
      {/if}
    </Card>
  {/if}
</section>

<style>
  .bk { display: flex; flex-direction: column; gap: var(--sp-5); }
  .top { display: grid; gap: var(--sp-4); grid-template-columns: 1fr; }
  @media (min-width: 1024px) { .top { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
  .big { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-2); margin: 0 0 var(--sp-2); color: var(--text-1); font: 600 var(--fs-h3) / var(--lh-h3) var(--font-ui); }
  .num { font-family: var(--font-mono); }
  .muted { margin: var(--sp-1) 0 0; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); overflow-wrap: anywhere; }
  .mono { font-family: var(--font-mono); }
  .path { color: var(--text-1); }
  .field { display: flex; flex-direction: column; gap: var(--sp-1); margin-bottom: var(--sp-3); }
  input {
    width: 100%;
    min-height: var(--touch);
    padding: var(--sp-2);
    border: 1px solid var(--border-input);
    border-radius: var(--r-2);
    background: var(--surf-2);
    color: var(--text-1);
    font: 16px / 1.3 var(--font-ui);
  }
  input:focus-visible { outline: none; box-shadow: var(--focus); }
  .err { margin: 0 0 var(--sp-2); color: var(--st-crit); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .list { display: flex; flex-direction: column; gap: var(--sp-3); margin: 0; padding: 0; list-style: none; }
  .item {
    display: flex;
    flex-direction: column;
    gap: var(--sp-2);
    padding: var(--sp-3) var(--sp-4);
    border: 1px solid var(--border-1);
    border-radius: var(--r-3);
    background: var(--surf-2);
    min-width: 0;
    animation: rise var(--dur-screen) var(--ease-out) backwards;
    animation-delay: calc(var(--i, 0) * var(--stagger));
  }
  .item.fresh { border-color: var(--st-ok); box-shadow: inset 3px 0 0 var(--st-ok); }
  @keyframes rise {
    from { opacity: 0; transform: translateY(6px); }
    to { opacity: 1; transform: none; }
  }
  .item-head { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--sp-2); }
  .item-title { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--sp-2); margin: 0; color: var(--text-1); font: 600 var(--fs-body) / var(--lh-body) var(--font-ui); }
  .badges { display: flex; flex-wrap: wrap; gap: var(--sp-2); }
  .actions { display: flex; flex-wrap: wrap; gap: var(--sp-2); }
  .cmd {
    margin: var(--sp-2) 0;
    padding: var(--sp-2) var(--sp-3);
    border-radius: var(--r-2);
    background: var(--bg-0);
    color: var(--text-1);
    font: var(--fs-mono-sm) / var(--lh-mono-sm) var(--font-mono);
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--sp-2);
    min-height: var(--touch);
    padding: 0 var(--sp-4);
    border-radius: var(--r-3);
    font: 600 var(--fs-body) / 1.2 var(--font-ui);
    cursor: pointer;
    transition: transform var(--dur-micro) var(--ease-std), background-color var(--dur-micro) var(--ease-std);
  }
  .btn:active:not(:disabled) { transform: scale(0.97); }
  .btn:disabled { opacity: 0.55; cursor: not-allowed; }
  .btn.primary { border: 1px solid var(--accent); background: var(--accent); color: var(--on-accent); }
  .btn.ghost { border: 1px solid var(--border-2); background: var(--surf-1); color: var(--text-1); }
  .btn.ghost:hover:not(:disabled) { background: var(--surf-3); }
  .btn:focus-visible { outline: none; box-shadow: var(--focus); }
  .sk { height: 220px; border-radius: var(--r-4); background: var(--surf-2); opacity: 0.6; }
</style>
