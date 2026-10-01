<script lang="ts">
  /** Qualidade do dado: sempre pill (forma + cor). GOOD quieto, SIMULATED lilás com hachura,
   *  UNCERTAIN tracejado âmbar, STALE desbotado tracejado com idade, COMM_ERROR anel oco ciano,
   *  BAD contorno vermelho com ✕. */
  import { QUALITY_PT, type Quality } from '../../lib/api'
  import { fmtAge } from '../../lib/format'

  let {
    quality,
    qualityPt,
    ageS = null,
    reasonPt = null,
    testid,
  }: {
    quality: Quality
    qualityPt?: string | null
    ageS?: number | null
    reasonPt?: string | null
    testid?: string
  } = $props()

  const text = $derived(qualityPt ?? QUALITY_PT[quality] ?? quality)
  const age = $derived(quality === 'STALE' && ageS != null ? ` · ${fmtAge(ageS)}` : '')
  const title = $derived(
    reasonPt ??
      (quality === 'STALE'
        ? 'Último valor conhecido. Não representa o estado atual.'
        : quality === 'SIMULATED'
          ? 'Dado gerado pelo simulador. Nenhum valor representa um KCM real.'
          : undefined),
  )
</script>

<span class="q" data-quality={quality} data-testid={testid} {title}>
  <span class="mark" aria-hidden="true">{#if quality === 'BAD'}✕{/if}</span>
  <span class="txt">{text}{age}</span>
</span>

<style>
  .q {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 1px 8px;
    border: 1px solid var(--border-1);
    border-radius: var(--r-pill);
    font: 500 var(--fs-label) / var(--lh-label) var(--font-ui);
    letter-spacing: var(--ls-label);
    text-transform: uppercase;
    color: var(--text-3);
    white-space: nowrap;
  }
  .mark {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex: none;
    display: inline-grid;
    place-items: center;
    font-size: 9px;
    line-height: 1;
  }

  [data-quality='GOOD'] { color: var(--text-2); border-color: var(--border-1); }
  [data-quality='GOOD'] .mark { background: var(--q-good); }

  [data-quality='SIMULATED'] {
    color: var(--q-sim);
    border-color: color-mix(in srgb, var(--q-sim) 45%, transparent);
    background-image: var(--q-sim-hatch);
  }
  [data-quality='SIMULATED'] .mark { background: var(--q-sim); }

  [data-quality='UNCERTAIN'] {
    color: var(--q-uncertain);
    border-style: dashed;
    border-color: var(--q-uncertain);
  }
  [data-quality='UNCERTAIN'] .mark { background: var(--q-uncertain); }

  [data-quality='STALE'] {
    color: var(--q-stale);
    border-style: dashed;
    border-color: var(--border-2);
  }
  [data-quality='STALE'] .mark {
    background: transparent;
    box-shadow: inset 0 0 0 1.5px var(--q-stale);
  }

  [data-quality='COMM_ERROR'] {
    color: var(--q-comm);
    border-color: color-mix(in srgb, var(--st-info) 45%, transparent);
  }
  [data-quality='COMM_ERROR'] .mark {
    background: transparent;
    box-shadow: inset 0 0 0 1.5px var(--q-comm);
  }

  [data-quality='BAD'] {
    color: var(--q-bad);
    border-color: var(--st-crit);
  }
  [data-quality='BAD'] .mark {
    border: 1px solid var(--q-bad);
    border-radius: 2px;
    color: var(--q-bad);
  }
</style>
