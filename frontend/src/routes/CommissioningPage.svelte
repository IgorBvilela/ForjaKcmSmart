<script lang="ts">
  /** KCM › Comissionamento: registro da visita de campo. Cabeçalho (o que foi encontrado no
   *  equipamento) e conferências valor Forja x valor na tela do KCM, uma a uma. A validação só
   *  existe depois de feita e registrada aqui; conferência gravada não muda. */
  import { untrack } from 'svelte'
  import ClipboardCheck from '@lucide/svelte/icons/clipboard-check'
  import Download from '@lucide/svelte/icons/download'
  import Printer from '@lucide/svelte/icons/printer'
  import RefreshCw from '@lucide/svelte/icons/refresh-cw'
  import { api, errorMessage, type Quality } from '../lib/api'
  import { commApi, type CommView } from '../lib/comm'
  import {
    commissioningApi,
    parseNumberPt,
    RESULT_PT,
    type CheckResult,
    type CommissioningHeader,
    type SessionDetail,
    type SessionList,
  } from '../lib/commissioning'
  import { discreteText, rawStatusText } from '../lib/discrete'
  import { fmtAge, fmtDateTime, fmtNumber } from '../lib/format'
  import { live } from '../lib/live.svelte'
  import { sortTags, tagCatalog } from '../lib/tagmeta.svelte'
  import Card from '../components/ui/Card.svelte'
  import PageHeader from '../components/ui/PageHeader.svelte'
  import EmptyState from '../components/ui/EmptyState.svelte'
  import QualityBadge from '../components/ui/QualityBadge.svelte'

  let { equipmentId }: { equipmentId: string } = $props()

  interface Reading {
    value: number | null
    value_pt: string
    quality: Quality | null
    raw_hex: string | null
    address: string
    origin: string
  }
  interface Draft {
    kcm: string
    result: CheckResult
    note: string
  }

  const LS_USER = 'forja.responsavel'
  function readUser(): string {
    try {
      return localStorage.getItem(LS_USER) ?? ''
    } catch {
      return ''
    }
  }
  function today(): string {
    const d = new Date()
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  }

  let list = $state<SessionList | null>(null)
  let detail = $state<SessionDetail | null>(null)
  let comm = $state<CommView | null>(null)
  let form = $state<CommissioningHeader | null>(null)
  let readings = $state<Record<string, Reading>>({})
  let drafts = $state<Record<string, Draft>>({})
  let conclusion = $state('')
  let countersAfter = $state('')
  let busy = $state('')
  let notice = $state<{ tone: 'ok' | 'warn' | 'crit'; text: string } | null>(null)
  let error = $state<string | null>(null)

  const name = $derived(live.cardOf(equipmentId)?.name ?? equipmentId)
  const open = $derived(detail?.session.status === 'OPEN')
  const tags = $derived.by(() => {
    const suggested = list?.suggested_tags ?? []
    const mapped = (comm?.mapping.entries ?? [])
      .filter((e) => e.protocol_address !== 'UNKNOWN')
      .map((e) => e.semantic_tag)
    return sortTags(Array.from(new Set([...suggested, ...mapped])))
  })

  function blankHeader(prefill: Partial<CommissioningHeader>): CommissioningHeader {
    return {
      technician: readUser(),
      authorized_by: '',
      visit_date: today(),
      protocol_found: prefill.protocol_found ?? 'UNKNOWN',
      kcm_software_version: prefill.kcm_software_version ?? 'UNKNOWN',
      host_interface: prefill.host_interface ?? 'UNKNOWN',
      ip: prefill.ip ?? 'UNKNOWN',
      subnet_mask: prefill.subnet_mask ?? 'UNKNOWN',
      gateway: prefill.gateway ?? 'UNKNOWN',
      mapping_id: prefill.mapping_id ?? 'UNKNOWN',
      mapping_version: prefill.mapping_version ?? null,
      host_counters_before: '',
      host_counters_after: '',
      notes_pt: '',
    }
  }

  async function load(id: string, sessionId?: string): Promise<void> {
    busy = 'load'
    try {
      await tagCatalog.ensure()
      const [l, c] = await Promise.all([commissioningApi.list(id), commApi.view(id)])
      if (id !== equipmentId) return
      list = l
      comm = c
      const chosen = sessionId ?? l.sessions.find((s) => s.status === 'OPEN')?.id ?? null
      detail = chosen ? await commissioningApi.get(chosen) : null
      form = detail ? { ...detail.session.header } : blankHeader(l.prefill)
      error = null
    } catch (err) {
      if (id === equipmentId) error = errorMessage(err)
    } finally {
      busy = ''
    }
  }

  $effect(() => {
    const id = equipmentId
    untrack(() => void load(id))
  })

  // um rascunho por variável do roteiro (criado em efeito, nunca durante a renderização)
  $effect(() => {
    for (const t of tags) {
      if (!untrack(() => drafts[t])) drafts[t] = { kcm: '', result: 'MATCH', note: '' }
    }
  })

  function draftOf(tag: string): Draft {
    return (drafts[tag] ??= { kcm: '', result: 'MATCH', note: '' })
  }

  function rememberUser(user: string): void {
    try {
      localStorage.setItem(LS_USER, user.trim())
    } catch {
      // armazenamento indisponível
    }
  }

  async function openSession(): Promise<void> {
    if (!form) return
    busy = 'open'
    notice = null
    try {
      rememberUser(form.technician)
      detail = await commissioningApi.open(equipmentId, form)
      form = { ...detail.session.header }
      list = await commissioningApi.list(equipmentId)
      notice = { tone: 'ok', text: 'Sessão aberta. Registre cada conferência abaixo.' }
    } catch (err) {
      notice = { tone: 'crit', text: errorMessage(err) }
    } finally {
      busy = ''
    }
  }

  async function saveHeader(): Promise<void> {
    if (!form || !detail) return
    busy = 'header'
    try {
      detail = await commissioningApi.header(detail.session.id, form, form.technician)
      notice = { tone: 'ok', text: 'Cabeçalho salvo.' }
    } catch (err) {
      notice = { tone: 'crit', text: errorMessage(err) }
    } finally {
      busy = ''
    }
  }

  /** Coleta ativa: usa o valor que a coleta já leu (nenhuma conexão extra). Senão: teste somente
   *  leitura com a configuração SALVA. */
  async function readNow(): Promise<void> {
    if (!comm) return
    busy = 'read'
    notice = null
    try {
      const next: Record<string, Reading> = {}
      if (comm.collection.enabled) {
        const lv = await api.live(equipmentId)
        for (const t of lv.tags) {
          const shown =
            t.value == null
              ? 'sem valor'
              : t.kind === 'STATUS_RAW'
                ? rawStatusText(t.value, t.tag === 'mdu_status' ? 4 : 8)
                : t.kind === 'DISCRETE'
                  ? discreteText(t.tag, t.value)
                  : fmtNumber(t.value, t.decimals) + (t.unit ? ` ${t.unit}` : '')
          next[t.tag] = {
            value: t.value,
            value_pt: shown,
            quality: t.quality,
            raw_hex: t.raw_hex,
            address: '',
            origin: `coleta (${fmtAge(t.age_s)})`,
          }
        }
      } else {
        const r = await commApi.testRead(comm.profile, comm.mapping, form?.technician ?? '')
        for (const row of r.detail.tags) {
          next[row.tag] = {
            value: row.value,
            value_pt: row.value_pt ?? 'sem valor',
            quality: row.quality,
            raw_hex: row.raw_hex,
            address: row.address_pt,
            origin: 'teste somente leitura',
          }
        }
        if (!r.success) notice = { tone: 'warn', text: `Teste sem leitura: ${r.final_pt ?? r.final}${r.error_pt ? ` (${r.error_pt})` : ''}` }
      }
      readings = next
    } catch (err) {
      notice = { tone: 'crit', text: errorMessage(err) }
    } finally {
      busy = ''
    }
  }

  async function register(tag: string): Promise<void> {
    if (!detail || !form) return
    const d = draftOf(tag)
    const r = readings[tag]
    const kcmNumber = parseNumberPt(d.kcm)
    busy = `check:${tag}`
    try {
      await commissioningApi.check(detail.session.id, {
        tag,
        address_text: r?.address ?? '',
        forja_value: r?.value ?? null,
        forja_raw_hex: r?.raw_hex ?? null,
        forja_quality: r?.quality ?? null,
        kcm_value: kcmNumber,
        kcm_text: kcmNumber == null ? d.kcm.trim() : '',
        result: d.result,
        note_pt: d.note.trim(),
        technician: form.technician.trim() || 'não informado',
      })
      detail = await commissioningApi.get(detail.session.id)
      drafts[tag] = { kcm: '', result: 'MATCH', note: '' }
      notice = { tone: 'ok', text: `${tagCatalog.meta(tag).label_pt}: conferência registrada.` }
    } catch (err) {
      notice = { tone: 'crit', text: errorMessage(err) }
    } finally {
      busy = ''
    }
  }

  async function closeSession(): Promise<void> {
    if (!detail || !form || !conclusion.trim()) return
    busy = 'close'
    try {
      detail = await commissioningApi.close(detail.session.id, conclusion.trim(), countersAfter.trim(), form.technician.trim() || 'não informado')
      list = await commissioningApi.list(equipmentId)
      notice = { tone: 'ok', text: 'Sessão encerrada. O relatório pode ser exportado ou impresso.' }
    } catch (err) {
      notice = { tone: 'crit', text: errorMessage(err) }
    } finally {
      busy = ''
    }
  }

  function u(v: string): string {
    return v === 'UNKNOWN' ? '' : v
  }
  function setU(key: keyof CommissioningHeader, raw: string): void {
    if (!form) return
    ;(form as unknown as Record<string, unknown>)[key] = raw.trim() === '' ? 'UNKNOWN' : raw
  }

  const HEADER_FIELDS: Array<{ key: keyof CommissioningHeader; label: string; unknown?: boolean; placeholder?: string }> = [
    { key: 'technician', label: 'Técnico' },
    { key: 'authorized_by', label: 'Autorizado por (responsável da planta)' },
    { key: 'protocol_found', label: 'Protocolo encontrado', unknown: true, placeholder: 'como aparece no KCM' },
    { key: 'kcm_software_version', label: 'Versão do software do KCM', unknown: true },
    { key: 'host_interface', label: 'Interface Host/Anybus (modelo, part number)', unknown: true },
    { key: 'ip', label: 'IP', unknown: true },
    { key: 'subnet_mask', label: 'Máscara', unknown: true },
    { key: 'gateway', label: 'Gateway', unknown: true },
    { key: 'host_counters_before', label: 'Contadores Host antes de conectar' },
  ]
