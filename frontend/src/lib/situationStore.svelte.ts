/** Situação da planta compartilhada: a tela Agora e o contador do menu leem a mesma resposta,
 *  então os dois números nunca discordam. Atualiza a cada 15 s e logo depois de evento,
 *  diagnóstico ou mudança de estado (quem chama `refreshSoon` é o App, ouvindo o SSE), no
 *  máximo uma vez a cada 5 s: com evento aberto o SSE manda uma atualização por segundo. */
import { errorMessage } from './api'
import { situationApi, type SituationResponse } from './situation'

const REFRESH_MS = 15_000
const DEBOUNCE_MS = 300
const MIN_GAP_MS = 5_000

class SituationStore {
  data = $state<SituationResponse | null>(null)
  error = $state<string | null>(null)
  /** Dosadores que pedem atenção: o mesmo número da frase da tela Agora. */
  attention: number = $derived(this.data?.summary.attention ?? 0)

  #interval: number | undefined
  #debounce: number | undefined
  #lastLoadAt = 0
  #started = false

  start(): void {
    if (this.#started) return
    this.#started = true
    void this.load()
    this.#interval = window.setInterval(() => void this.load(), REFRESH_MS)
  }

  stop(): void {
    if (this.#interval) clearInterval(this.#interval)
    if (this.#debounce) clearTimeout(this.#debounce)
    this.#debounce = undefined
    this.#started = false
  }

  /** Várias mensagens seguidas do SSE viram uma consulta só, nunca antes de 5 s da anterior. */
  refreshSoon(): void {
    if (!this.#started || this.#debounce) return
    const wait = Math.max(DEBOUNCE_MS, this.#lastLoadAt + MIN_GAP_MS - Date.now())
    this.#debounce = window.setTimeout(() => {
      this.#debounce = undefined
      void this.load()
    }, wait)
  }

  async load(): Promise<void> {
    this.#lastLoadAt = Date.now()
    try {
      this.data = await situationApi.get()
      this.error = null
    } catch (err) {
      this.error = errorMessage(err)
    }
  }
}

export const situation = new SituationStore()
