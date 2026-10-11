/* Tema antes da primeira pintura: a escolha guardada neste navegador ou, sem escolha, o tema do
   Windows. Mesma regra de src/lib/theme.svelte.ts. Arquivo separado porque o CSP só aceita
   script servido pelo próprio Edge (nada embutido no HTML). */
(function () {
  var escolha = null
  try {
    escolha = window.localStorage.getItem('forja.tema')
  } catch (e) {
    escolha = null
  }
  var claro =
    escolha === 'light' ||
    (escolha !== 'dark' && !!window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches)
  document.documentElement.setAttribute('data-theme', claro ? 'light' : 'dark')
  var cor = document.querySelector('meta[name="theme-color"]')
  if (cor) cor.setAttribute('content', claro ? '#FFFFFF' : '#1F1F1F')
})()
