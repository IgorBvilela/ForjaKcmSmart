<script lang="ts">
  /** Sobre: versão, somente leitura, origem dos dados, licenças das dependências empacotadas. */
  import { onMount } from 'svelte'
  import { api, errorMessage, type About } from '../lib/api'
  import { fmtDateTime, fmtDuration } from '../lib/format'
  import { TID } from '../lib/testids'
  import Badge from '../components/ui/Badge.svelte'
  import Card from '../components/ui/Card.svelte'
  import EmptyState from '../components/ui/EmptyState.svelte'

  let about = $state<About | null>(null)
  let error = $state<string | null>(null)

  const LICENSES = [
    { name: 'IBM Plex Sans', license: 'OFL 1.1', file: 'IBM-Plex-Sans-OFL.txt', use: 'tipografia da interface' },
    { name: 'IBM Plex Mono', license: 'OFL 1.1', file: 'IBM-Plex-Mono-OFL.txt', use: 'números e código' },
    { name: 'Lucide', license: 'ISC', file: 'Lucide-ISC.txt', use: 'ícones' },
    { name: 'uPlot', license: 'MIT', file: 'uPlot-MIT.txt', use: 'gráficos de tendência (fase E)' },
    { name: 'Svelte', license: 'MIT', file: 'Svelte-MIT.txt', use: 'framework da interface' },
  ]

  onMount(() => {
    api
      .about()
      .then((a) => (about = a))
      .catch((e) => (error = errorMessage(e)))
  })
</script>