</script>

<section class="cm" data-testid="commissioning">
  <PageHeader kicker={name} title="Comissionamento" lead="Registro da visita de campo, com cada valor conferido na tela do KCM.">
    {#snippet more()}
      <p>O registro guarda o que foi encontrado no equipamento. A validação só existe depois de feita e registrada aqui.</p>
    {/snippet}
    {#snippet actions()}
      {#if detail}
        <div class="actions no-print">
          <a class="btn ghost" href={commissioningApi.csvUrl(detail.session.id)} download data-testid="cm-export">
            <Download size={16} aria-hidden="true" /> Exportar CSV
          </a>
          <button type="button" class="btn ghost" onclick={() => window.print()} data-testid="cm-print">
            <Printer size={16} aria-hidden="true" /> Imprimir relatório
          </button>
        </div>
      {/if}
    {/snippet}
  </PageHeader>

  {#if notice}<p class="notice no-print" data-tone={notice.tone} role="status" data-testid="cm-notice">{notice.text}</p>{/if}

  {#if error}
    <EmptyState title="Não foi possível carregar o comissionamento" text={error} />
  {:else if !list || !form}
    <div class="sk" aria-busy="true" aria-label="Carregando"></div>
  {:else}
    <div class="layout">
      <div class="main">
        <Card title={detail ? `Visita de ${detail.session.header.visit_date} · ${detail.status_pt}` : 'Abrir sessão de comissionamento'} testid="cm-header">
          <div class="grid">
            <label>Data da visita
              <input type="date" bind:value={form.visit_date} disabled={!!detail && !open} />
            </label>
            {#each HEADER_FIELDS as f (f.key)}
              <label>{f.label}
                {#if f.unknown}
                  <input type="text" maxlength="200" placeholder={f.placeholder ?? 'não identificado'} value={u(String(form[f.key] ?? ''))} oninput={(e) => setU(f.key, e.currentTarget.value)} disabled={!!detail && !open} data-testid={`cm-${f.key}`} />
                {:else}
                  <input type="text" maxlength="200" value={String(form[f.key] ?? '')} oninput={(e) => form && ((form as unknown as Record<string, unknown>)[f.key] = e.currentTarget.value)} disabled={!!detail && !open} data-testid={`cm-${f.key}`} />
                {/if}
              </label>
            {/each}
            <label class="wide">Observações
              <textarea rows="3" maxlength="4000" bind:value={form.notes_pt} disabled={!!detail && !open}></textarea>
            </label>
          </div>
          <div class="row no-print">
            {#if !detail}
              <button type="button" class="btn primary" disabled={busy !== '' || !form.technician.trim()} onclick={openSession} data-testid="cm-open">
                <ClipboardCheck size={18} aria-hidden="true" /> Abrir sessão
              </button>
            {:else if open}
              <button type="button" class="btn ghost" disabled={busy !== ''} onclick={saveHeader} data-testid="cm-save-header">Salvar cabeçalho</button>
            {/if}
          </div>
        </Card>

        {#if detail}
          <Card title="Conferências" testid="cm-checks">
            {#if open}
              <div class="row no-print">
                <button type="button" class="btn primary" disabled={busy !== '' || !comm} onclick={readNow} data-testid="cm-read">
                  <RefreshCw size={18} aria-hidden="true" /> Ler valores agora (somente leitura)
                </button>
                <p class="hint">
                  {comm?.collection.enabled
                    ? 'Coleta ativa: usa o último valor lido pela coleta, sem abrir conexão extra.'
                    : 'Coleta pausada: faz um teste somente leitura com a configuração salva.'}
                </p>
              </div>
              <div class="to-check no-print">
                {#each tags as tag (tag)}
                  {@const r = readings[tag]}
                  {@const d = drafts[tag]}
                  {@const done = detail.covered_tags.includes(tag)}
                  {#if d}
                  <article class="item" data-testid={`cm-item-${tag}`} data-done={done}>
                    <header>
                      <b>{tagCatalog.meta(tag).label_pt}</b>
                      {#if done}<span class="done">já registrada</span>{/if}
                    </header>
                    <p class="forja">
                      Forja: <b class="num">{r ? r.value_pt : '—'}</b>
                      {#if r?.quality}<QualityBadge quality={r.quality} />{/if}
                      {#if r}<small>{r.origin}{r.address ? ` · ${r.address}` : ''}</small>{/if}
                    </p>
                    <div class="fields">
                      <label>Valor na tela do KCM
                        <input type="text" inputmode="decimal" placeholder="valor no KCM" bind:value={d.kcm} data-testid={`cm-kcm-${tag}`} />
                      </label>
                      <label>Resultado
                        <select bind:value={d.result} data-testid={`cm-result-${tag}`}>
                          {#each Object.entries(RESULT_PT) as [value, text] (value)}<option {value}>{text}</option>{/each}
                        </select>
                      </label>
                      <label class="wide">Observação
                        <input type="text" maxlength="500" bind:value={d.note} />
                      </label>
                    </div>
                    <button type="button" class="btn ghost" disabled={busy !== ''} onclick={() => register(tag)} data-testid={`cm-register-${tag}`}>
                      Registrar conferência
                    </button>
                  </article>
                  {/if}
                {/each}
              </div>
            {/if}

            {#if detail.checks.length}
              <div class="table-wrap">
                <table class="resp" data-testid="cm-table">
                  <thead>
                    <tr>
                      <th scope="col">Variável</th>
                      <th scope="col">Instante</th>
                      <th scope="col" class="r">Forja</th>
                      <th scope="col" class="r">KCM</th>
                      <th scope="col" class="r">Diferença</th>
                      <th scope="col">Resultado</th>
                      <th scope="col">Observação</th>
                    </tr>
                  </thead>
                  <tbody>
                    {#each detail.checks as c (c.id)}
                      <tr data-result={c.result}>
                        <th scope="row">{c.label_pt}{#if c.unit}<span class="u">{c.unit}</span>{/if}</th>
                        <td class="num" data-label="Instante">{fmtDateTime(c.ts_utc)}</td>
                        <td class="r num" data-label="Forja">{fmtNumber(c.forja_value, tagCatalog.meta(c.tag).decimals)}</td>
                        <td class="r num" data-label="KCM">{c.kcm_value != null ? fmtNumber(c.kcm_value, tagCatalog.meta(c.tag).decimals) : c.kcm_text || '—'}</td>
                        <td class="r num" data-label="Diferença">{fmtNumber(c.difference, tagCatalog.meta(c.tag).decimals + 1)}</td>
                        <td data-label="Resultado"><span class="res" data-result={c.result}>{c.result_pt}</span></td>
                        <td data-label="Observação">{c.note_pt || '—'}</td>
                      </tr>
                    {/each}
                  </tbody>
                </table>
              </div>
              <p class="hint">
                Confere {detail.summary.MATCH} · Diverge {detail.summary.MISMATCH} · Não exposta
                {detail.summary.NOT_EXPOSED} · Não conferida {detail.summary.NOT_CHECKED}
              </p>
            {:else}
              <p class="hint">Nenhuma conferência registrada ainda.</p>
            {/if}
          </Card>

          <Card title={open ? 'Encerrar sessão' : 'Conclusão'} testid="cm-close">
            {#if open}
              <label>Contadores Host depois de conectar
                <input type="text" maxlength="500" placeholder="anote os mesmos contadores do início" bind:value={countersAfter} />
              </label>
              <label>Conclusão do técnico
                <textarea rows="3" maxlength="4000" bind:value={conclusion} data-testid="cm-conclusion"></textarea>
              </label>
              <button type="button" class="btn primary no-print" disabled={busy !== '' || !conclusion.trim()} onclick={closeSession} data-testid="cm-finish">
                Encerrar sessão
              </button>
              <p class="hint">Sessão encerrada não muda mais: vira o registro da visita.</p>
            {:else}
              <p class="conclusion">{detail.session.conclusion_pt}</p>
              <p class="hint">Contadores Host: antes "{detail.session.header.host_counters_before || '—'}", depois "{detail.session.header.host_counters_after || '—'}".</p>
            {/if}
            <div class="print-only signatures">
              <p>Técnico: ______________________________</p>
              <p>Responsável da planta: ______________________________</p>
            </div>
          </Card>
        {/if}
      </div>

      <aside class="side no-print">
        <Card title="Sessões deste equipamento" testid="cm-sessions">
          {#if list.sessions.length === 0}
            <p class="hint">Nenhuma visita registrada ainda.</p>
          {:else}
            <ul class="sessions">
              {#each list.sessions as s (s.id)}
                <li>
                  <button type="button" class="sess" aria-current={detail?.session.id === s.id ? 'true' : undefined} onclick={() => load(equipmentId, s.id)}>
                    <b>{s.header.visit_date}</b> · {s.header.technician}
                    <span class="st" data-status={s.status}>{s.status_pt}</span>
                  </button>
                </li>
              {/each}
            </ul>
          {/if}
          {#if detail && !open}
            <button type="button" class="btn ghost" onclick={() => { detail = null; form = blankHeader(list?.prefill ?? {}) }}>
              Nova visita
            </button>
          {/if}
        </Card>
      </aside>
    </div>
  {/if}
</section>

<style>
  .cm { display: flex; flex-direction: column; gap: var(--sp-5); min-width: 0; }
  .actions { display: flex; flex-wrap: wrap; gap: var(--sp-2); }
  .notice { margin: 0; padding: var(--sp-3) var(--sp-4); border-radius: var(--r-3); font: 500 var(--fs-body) / var(--lh-body) var(--font-ui); }
  .notice[data-tone='ok'] { background: var(--st-ok-bg); color: var(--st-ok); }
  .notice[data-tone='warn'] { background: var(--st-warn-bg); color: var(--st-warn); }
  .notice[data-tone='crit'] { background: var(--st-crit-bg); color: var(--st-crit); }
  .sk { height: 320px; border-radius: var(--r-4); background: var(--surf-2); opacity: 0.6; }
  .layout { display: grid; gap: var(--sp-4); grid-template-columns: minmax(0, 1fr); align-items: start; }
  @media (min-width: 1280px) { .layout { grid-template-columns: minmax(0, 3fr) minmax(300px, 1fr); } }
  .main, .side { display: flex; flex-direction: column; gap: var(--sp-4); min-width: 0; }
  .grid { display: grid; gap: var(--sp-3); grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); }
  label { display: flex; flex-direction: column; gap: 4px; min-width: 0; color: var(--text-3); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .wide { grid-column: 1 / -1; }
  input, select, textarea { width: 100%; min-height: var(--touch); padding: var(--sp-2); border: 1px solid var(--border-input); border-radius: var(--r-2); background: var(--surf-2); color: var(--text-1); font: 16px / 1.3 var(--font-ui); }
  input:disabled, textarea:disabled { opacity: 0.7; }
  .row { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-3); margin-top: var(--sp-3); }
  .btn { display: inline-flex; align-items: center; justify-content: center; gap: var(--sp-2); min-height: var(--touch); padding: 0 var(--sp-4); border-radius: var(--r-3); font: 600 var(--fs-body) / 1.2 var(--font-ui); text-decoration: none; cursor: pointer; }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .btn.primary { border: 1px solid var(--accent); background: var(--accent); color: var(--on-accent); }
  .btn.ghost { border: 1px solid var(--border-2); background: var(--surf-1); color: var(--text-1); }
  .hint { margin: 0; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .to-check { display: grid; gap: var(--sp-3); grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); margin: var(--sp-3) 0; }
  .item { display: flex; flex-direction: column; gap: var(--sp-2); padding: var(--sp-3); border: 1px solid var(--border-1); border-radius: var(--r-3); background: var(--surf-2); min-width: 0; }
  .item[data-done='true'] { border-left: 3px solid var(--st-ok); }
  .item header { display: flex; justify-content: space-between; gap: var(--sp-2); }
  .item header b { color: var(--text-1); font: 600 var(--fs-body) / var(--lh-body) var(--font-ui); }
  .done { color: var(--st-ok); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .forja { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-2); margin: 0; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .forja b { color: var(--text-1); font-size: var(--fs-mono); }
  .forja small { flex-basis: 100%; color: var(--text-3); font-size: var(--fs-caption); }
  .fields { display: grid; gap: var(--sp-2); grid-template-columns: 1fr 1fr; }
  .table-wrap { overflow-x: auto; margin-top: var(--sp-3); }
  table { width: 100%; border-collapse: collapse; font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  th, td { padding: var(--sp-2); border-bottom: 1px solid var(--border-1); text-align: left; vertical-align: top; }
  thead th { color: var(--text-3); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  tbody th { color: var(--text-1); font-weight: 500; }
  .u { margin-left: 6px; color: var(--text-3); font-weight: 400; }
  .r { text-align: right; }
  td.num { font-family: var(--font-mono); font-size: var(--fs-mono-sm); color: var(--text-1); }
  .res { padding: 1px 8px; border-radius: var(--r-pill); border: 1px solid var(--border-2); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .res[data-result='MATCH'] { color: var(--st-ok); border-color: var(--st-ok); }
  .res[data-result='MISMATCH'] { color: var(--st-crit); border-color: var(--st-crit); }
  .res[data-result='NOT_EXPOSED'] { color: var(--text-2); }
  .conclusion { margin: 0; color: var(--text-1); font: var(--fs-body-lg) / var(--lh-body-lg) var(--font-ui); white-space: pre-wrap; }
  .signatures { margin-top: var(--sp-8); }
  .signatures p { margin: var(--sp-6) 0 0; }
  .sessions { display: flex; flex-direction: column; gap: var(--sp-2); margin: 0 0 var(--sp-3); padding: 0; list-style: none; }
  .sess { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-2); width: 100%; min-height: var(--touch); padding: var(--sp-2) var(--sp-3); border: 1px solid var(--border-1); border-radius: var(--r-3); background: var(--surf-1); color: var(--text-1); text-align: left; font: var(--fs-body) / var(--lh-body) var(--font-ui); cursor: pointer; }
  .sess[aria-current='true'] { border-color: var(--accent); background: var(--accent-soft); }
  .st { margin-left: auto; color: var(--text-3); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .st[data-status='OPEN'] { color: var(--st-warn); }
  @media (max-width: 767px) {
    .fields { grid-template-columns: minmax(0, 1fr); }
  }
</style>
