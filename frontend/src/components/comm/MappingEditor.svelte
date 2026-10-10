<script lang="ts">
  /** Editor do mapping: uma variável por cartão. Endereço, tipo, ordem de bytes, escala, faixa
   *  válida e fonte. Campos mudam com o protocolo. Nada vem preenchido por suposição: o que não
   *  está no documento da máquina fica "Não definido" (UNKNOWN). */
  import ChevronDown from '@lucide/svelte/icons/chevron-down'
  import Plus from '@lucide/svelte/icons/plus'
  import Trash2 from '@lucide/svelte/icons/trash-2'
  import {
    DATATYPE_PT,
    ENDIANNESS_PT,
    MODBUS_AREAS,
    type DataTypeName,
    type EndiannessName,
    type MappingDto,
    type MappingEntryDto,
  } from '../../lib/comm'
  import { fmtNumber } from '../../lib/format'
  import { sortTags, tagCatalog } from '../../lib/tagmeta.svelte'

  let {
    mapping = $bindable(),
    driver,
    readonly = false,
  }: { mapping: MappingDto; driver: string; readonly?: boolean } = $props()

  let open = $state<Record<string, boolean>>({})
  let toAdd = $state('')
  const uid = $props.id()

  const available = $derived(
    sortTags(Object.keys(tagCatalog.byCode)).filter(
      (t) => !mapping.entries.some((e) => e.semantic_tag === t),
    ),
  )

  /** Leitura do endereço para exibir (nunca altera estado durante a renderização). */
  function view(e: MappingEntryDto): Record<string, unknown> {
    return typeof e.protocol_address === 'object' && e.protocol_address !== null ? e.protocol_address : {}
  }

  /** Garante o objeto de endereço; só em evento de edição. */
  function ensure(e: MappingEntryDto): Record<string, unknown> {
    if (typeof e.protocol_address === 'object' && e.protocol_address !== null) return e.protocol_address
    e.protocol_address = driver === 'ethernet_ip' ? { kind: 'assembly' } : { area: 'holding' }
    return e.protocol_address as Record<string, unknown>
  }

  function num(value: unknown): string {
    return typeof value === 'number' && Number.isFinite(value) ? String(value) : ''
  }

  function setNum(e: MappingEntryDto, key: string, raw: string, optional = true): void {
    const a = ensure(e)
    const trimmed = raw.trim()
    if (trimmed === '') {
      if (optional) delete a[key]
      else a[key] = null
      return
    }
    const n = Number(trimmed)
    a[key] = Number.isFinite(n) ? Math.trunc(n) : trimmed
  }

  function status(e: MappingEntryDto): { text: string; tone: string } {
    if (e.confirmed) return { text: 'Validada na tela do KCM', tone: 'ok' }
    if (e.protocol_address === 'UNKNOWN' || e.datatype === 'UNKNOWN') return { text: 'Sem endereço', tone: 'unknown' }
    if (e.validation && !e.validation.matched) return { text: 'Divergiu na conferência', tone: 'crit' }
    return { text: 'Não validada', tone: 'warn' }
  }

  function summary(e: MappingEntryDto): string {
    if (e.protocol_address === 'UNKNOWN') return 'endereço não informado'
    const a = e.protocol_address as Record<string, unknown>
    if (driver === 'ethernet_ip') {
      return `classe ${a.class ?? '?'} · instância ${a.instance ?? '?'} · atributo ${a.attribute ?? '?'} · byte ${a.offset ?? 0}`
    }
    if (driver === 'modbus_tcp') {
      const area = MODBUS_AREAS.find((x) => x.value === a.area)?.label ?? String(a.area ?? '?')
      return `${area} · endereço ${a.address ?? '?'}${a.bit != null ? ` · bit ${a.bit}` : ''}`
    }
    return String(e.protocol_address)
  }

  function clearAddress(e: MappingEntryDto): void {
    e.protocol_address = 'UNKNOWN'
    e.confirmed = false
  }

  function remove(tag: string): void {
    mapping.entries = mapping.entries.filter((e) => e.semantic_tag !== tag)
  }

  function add(): void {
    if (!toAdd) return
    mapping.entries = [
      ...mapping.entries,
      {
        semantic_tag: toAdd,
        protocol_address: 'UNKNOWN',
        datatype: 'UNKNOWN',
        endianness: 'UNKNOWN',
        scale: 'UNKNOWN',
        unit: null,
        confirmed: false,
        source: 'UNKNOWN',
        evidence: 'UNKNOWN',
        validation: null,
        valid_min: null,
        valid_max: null,
        notes_pt: '',
      },
    ]
    open[toAdd] = true
    toAdd = ''
  }

  function scaleValue(e: MappingEntryDto, key: 'factor' | 'offset'): string {
    return e.scale === 'UNKNOWN' ? '' : String(e.scale[key])
  }

  function setScale(e: MappingEntryDto, key: 'factor' | 'offset', raw: string): void {
    const n = Number(raw)
    if (raw.trim() === '' || !Number.isFinite(n)) {
      if (key === 'factor') e.scale = 'UNKNOWN'
      return
    }
    const base = e.scale === 'UNKNOWN' ? { factor: 1, offset: 0 } : e.scale
    e.scale = { ...base, [key]: n }
  }

  function setRange(e: MappingEntryDto, key: 'valid_min' | 'valid_max', raw: string): void {
    const n = Number(raw)
    e[key] = raw.trim() === '' || !Number.isFinite(n) ? null : n
  }

  function onEdit(e: MappingEntryDto): void {
    // qualquer mudança de endereço/tipo invalida a conferência anterior
    if (e.confirmed) e.confirmed = false
  }
