import { defineConfig, type Plugin } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

/** O runtime do Svelte embute links de documentação nas mensagens de erro
 *  (`https://svelte.dev/e/<codigo>`). Nada os busca, mas a regra do produto é zero URL remota
 *  no build. Este plugin tira o protocolo, mantendo o código do erro legível no console. */
function stripSvelteErrorUrls(): Plugin {
  return {
    name: 'forja-strip-svelte-error-urls',
    apply: 'build',
    renderChunk(code) {
      if (!code.includes('https://svelte.dev/e/')) return null
      return { code: code.replaceAll('https://svelte.dev/e/', 'svelte.dev/e/'), map: null }
    },
  }
}

// Build estático servido pelo FastAPI em /app. Zero CDN: tudo que entra aqui é empacotado.
export default defineConfig({
  plugins: [svelte(), stripSvelteErrorUrls()],
  base: '/app/',
  build: {
    outDir: '../src/forja/ui/dist',
    emptyOutDir: true,
    sourcemap: false,
    target: 'es2022',
  },
  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      '/api': { target: process.env.FORJA_API ?? 'http://127.0.0.1:8765', changeOrigin: false },
      '/health': { target: process.env.FORJA_API ?? 'http://127.0.0.1:8765', changeOrigin: false },
    },
  },
})