<section class="about" data-testid={TID.about}>
  <header class="about-head">
    <p class="label">Sistema</p>
    <h1 class="about-title">Sobre</h1>
  </header>

  <Card class="phrase-card">
    <p class="phrase">
      O KCM controla a dosagem. A Forja observa o KCM, entende o comportamento e ajuda a manutenção a
      diagnosticar.
    </p>
    <div class="phrase-badges">
      <Badge tone="neutral" size="md">Somente leitura</Badge>
      <Badge tone="info" size="md">Offline-first · nada sai da máquina</Badge>
      {#if about}
        <Badge tone={about.data_source === 'SIMULATED' ? 'sim' : 'info'} hatch={about.data_source === 'SIMULATED'} size="md">
          {about.data_source_pt}
        </Badge>
      {/if}
    </div>
  </Card>

  <div class="about-grid">
    <Card title="Este Edge" kicker="Instalação local">
      {#if error}
        <EmptyState compact title="Sem resposta do Edge" text={error} />
      {:else if about}
        <dl class="facts">
          <div><dt class="label">Produto</dt><dd>{about.name}</dd></div>
          <div><dt class="label">Nome do Edge</dt><dd>{about.edge_name}</dd></div>
          <div><dt class="label">Versão</dt><dd class="num">{about.version}</dd></div>
          <div><dt class="label">Contrato de diagnóstico</dt><dd class="num">v{about.diagnosis_schema_version}</dd></div>
          <div><dt class="label">Escrita no equipamento</dt><dd>{about.read_only ? 'Nenhuma. Driver só lê.' : 'Indefinido'}</dd></div>
          <div><dt class="label">Origem dos dados</dt><dd>{about.data_source_pt}</dd></div>
          <div><dt class="label">Equipamentos</dt><dd class="num">{about.equipment_count}</dd></div>
          <div><dt class="label">Em execução há</dt><dd class="num">{fmtDuration(about.uptime_s)}</dd></div>
          <div><dt class="label">Iniciado em</dt><dd class="num">{fmtDateTime(about.started_at_utc)}</dd></div>
          <div><dt class="label">Fuso horário</dt><dd class="num">{about.timezone}</dd></div>
          <div><dt class="label">Python</dt><dd class="num">{about.python}</dd></div>
          <div><dt class="label">SQLite</dt><dd class="num">{about.sqlite}</dd></div>
          {#if about.dev_mode}
            <div><dt class="label">Modo</dt><dd>Desenvolvimento{about.docs_url ? ` · documentação da API em ${about.docs_url}` : ''}</dd></div>
          {/if}
        </dl>
      {:else}
        <p class="muted">Consultando o Edge…</p>
      {/if}
    </Card>

    <Card title="Licenças" kicker="Dependências empacotadas">
      <p class="lic-intro">Tudo roda local, sem CDN e sem fonte remota. Os textos completos estão incluídos neste build.</p>
      <ul class="lic">
        {#each LICENSES as l (l.name)}
          <li>
            <span class="lic-name">{l.name}</span>
            <span class="lic-use">{l.use}</span>
            <a class="lic-link" href={`/app/licenses/${l.file}`} target="_blank" rel="noopener">{l.license}</a>
          </li>
        {/each}
      </ul>
    </Card>
  </div>

  <Card title="Como a Forja trata a informação" kicker="Regras do produto">
    <ul class="rules">
      <li><strong>Somente leitura por construção.</strong> O driver só conecta, lê e informa saúde. Não existe escrita em código, API, interface ou perfis.</li>
      <li><strong>Leitura direta do KCM</strong> via interface Host/Anybus. PLC e SCADA não são fonte nem reserva.</li>
      <li><strong>Sem comunicação ≠ valor antigo.</strong> Falha na tentativa atual aparece como "Sem comunicação"; valor que envelheceu aparece desbotado com a idade. Buraco nunca é interpolado.</li>
      <li><strong>Hipótese não é causa.</strong> Todo diagnóstico diz "comportamento compatível com" e carrega o nível de evidência de cada item.</li>
      <li><strong>Nada da planta é inventado.</strong> O que não se sabe fica como "não confirmado" até prova de campo.</li>
    </ul>
  </Card>
</section>

<style>
  .about { display: flex; flex-direction: column; gap: var(--sp-5); }
  .about-head .label { margin: 0 0 var(--sp-1); }
  .about-title {
    margin: 0;
    font: 600 var(--fs-h1) / var(--lh-h1) var(--font-ui);
    color: var(--text-1);
  }
  @media (min-width: 1024px) {
    .about-title { font-size: var(--fs-display); line-height: var(--lh-display); }
  }
  .phrase {
    margin: 0;
    max-width: 60ch;
    font: 500 var(--fs-h2) / var(--lh-h2) var(--font-ui);
    color: var(--text-1);
  }
  .phrase-badges { display: flex; flex-wrap: wrap; gap: var(--sp-2); margin-top: var(--sp-4); }

  .about-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 360px), 1fr));
    gap: var(--sp-5);
    align-items: start;
  }
  .facts {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: var(--sp-3) var(--sp-5);
    margin: 0;
  }
  .facts div { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .facts dd {
    margin: 0;
    color: var(--text-1);
    font: var(--fs-body) / var(--lh-body) var(--font-ui);
    overflow-wrap: anywhere;
  }
  .facts dd.num { font-size: var(--fs-mono); }
  .muted { margin: 0; color: var(--text-3); }

  .lic-intro { margin: 0 0 var(--sp-3); color: var(--text-2); font: var(--fs-body) / var(--lh-body) var(--font-ui); }
  .lic { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
  .lic li {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1.4fr) auto;
    gap: var(--sp-3);
    align-items: center;
    min-height: 44px;
    padding: var(--sp-2) 0;
    border-top: 1px solid var(--border-1);
  }
  .lic li:first-child { border-top: 0; }
  .lic-name { color: var(--text-1); font: 500 var(--fs-body) / var(--lh-body) var(--font-ui); }
  .lic-use { color: var(--text-3); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .lic-link {
    display: inline-flex;
    align-items: center;
    align-self: stretch;
    justify-content: center;
    min-width: var(--touch);
    min-height: var(--touch);
    color: var(--accent-text);
    text-decoration: none;
    font: 500 var(--fs-caption) / var(--lh-caption) var(--font-mono);
    border-radius: var(--r-1);
    padding: 0 var(--sp-2);
  }
  .lic-link:hover { text-decoration: underline; }
  @media (max-width: 479px) {
    .lic li { grid-template-columns: minmax(0, 1fr) auto; }
    .lic-use { grid-column: 1 / -1; }
  }

  .rules {
    margin: 0;
    padding-left: var(--sp-5);
    color: var(--text-2);
    font: var(--fs-body) / var(--lh-body) var(--font-ui);
    display: flex;
    flex-direction: column;
    gap: var(--sp-2);
  }
  .rules strong { color: var(--text-1); font-weight: 600; }
</style>