</script>

<div class="editor" data-testid="mapping-editor" data-driver={driver}>
  <p class="meta">
    <span>Mapping <b class="num">{mapping.mapping_id}</b></span>
    <span>versão <b class="num">{mapping.version}</b></span>
    <span>{mapping.entries.length} variável(is)</span>
  </p>

  {#each mapping.entries as e (e.semantic_tag)}
    {@const meta = tagCatalog.meta(e.semantic_tag)}
    {@const st = status(e)}
    {@const isOpen = open[e.semantic_tag] ?? false}
    <section class="entry" data-testid={`mapping-entry-${e.semantic_tag}`} data-status={st.tone}>
      <button
        type="button"
        class="entry-head"
        aria-expanded={isOpen}
        aria-controls={`${uid}-${e.semantic_tag}`}
        onclick={() => (open[e.semantic_tag] = !isOpen)}
      >
        <span class="who">
          <b>{meta.label_pt}</b>
          <span class="code num">{e.semantic_tag}</span>
        </span>
        <span class="where num">{summary(e)}</span>
        <span class="badge" data-tone={st.tone}>{st.text}</span>
        <span class="chev" class:open={isOpen} aria-hidden="true"><ChevronDown size={18} /></span>
      </button>

      {#if isOpen}
        <div class="fields" id={`${uid}-${e.semantic_tag}`}>
          {#if driver === 'modbus_tcp'}
            {@const a = view(e)}
            <label>Área
              <select disabled={readonly} value={String(a.area ?? 'holding')} onchange={(ev) => { ensure(e).area = ev.currentTarget.value; onEdit(e) }} data-testid={`map-${e.semantic_tag}-area`}>
                {#each MODBUS_AREAS as ar (ar.value)}<option value={ar.value}>{ar.label}</option>{/each}
              </select>
            </label>
            <label>Endereço (base 0)
              <input type="number" min="0" max="65535" inputmode="numeric" disabled={readonly} value={num(a.address)} oninput={(ev) => { setNum(e, 'address', ev.currentTarget.value, false); onEdit(e) }} data-testid={`map-${e.semantic_tag}-address`} />
            </label>
            <label>Registradores
              <input type="number" min="1" max="125" inputmode="numeric" placeholder="pelo tipo" disabled={readonly} value={num(a.count)} oninput={(ev) => { setNum(e, 'count', ev.currentTarget.value); onEdit(e) }} />
            </label>
            <label>Bit (opcional)
              <input type="number" min="0" max="31" inputmode="numeric" disabled={readonly} value={num(a.bit)} oninput={(ev) => { setNum(e, 'bit', ev.currentTarget.value); onEdit(e) }} />
            </label>
          {:else if driver === 'ethernet_ip'}
            {@const a = view(e)}
            <label>Classe
              <input type="number" min="1" max="65535" inputmode="numeric" disabled={readonly} value={num(a.class)} oninput={(ev) => { setNum(e, 'class', ev.currentTarget.value, false); onEdit(e) }} data-testid={`map-${e.semantic_tag}-class`} />
            </label>
            <label>Instância
              <input type="number" min="0" max="65535" inputmode="numeric" disabled={readonly} value={num(a.instance)} oninput={(ev) => { setNum(e, 'instance', ev.currentTarget.value, false); onEdit(e) }} data-testid={`map-${e.semantic_tag}-instance`} />
            </label>
            <label>Atributo
              <input type="number" min="1" max="65535" inputmode="numeric" disabled={readonly} value={num(a.attribute)} oninput={(ev) => { setNum(e, 'attribute', ev.currentTarget.value, false); onEdit(e) }} data-testid={`map-${e.semantic_tag}-attribute`} />
            </label>
            <label>Byte inicial
              <input type="number" min="0" inputmode="numeric" disabled={readonly} value={num(a.offset)} oninput={(ev) => { setNum(e, 'offset', ev.currentTarget.value); onEdit(e) }} data-testid={`map-${e.semantic_tag}-offset`} />
            </label>
            <label>Tamanho (bytes)
              <input type="number" min="1" inputmode="numeric" placeholder="pelo tipo" disabled={readonly} value={num(a.length)} oninput={(ev) => { setNum(e, 'length', ev.currentTarget.value); onEdit(e) }} />
            </label>
            <label>Bit (opcional)
              <input type="number" min="0" max="31" inputmode="numeric" disabled={readonly} value={num(a.bit)} oninput={(ev) => { setNum(e, 'bit', ev.currentTarget.value); onEdit(e) }} />
            </label>
          {/if}
          <label>Tipo de dado
            <select disabled={readonly} value={e.datatype} onchange={(ev) => { e.datatype = ev.currentTarget.value as DataTypeName | 'UNKNOWN'; onEdit(e) }} data-testid={`map-${e.semantic_tag}-datatype`}>
              <option value="UNKNOWN">Não definido</option>
              {#each Object.entries(DATATYPE_PT) as [value, label] (value)}<option {value}>{label}</option>{/each}
            </select>
          </label>
          <label>Ordem dos bytes
            <select disabled={readonly} value={e.endianness} onchange={(ev) => { e.endianness = ev.currentTarget.value as EndiannessName | 'UNKNOWN'; onEdit(e) }} data-testid={`map-${e.semantic_tag}-endianness`}>
              <option value="UNKNOWN">Não definida</option>
              {#each Object.entries(ENDIANNESS_PT) as [value, label] (value)}<option {value}>{label}</option>{/each}
            </select>
          </label>
          <label>Escala: fator
            <input type="number" step="any" inputmode="decimal" placeholder="não definida" disabled={readonly} value={scaleValue(e, 'factor')} oninput={(ev) => { setScale(e, 'factor', ev.currentTarget.value); onEdit(e) }} />
          </label>
          <label>Escala: deslocamento
            <input type="number" step="any" inputmode="decimal" disabled={readonly || e.scale === 'UNKNOWN'} value={scaleValue(e, 'offset')} oninput={(ev) => { setScale(e, 'offset', ev.currentTarget.value); onEdit(e) }} />
          </label>
          <label>Faixa válida: mínimo
            <input type="number" step="any" inputmode="decimal" disabled={readonly} value={e.valid_min ?? ''} oninput={(ev) => setRange(e, 'valid_min', ev.currentTarget.value)} />
          </label>
          <label>Faixa válida: máximo
            <input type="number" step="any" inputmode="decimal" disabled={readonly} value={e.valid_max ?? ''} oninput={(ev) => setRange(e, 'valid_max', ev.currentTarget.value)} />
          </label>
          <label class="wide">De onde veio o endereço (documento, revisão, página)
            <input type="text" maxlength="300" disabled={readonly} value={e.source === 'UNKNOWN' ? '' : e.source} placeholder="ex.: [documento da máquina], rev. [x], p. [y]" oninput={(ev) => { e.source = ev.currentTarget.value.trim() || 'UNKNOWN' }} data-testid={`map-${e.semantic_tag}-source`} />
          </label>
          {#if e.validation}
            {@const forja = typeof e.validation.forja_value === 'number' ? e.validation.forja_value : Number(e.validation.forja_value)}
            {@const kcmNum = Number(String(e.validation.kcm_value).replace(/\./g, '').replace(',', '.'))}
            <p class="wide val" data-matched={e.validation.matched}>
              Conferência por {e.validation.validated_by}: Forja {fmtNumber(forja, meta.decimals)} {meta.unit} ×
              KCM {e.validation.kcm_value} {meta.unit}{#if Number.isFinite(forja) && Number.isFinite(kcmNum)} (diferença {fmtNumber(kcmNum - forja, meta.decimals + 1)}){/if}
              · {e.validation.matched ? 'confere' : 'diverge'}
            </p>
          {/if}
          {#if !readonly}
            <div class="wide row-actions">
              <button type="button" class="ghost" onclick={() => clearAddress(e)}>Limpar endereço</button>
              <button type="button" class="ghost danger" aria-label="Retirar esta variável do mapping" onclick={() => remove(e.semantic_tag)}>
                <Trash2 size={16} aria-hidden="true" /> Retirar do mapping
              </button>
            </div>
          {/if}
        </div>
      {/if}
    </section>
  {/each}

  {#if !readonly && available.length}
    <div class="add">
      <label>Acrescentar variável
        <select bind:value={toAdd} data-testid="mapping-add-select">
          <option value="">Escolha…</option>
          {#each available as t (t)}<option value={t}>{tagCatalog.meta(t).label_pt}</option>{/each}
        </select>
      </label>
      <button type="button" class="ghost" disabled={!toAdd} onclick={add} data-testid="mapping-add">
        <Plus size={16} aria-hidden="true" /> Acrescentar
      </button>
    </div>
  {/if}
</div>

<style>
  .editor { display: flex; flex-direction: column; gap: var(--sp-2); min-width: 0; }
  .meta { display: flex; flex-wrap: wrap; gap: var(--sp-2) var(--sp-4); margin: 0 0 var(--sp-2); color: var(--text-3); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .meta b { color: var(--text-2); font-weight: 500; }
  .entry { border: 1px solid var(--border-1); border-radius: var(--r-3); background: var(--surf-1); min-width: 0; }
  .entry[data-status='ok'] { border-left: 3px solid var(--st-ok); }
  .entry[data-status='warn'] { border-left: 3px solid var(--st-warn); }
  .entry[data-status='crit'] { border-left: 3px solid var(--st-crit); }
  .entry-head {
    display: grid;
    grid-template-columns: minmax(140px, 1fr) minmax(0, 2fr) auto 24px;
    align-items: center;
    gap: var(--sp-3);
    width: 100%;
    min-height: var(--touch);
    padding: var(--sp-2) var(--sp-3);
    border: 0;
    background: transparent;
    color: var(--text-1);
    text-align: left;
    cursor: pointer;
  }
  .who { display: flex; flex-direction: column; min-width: 0; }
  .who b { font: 600 var(--fs-body) / var(--lh-body) var(--font-ui); }
  .code { color: var(--text-3); font-size: var(--fs-mono-sm); }
  .where { color: var(--text-2); font-size: var(--fs-mono-sm); overflow-wrap: anywhere; }
  .badge { padding: 2px 8px; border-radius: var(--r-pill); border: 1px solid var(--border-2); color: var(--text-2); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); white-space: nowrap; }
  .badge[data-tone='ok'] { color: var(--st-ok); border-color: var(--st-ok); }
  .badge[data-tone='warn'] { color: var(--st-warn); border-color: var(--st-warn); }
  .badge[data-tone='crit'] { color: var(--st-crit); border-color: var(--st-crit); }
  .chev { display: inline-grid; color: var(--text-3); transition: transform var(--dur-base) var(--ease-out); }
  .chev.open { transform: rotate(180deg); }
  .fields {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
    gap: var(--sp-3);
    padding: var(--sp-3);
    border-top: 1px solid var(--border-1);
    animation: open var(--dur-base) var(--ease-out) both;
  }
  @keyframes open { from { opacity: 0; transform: translateY(-2px); } to { opacity: 1; transform: none; } }
  label { display: flex; flex-direction: column; gap: 4px; min-width: 0; color: var(--text-3); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .wide { grid-column: 1 / -1; }
  input, select {
    width: 100%;
    min-height: var(--touch);
    padding: 0 var(--sp-2);
    border: 1px solid var(--border-input);
    border-radius: var(--r-2);
    background: var(--surf-2);
    color: var(--text-1);
    font: 16px / 1.2 var(--font-ui);
  }
  input[type='number'] { font-family: var(--font-mono); }
  input:disabled, select:disabled { opacity: 0.6; }
  .val { margin: 0; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .val[data-matched='false'] { color: var(--st-crit); }
  .row-actions { display: flex; flex-wrap: wrap; gap: var(--sp-2); justify-content: flex-end; }
  .ghost {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    min-height: var(--touch);
    padding: 0 var(--sp-3);
    border: 1px solid var(--border-2);
    border-radius: var(--r-3);
    background: var(--surf-1);
    color: var(--text-1);
    font: 500 var(--fs-body) / 1 var(--font-ui);
    cursor: pointer;
  }
  .ghost:disabled { opacity: 0.5; cursor: not-allowed; }
  .ghost.danger { color: var(--st-crit); }
  .add { display: flex; flex-wrap: wrap; align-items: flex-end; gap: var(--sp-2); margin-top: var(--sp-2); }
  .add label { flex: 1 1 260px; }
  @media (max-width: 767px) {
    .entry-head { grid-template-columns: minmax(0, 1fr) 24px; }
    .entry-head .where, .entry-head .badge { grid-column: 1 / 2; }
    .entry-head .chev { grid-row: 1; grid-column: 2; }
    .fields { grid-template-columns: minmax(0, 1fr); }
  }
</style>
