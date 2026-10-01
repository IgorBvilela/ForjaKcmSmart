import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

// Build estático servido pelo FastAPI em /app. Zero CDN: tudo que entra aqui é empacotado.
export default defineConfig({
  plugins: [svelte()],
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
