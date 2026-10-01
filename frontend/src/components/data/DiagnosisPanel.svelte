<script lang="ts">
  /** Diagnóstico v1.0 nas 7 seções oficiais, na ordem do contrato. A UI consome o JSON como veio. */
  import {
    EVIDENCE_PT,
    SOURCE_KIND_PT,
    severityTone,
    type Diagnosis,
    type NextCheck,
  } from '../../lib/api'
  import { fmtDateTime, fmtNumber } from '../../lib/format'
  import { TID } from '../../lib/testids'
  import Badge from '../ui/Badge.svelte'
  import QualityBadge from '../ui/QualityBadge.svelte'
  import EvidenceBadge from './EvidenceBadge.svelte'
  import WhatChanged from './WhatChanged.svelte'

  let { diagnosis }: { diagnosis: Diagnosis } = $props()

  const sections = [
    ['summary', 'RESUMO'],
    ['evidence', 'EVIDÊNCIAS'],
    ['what_changed', 'O QUE MUDOU'],
    ['hypotheses', 'HIPÓTESES'],
    ['next_checks', 'PRÓXIMAS VERIFICAÇÕES'],
    ['sources', 'FONTES'],
    ['caveats', 'RESSALVAS'],
  ] as const

  const checksOrdered = $derived<NextCheck[]>(
    [...diagnosis.next_checks].sort((a, b) => a.order - b.order),
  )
  const sourceById = $derived(new Map(diagnosis.sources.map((s) => [s.id, s])))
  const tone = $derived(severityTone(diagnosis.summary.severity))
  const severityPt = $derived(
    diagnosis.summary.severity === 'CRITICAL'
      ? 'Crítico'
      : diagnosis.summary.severity === 'ATTENTION'
        ? 'Atenção'
        : 'Informação',
  )

  function sectionId(code: string): string {
    return `diag-${code}`
  }
</script>

