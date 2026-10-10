<script lang="ts">
  /** Resultado do TESTE SOMENTE LEITURA: etapas, latência e, por variável, onde foi lido, valor
   *  bruto, valor decodificado e qualidade. Ao lado, o valor que o técnico vê na tela do KCM:
   *  a diferença aparece na hora e a conferência pode ser registrada no mapping. */
  import Check from '@lucide/svelte/icons/check'
  import X from '@lucide/svelte/icons/x'
  import CircleCheck from '@lucide/svelte/icons/circle-check'
  import CircleX from '@lucide/svelte/icons/circle-x'
  import type { ReadTestResult } from '../../lib/comm'
  import { fmtNumber } from '../../lib/format'
  import QualityBadge from '../ui/QualityBadge.svelte'

  let {
    result,
    kcm = $bindable({}),
    canRegister = false,
    onregister,
  }: {
    result: ReadTestResult
    kcm?: Record<string, string>
    canRegister?: boolean
    onregister?: (tag: string, matched: boolean, forja: number | null, kcmValue: string) => void
  } = $props()

  const STAGE_PT: Record<string, string> = {
    CONNECTING: 'Conectando',
    HANDSHAKE: 'Conexão aceita',
    SESSION_CREATED: 'Sessão criada',
    READ_OBTAINED: 'Leitura obtida',
    TIMEOUT: 'Sem resposta (timeout)',
    CONNECTION_REFUSED: 'Conexão recusada',
    INVALID_RESPONSE: 'Resposta inválida',
    UNIDENTIFIED: 'Falha não identificada',
  }

  function parsed(text: string | undefined): number | null {
    if (!text) return null
    const n = Number(text.replace(/\./g, '').replace(',', '.'))
    return Number.isFinite(n) ? n : null
  }

  function diff(forja: number | null, typed: string | undefined): number | null {
    const k = parsed(typed)
    return forja == null || k == null ? null : k - forja
  }
</script>

