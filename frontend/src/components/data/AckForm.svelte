<script lang="ts">
  /** Reconhecer um evento ou aviso da Forja: registra quem viu e quando (auditado). Não altera o KCM. */
  import Check from '@lucide/svelte/icons/check'
  import { errorMessage, type EventView } from '../../lib/api'
  import { ACK_USER_PATTERN, intelligenceApi, rememberUser, rememberedUser } from '../../lib/intelligence'

  let {
    event,
    ondone,
  }: { event: EventView; ondone?: (updated: EventView) => void } = $props()

  let editing = $state(false)
  let saving = $state(false)
  let user = $state('')
  let note = $state('')
  let error = $state<string | null>(null)
  let shake = $state(0)
  const ids = $props.id()

  const userOk = $derived(ACK_USER_PATTERN.test(user.trim()))

  function start(): void {
    user = rememberedUser()
    note = ''
    error = null
    editing = true
  }

  async function confirm(e: SubmitEvent): Promise<void> {
    e.preventDefault()
    if (!userOk) {
      error = 'Informe seu nome (letras, números, espaço, ponto, @ ou hífen).'
      shake += 1
      return
    }
    saving = true
    error = null
    try {
      const updated = await intelligenceApi.ack(event.id, user.trim(), note.trim())
      rememberUser(user.trim())
      editing = false
      ondone?.(updated)
    } catch (err) {
      error = errorMessage(err)
      shake += 1
    } finally {
      saving = false
    }
  }
</script>

{#if event.status === 'ACKNOWLEDGED'}
  <p class="done" data-testid="ack-done">
    <span class="tick" aria-hidden="true"><Check size={14} /></span>
    Reconhecido por {event.acked_by}
  </p>
{:else if event.status === 'OPEN' && !editing}
  <button class="btn ghost" type="button" onclick={start} data-testid="ack-start">Reconhecer</button>
{:else if editing}
  {#key shake}
    <form class="ack" class:shake={shake > 0} onsubmit={confirm} data-testid="ack-form">
      <p class="hint">Fica registrado quem viu e quando. Não altera nada no KCM.</p>
      <label for="{ids}-user">Seu nome</label>
      <input
        id="{ids}-user"
        bind:value={user}
        maxlength="64"
        autocomplete="name"
        aria-invalid={error != null && !userOk}
        data-testid="ack-user"
      />
      <label for="{ids}-note">Observação (opcional)</label>
      <textarea id="{ids}-note" rows="2" maxlength="2000" bind:value={note} data-testid="ack-note"></textarea>
      {#if error}<p class="err" role="alert">{error}</p>{/if}
      <div class="row">
        <button class="btn primary" type="submit" disabled={saving} data-testid="ack-confirm">
          {saving ? 'Registrando…' : 'Confirmar reconhecimento'}
        </button>
        <button class="btn ghost" type="button" onclick={() => (editing = false)} disabled={saving}>Cancelar</button>
      </div>
    </form>
  {/key}
{/if}

<style>
  .ack {
    display: flex;
    flex-direction: column;
    gap: var(--sp-2);
    margin-top: var(--sp-2);
    padding: var(--sp-3);
    border: 1px solid var(--border-2);
    border-radius: var(--r-3);
    background: var(--surf-2);
    animation: open var(--dur-base) var(--ease-out);
  }
  @keyframes open {
    from { opacity: 0; transform: translateY(-4px); }
    to { opacity: 1; transform: none; }
  }
  .ack.shake { animation: shake 360ms var(--ease-std); }
  @keyframes shake {
    20% { transform: translateX(-6px); }
    40% { transform: translateX(5px); }
    60% { transform: translateX(-3px); }
    80% { transform: translateX(2px); }
  }
  label {
    color: var(--text-2);
    font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui);
  }
  input, textarea {
    width: 100%;
    min-height: var(--touch);
    padding: var(--sp-2);
    border: 1px solid var(--border-input);
    border-radius: var(--r-2);
    background: var(--surf-1);
    color: var(--text-1);
    font: 16px / 1.3 var(--font-ui);
  }
  input[aria-invalid='true'] { border-color: var(--st-crit); }
  .hint { margin: 0; color: var(--text-2); font: var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .err { margin: 0; color: var(--st-crit); font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui); }
  .row { display: flex; flex-wrap: wrap; gap: var(--sp-2); margin-top: var(--sp-1); }
  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: var(--touch);
    padding: 0 var(--sp-4);
    border-radius: var(--r-3);
    font: 600 var(--fs-body) / 1.2 var(--font-ui);
    cursor: pointer;
    transition: background-color var(--dur-micro) var(--ease-std), transform var(--dur-micro) var(--ease-std);
  }
  .btn:active:not(:disabled) { transform: scale(0.97); }
  .btn:disabled { opacity: 0.55; cursor: not-allowed; }
  .btn.primary { border: 1px solid var(--accent); background: var(--accent); color: var(--on-accent); }
  .btn.ghost { border: 1px solid var(--border-2); background: var(--surf-1); color: var(--text-1); }
  .btn.ghost:hover:not(:disabled) { background: var(--surf-2); }
  .done {
    display: inline-flex;
    align-items: center;
    gap: var(--sp-2);
    margin: 0;
    color: var(--st-info);
    font: 500 var(--fs-caption) / var(--lh-caption) var(--font-ui);
  }
  .tick {
    display: inline-grid;
    place-items: center;
    width: 20px;
    height: 20px;
    border-radius: var(--r-pill);
    background: var(--st-info-bg);
    animation: pop 420ms var(--ease-out);
  }
  @keyframes pop {
    0% { transform: scale(0.4); opacity: 0; }
    60% { transform: scale(1.18); opacity: 1; }
    100% { transform: scale(1); }
  }
</style>