<div class="panel" data-testid={TID.diagnosisPanel} data-schema={diagnosis.diagnosis_schema_version}>
  <nav class="toc" aria-label="Seções do diagnóstico">
    {#each sections as [code, label], i (code)}
      <a href={`#${sectionId(code)}`} class="toc-link">
        <span class="toc-n num">{i + 1}</span>
        <span class="toc-label">{label}</span>
      </a>
    {/each}
  </nav>

  <!-- 1. RESUMO -->
  <section
    class="sec sec-summary"
    id={sectionId('summary')}
    data-testid={TID.diagnosisSection('RESUMO')}
    aria-labelledby={`${sectionId('summary')}-h`}
  >
    <header class="sec-head">
      <span class="sec-n num">1</span>
      <h3 class="label" id={`${sectionId('summary')}-h`}>Resumo</h3>
      <Badge {tone} size="md">{severityPt}</Badge>
    </header>
    <h2 class="summary-title">{diagnosis.summary.title_pt}</h2>
    <p class="summary-text">{diagnosis.summary.text_pt}</p>
  </section>

  <!-- 2. EVIDÊNCIAS -->
  <section
    class="sec"
    id={sectionId('evidence')}
    data-testid={TID.diagnosisSection('EVIDENCIAS')}
    aria-labelledby={`${sectionId('evidence')}-h`}
  >
    <header class="sec-head">
      <span class="sec-n num">2</span>
      <h3 class="label" id={`${sectionId('evidence')}-h`}>Evidências</h3>
      <span class="count num">{diagnosis.evidence.length}</span>
    </header>
    {#if diagnosis.evidence.length === 0}
      <p class="muted">Nenhuma evidência registrada.</p>
    {:else}
      <ul class="list">
        {#each diagnosis.evidence as ev (ev.id)}
          <li class="item" data-id={ev.id}>
            <div class="item-main">
              <p class="item-text">{ev.text_pt}</p>
              <div class="item-meta">
                <EvidenceBadge level={ev.evidence_level} />
                {#if ev.value != null}
                  <span class="num meta-val">{fmtNumber(ev.value, 2)}{ev.unit ? ` ${ev.unit}` : ''}</span>
                {/if}
                {#if ev.quality}<QualityBadge quality={ev.quality} />{/if}
              </div>
            </div>
          </li>
        {/each}
      </ul>
    {/if}
  </section>

  <!-- 3. O QUE MUDOU -->
  <section
    class="sec"
    id={sectionId('what_changed')}
    data-testid={TID.diagnosisSection('O_QUE_MUDOU')}
    aria-labelledby={`${sectionId('what_changed')}-h`}
  >
    <header class="sec-head">
      <span class="sec-n num">3</span>
      <h3 class="label" id={`${sectionId('what_changed')}-h`}>O que mudou</h3>
    </header>
    <WhatChanged items={diagnosis.what_changed} />
  </section>

  <!-- 4. HIPÓTESES -->
  <section
    class="sec"
    id={sectionId('hypotheses')}
    data-testid={TID.diagnosisSection('HIPOTESES')}
    aria-labelledby={`${sectionId('hypotheses')}-h`}
  >
    <header class="sec-head">
      <span class="sec-n num">4</span>
      <h3 class="label" id={`${sectionId('hypotheses')}-h`}>Hipóteses</h3>
      <span class="hint">comportamento compatível com, nunca causa confirmada</span>
    </header>
    {#if diagnosis.hypotheses.length === 0}
      <p class="muted">Nenhuma hipótese formulada.</p>
    {:else}
      <ol class="list numbered">
        {#each diagnosis.hypotheses as h, i (h.id)}
          <li class="item" data-id={h.id}>
            <span class="item-n num">{i + 1}</span>
            <div class="item-main">
              <p class="item-text strong">{h.text_pt}</p>
              {#if h.rationale_pt}<p class="item-sub">{h.rationale_pt}</p>{/if}
              <div class="item-meta">
                <EvidenceBadge level={h.evidence_level} />
                {#if h.verification_ids.length}
                  <span class="refs">
                    Verificar:
                    {#each h.verification_ids as vid, k (vid)}
                      <a href={`#check-${vid}`} class="ref">{vid}</a>{k < h.verification_ids.length - 1 ? ', ' : ''}
                    {/each}
                  </span>
                {/if}
                {#if h.source_ids.length}
                  <span class="refs">
                    Fontes:
                    {#each h.source_ids as sid, k (sid)}
                      <a href={`#source-${sid}`} class="ref" title={sourceById.get(sid)?.title ?? sid}>{sid}</a>{k < h.source_ids.length - 1 ? ', ' : ''}
                    {/each}
                  </span>
                {/if}
              </div>
            </div>
          </li>
        {/each}
      </ol>
    {/if}
  </section>

  <!-- 5. PRÓXIMAS VERIFICAÇÕES -->
  <section
    class="sec"
    id={sectionId('next_checks')}
    data-testid={TID.diagnosisSection('PROXIMAS_VERIFICACOES')}
    aria-labelledby={`${sectionId('next_checks')}-h`}
  >
    <header class="sec-head">
      <span class="sec-n num">5</span>
      <h3 class="label" id={`${sectionId('next_checks')}-h`}>Próximas verificações</h3>
      <span class="hint">na ordem sugerida</span>
    </header>
    {#if checksOrdered.length === 0}
      <p class="muted">Nenhuma verificação sugerida.</p>
    {:else}
      <ol class="list numbered">
        {#each checksOrdered as c (c.id)}
          <li class="item" id={`check-${c.id}`} data-id={c.id}>
            <span class="item-n num">{c.order}</span>
            <div class="item-main">
              <p class="item-text strong">{c.text_pt}</p>
              {#if c.how_pt}
                <p class="item-sub"><span class="kv">Como:</span> {c.how_pt}</p>
              {/if}
              {#if c.safety_pt}
                <p class="item-sub"><span class="kv">Segurança:</span> {c.safety_pt}</p>
              {/if}
              <div class="item-meta">
                <EvidenceBadge level={c.evidence_level} />
                <span class="refs id">{c.id}</span>
              </div>
            </div>
          </li>
        {/each}
      </ol>
    {/if}
  </section>

  <!-- 6. FONTES -->
  <section
    class="sec"
    id={sectionId('sources')}
    data-testid={TID.diagnosisSection('FONTES')}
    aria-labelledby={`${sectionId('sources')}-h`}
  >
    <header class="sec-head">
      <span class="sec-n num">6</span>
      <h3 class="label" id={`${sectionId('sources')}-h`}>Fontes</h3>
      <span class="count num">{diagnosis.sources.length}</span>
    </header>
    {#if diagnosis.sources.length === 0}
      <p class="muted">Nenhuma fonte referenciada.</p>
    {:else}
      <ul class="list">
        {#each diagnosis.sources as s (s.id)}
          <li class="item" id={`source-${s.id}`} data-id={s.id}>
            <div class="item-main">
              <p class="item-text">
                <span class="kind">{SOURCE_KIND_PT[s.kind] ?? s.kind}</span>
                {s.title}
              </p>
              {#if s.reference}<p class="item-sub mono">{s.reference}</p>{/if}
              <div class="item-meta">
                <EvidenceBadge level={s.evidence_level} />
                <span class="refs id">{s.id}</span>
              </div>
            </div>
          </li>
        {/each}
      </ul>
    {/if}
  </section>

  <!-- 7. RESSALVAS -->
  <section
    class="sec sec-caveats"
    id={sectionId('caveats')}
    data-testid={TID.diagnosisSection('RESSALVAS')}
    aria-labelledby={`${sectionId('caveats')}-h`}
  >
    <header class="sec-head">
      <span class="sec-n num">7</span>
      <h3 class="label" id={`${sectionId('caveats')}-h`}>Ressalvas</h3>
    </header>
    <ul class="caveats">
      {#each diagnosis.caveats as c, i (i)}
        <li>{c.text_pt}</li>
      {/each}
    </ul>
  </section>

  <footer class="foot">
    <span>
      Evidência mais forte:
      <strong>{diagnosis.evidence_summary.strongest_level ? EVIDENCE_PT[diagnosis.evidence_summary.strongest_level] : '—'}</strong>
      · mais fraca:
      <strong>{diagnosis.evidence_summary.weakest_level ? EVIDENCE_PT[diagnosis.evidence_summary.weakest_level] : '—'}</strong>
    </span>
    <span class="foot-note">{diagnosis.evidence_summary.note_pt}</span>
    <span class="foot-meta">Gerado em {fmtDateTime(diagnosis.generated_at_utc)} · contrato v{diagnosis.diagnosis_schema_version}</span>
  </footer>
</div>

<style>
  .panel {
    display: flex;
    flex-direction: column;
    gap: var(--sp-6);
    min-width: 0;
  }
  .toc {
    display: flex;
    flex-wrap: wrap;
    gap: var(--sp-2);
    padding-bottom: var(--sp-4);
    border-bottom: 1px solid var(--border-1);
  }
  .toc-link {
    display: inline-flex;
    align-items: center;
    gap: var(--sp-2);
    min-height: 32px;
    padding: 0 var(--sp-3);
    border: 1px solid var(--border-1);
    border-radius: var(--r-pill);
    color: var(--text-2);
    text-decoration: none;
    font: 500 var(--fs-label) / var(--lh-label) var(--font-ui);
    letter-spacing: var(--ls-label);
    text-transform: uppercase;
    transition:
      border-color var(--dur-base) var(--ease-std),
      color var(--dur-base) var(--ease-std);
  }
  .toc-link:hover { border-color: var(--border-2); color: var(--text-1); }
  .toc-n { color: var(--accent-text); font-size: var(--fs-mono-sm); }
  @media (max-width: 767px) {
    .toc-link { min-height: var(--touch); }
  }

  .sec { display: flex; flex-direction: column; gap: var(--sp-3); scroll-margin-top: 96px; }
  .sec-head {
    display: flex;
    align-items: center;
    gap: var(--sp-3);
    flex-wrap: wrap;
  }
  .sec-head h3 { margin: 0; }
  .sec-n {
    display: grid;
    place-items: center;
    width: 24px;
    height: 24px;
    border-radius: 50%;
    background: var(--surf-2);
    color: var(--accent-text);
    font-size: var(--fs-mono-sm);
  }
  .count {
    color: var(--text-3);
    font-size: var(--fs-mono-sm);
  }
  .hint {
    color: var(--text-3);
    font: var(--fs-caption) / var(--lh-caption) var(--font-ui);
  }
  .summary-title {
    margin: 0;
    font: 600 var(--fs-h1) / var(--lh-h1) var(--font-ui);
    color: var(--text-1);
  }
  .summary-text {
    margin: 0;
    font: var(--fs-body-lg) / var(--lh-body-lg) var(--font-ui);
    color: var(--text-1);
    max-width: 80ch;
  }
  .muted { margin: 0; color: var(--text-3); }

  .list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    border: 1px solid var(--border-1);
    border-radius: var(--r-3);
    overflow: hidden;
  }
  .item {
    display: flex;
    gap: var(--sp-3);
    padding: var(--sp-3) var(--sp-4);
    border-top: 1px solid var(--border-1);
    background: var(--surf-1);
    scroll-margin-top: 96px;
  }
  .item:first-child { border-top: 0; }
  .item:target { background: var(--surf-2); }
  .item-n {
    flex: none;
    width: 24px;
    height: 24px;
    display: grid;
    place-items: center;
    border-radius: 50%;
    border: 1px solid var(--border-2);
    color: var(--text-2);
    font-size: var(--fs-mono-sm);
  }
  .item-main { display: flex; flex-direction: column; gap: var(--sp-1); min-width: 0; }
  .item-text {
    margin: 0;
    color: var(--text-1);
    font: var(--fs-body) / var(--lh-body) var(--font-ui);
  }
  .item-text.strong { font-weight: 500; }
  .item-sub {
    margin: 0;
    color: var(--text-2);
    font: var(--fs-caption) / var(--lh-caption) var(--font-ui);
  }
  .item-sub.mono { font-family: var(--font-mono); font-size: var(--fs-mono-sm); color: var(--text-3); }
  .kv { color: var(--text-3); font-weight: 500; }
  .kind {
    display: inline-block;
    margin-right: var(--sp-2);
    padding: 0 6px;
    border-radius: var(--r-1);
    background: var(--surf-2);
    color: var(--text-3);
    font: 500 var(--fs-label) / var(--lh-label) var(--font-ui);
    letter-spacing: var(--ls-label);
    text-transform: uppercase;
    vertical-align: middle;
  }
  .item-meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--sp-2) var(--sp-3);
    margin-top: var(--sp-1);
  }
  .meta-val { color: var(--text-2); font-size: var(--fs-mono-sm); }
  .refs {
    color: var(--text-3);
    font: var(--fs-caption) / var(--lh-caption) var(--font-ui);
  }
  .refs.id { font-family: var(--font-mono); font-size: var(--fs-mono-sm); }
  .ref {
    color: var(--accent-text);
    text-decoration: none;
    font-family: var(--font-mono);
    font-size: var(--fs-mono-sm);
    border-radius: var(--r-1);
  }
  .ref:hover { text-decoration: underline; }

  .caveats {
    margin: 0;
    padding: var(--sp-3) var(--sp-4) var(--sp-3) var(--sp-8);
    border: 1px solid var(--border-1);
    border-left: 2px solid var(--st-warn);
    border-radius: var(--r-3);
    background: var(--surf-1);
    color: var(--text-2);
    font: var(--fs-body) / var(--lh-body) var(--font-ui);
    display: flex;
    flex-direction: column;
    gap: var(--sp-1);
  }
  .caveats li:first-child { color: var(--text-1); font-weight: 500; }

  .foot {
    display: flex;
    flex-direction: column;
    gap: var(--sp-1);
    padding-top: var(--sp-4);
    border-top: 1px solid var(--border-1);
    color: var(--text-2);
    font: var(--fs-caption) / var(--lh-caption) var(--font-ui);
  }
  .foot strong { color: var(--text-1); font-weight: 500; }
  .foot-note,
  .foot-meta { color: var(--text-3); }
</style>