<div class="rt" data-testid="read-test-result" data-success={result.success} data-final={result.final}>
  <ol class="stages" aria-label="Etapas do teste">
    {#each result.stages as [stage, , text], i (i)}
      {@const ok = !['TIMEOUT', 'CONNECTION_REFUSED', 'INVALID_RESPONSE', 'UNIDENTIFIED'].includes(stage)}
      <li data-ok={ok}>
        <span class="dot" aria-hidden="true">{#if ok}<Check size={14} strokeWidth={3} />{:else}<X size={14} strokeWidth={3} />{/if}</span>
        <span><b>{STAGE_PT[stage] ?? stage}</b>{#if text && text !== STAGE_PT[stage]}<small>{text}</small>{/if}</span>
      </li>
    {/each}
  </ol>

  <p class="verdict" data-ok={result.success}>
    {#if result.success}
      <CircleCheck size={20} aria-hidden="true" /> Leitura obtida
      {#if result.latency_ms != null}<span class="num">em {fmtNumber(result.latency_ms, 1)} ms</span>{/if}
    {:else}
      <CircleX size={20} aria-hidden="true" /> {result.final_pt ?? result.final}{#if result.error_pt}: {result.error_pt}{/if}
    {/if}
  </p>

  {#each result.warnings as w, i (i)}<p class="warn">{w}</p>{/each}

  {#if result.detail.tags.length}
    <div class="rows">
      {#each result.detail.tags as row (row.tag)}
        {@const d = diff(row.value, kcm[row.tag])}
        <article class="row" data-testid={`read-test-row-${row.tag}`} data-quality={row.quality ?? 'NONE'}>
          <header>
            <b>{row.label_pt}</b>
            {#if row.quality}<QualityBadge quality={row.quality} qualityPt={row.quality_pt} reasonPt={row.reason_pt} />{/if}
          </header>
          <dl>
            <div><dt>Onde foi lido</dt><dd class="num">{row.address_pt}</dd></div>
            <div><dt>Bruto (hex)</dt><dd class="num">{row.raw_hex ?? '—'}</dd></div>
            <div><dt>Tipo e ordem</dt><dd>{row.datatype} · {row.endianness_pt}</dd></div>
            <div><dt>Decodificado</dt><dd class="num big">{row.value_pt ?? 'sem valor'}</dd></div>
          </dl>
          {#if row.reason_pt}<p class="why">{row.reason_pt}</p>{/if}
          <div class="compare">
            <label>Valor na tela do KCM
              <input
                type="text"
                inputmode="decimal"
                placeholder="o que aparece no KCM"
                bind:value={kcm[row.tag]}
                data-testid={`kcm-value-${row.tag}`}
              />
            </label>
            <p class="diff num" data-has={d != null}>
              {#if d != null}Diferença (KCM − Forja): {fmtNumber(d, 3)}{:else}Diferença: —{/if}
            </p>
            {#if canRegister && onregister && row.value != null && kcm[row.tag]}
              <div class="reg">
                <button type="button" class="ok" onclick={() => onregister(row.tag, true, row.value, kcm[row.tag])} data-testid={`register-match-${row.tag}`}>Confere</button>
                <button type="button" class="ko" onclick={() => onregister(row.tag, false, row.value, kcm[row.tag])} data-testid={`register-mismatch-${row.tag}`}>Diverge</button>
              </div>
            {/if}
          </div>
        </article>
      {/each}
    </div>
  {/if}
</div>

<style>
  .rt { display: flex; flex-direction: column; gap: var(--sp-3); min-width: 0; }
  .stages { display: flex; flex-wrap: wrap; gap: var(--sp-2) var(--sp-4); margin: 0; padding: 0; list-style: none; }
  .stages li { display: flex; align-items: center; gap: var(--sp-2); color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); animation: pop var(--dur-base) var(--ease-out) both; }
  .stages small { display: block; color: var(--text-3); }
  .dot { display: inline-grid; place-items: center; width: 22px; height: 22px; border-radius: var(--r-pill); background: var(--st-ok-bg); color: var(--st-ok); }
  li[data-ok='false'] .dot { background: var(--st-crit-bg); color: var(--st-crit); }
  @keyframes pop { from { opacity: 0; transform: scale(0.96); } to { opacity: 1; transform: none; } }
  .verdict { display: flex; flex-wrap: wrap; align-items: center; gap: var(--sp-2); margin: 0; padding: var(--sp-3); border-radius: var(--r-3); background: var(--st-ok-bg); color: var(--st-ok); font: 600 var(--fs-body) / var(--lh-body) var(--font-ui); }
  .verdict[data-ok='false'] { background: var(--st-crit-bg); color: var(--st-crit); }
  .verdict .num { color: var(--text-2); font-weight: 400; }
  .warn { margin: 0; padding: var(--sp-2) var(--sp-3); border-left: 3px solid var(--st-warn); background: var(--st-warn-bg); color: var(--text-1); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .rows { display: grid; gap: var(--sp-3); grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); }
  .row { display: flex; flex-direction: column; gap: var(--sp-2); padding: var(--sp-3); border: 1px solid var(--border-1); border-radius: var(--r-3); background: var(--surf-2); min-width: 0; }
  .row header { display: flex; align-items: center; justify-content: space-between; gap: var(--sp-2); flex-wrap: wrap; }
  .row header b { color: var(--text-1); font: 600 var(--fs-body) / var(--lh-body) var(--font-ui); }
  dl { display: grid; gap: 4px; margin: 0; }
  dl div { display: grid; grid-template-columns: 110px minmax(0, 1fr); gap: var(--sp-2); }
  dt { color: var(--text-3); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  dd { margin: 0; color: var(--text-1); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); overflow-wrap: anywhere; }
  dd.num { font-family: var(--font-mono); }
  dd.big { font-size: var(--fs-mono); font-weight: 600; }
  .why { margin: 0; color: var(--text-3); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .compare { display: flex; flex-direction: column; gap: var(--sp-2); padding-top: var(--sp-2); border-top: 1px dashed var(--border-2); }
  .compare label { display: flex; flex-direction: column; gap: 4px; color: var(--text-3); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .compare input { min-height: var(--touch); padding: 0 var(--sp-2); border: 1px solid var(--border-input); border-radius: var(--r-2); background: var(--surf-1); color: var(--text-1); font: 16px / 1.2 var(--font-mono); }
  .diff { margin: 0; color: var(--text-3); font-size: var(--fs-mono-sm); }
  .diff[data-has='true'] { color: var(--text-1); }
  .reg { display: flex; gap: var(--sp-2); }
  .reg button { flex: 1; min-height: var(--touch); border-radius: var(--r-3); border: 1px solid; font: 600 var(--fs-body) / 1 var(--font-ui); cursor: pointer; background: transparent; }
  .reg .ok { border-color: var(--st-ok); color: var(--st-ok); }
  .reg .ko { border-color: var(--st-crit); color: var(--st-crit); }
  @media (max-width: 767px) {
    dl div { grid-template-columns: minmax(0, 1fr); gap: 0; }
  }
</style>
