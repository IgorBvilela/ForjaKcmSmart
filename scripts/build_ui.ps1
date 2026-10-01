<#
.SYNOPSIS
  Compila a interface (frontend/) para src/forja/ui/dist, que o FastAPI serve em /app.
.DESCRIPTION
  Roda `npm ci` (instalação limpa, travada no package-lock) e `npm run build`.
  Tudo local: sem CDN, sem fonte remota. Use -SkipInstall para pular o npm ci.
.EXAMPLE
  .\scripts\build_ui.ps1
  .\scripts\build_ui.ps1 -SkipInstall
#>
[CmdletBinding()]
param(
  [switch]$SkipInstall
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path $root 'frontend'
$dist = Join-Path $root 'src\forja\ui\dist'

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
  Write-Error 'npm não encontrado. Instale o Node.js (LTS) e abra um terminal novo.'
}

Push-Location $frontend
try {
  if (-not $SkipInstall) {
    Write-Host '> npm ci' -ForegroundColor Cyan
    npm ci
    if ($LASTEXITCODE -ne 0) { throw "npm ci falhou (código $LASTEXITCODE)" }
  }
  Write-Host '> npm run build' -ForegroundColor Cyan
  npm run build
  if ($LASTEXITCODE -ne 0) { throw "npm run build falhou (código $LASTEXITCODE)" }
}
finally {
  Pop-Location
}

if (-not (Test-Path (Join-Path $dist 'index.html'))) {
  throw "Build terminou sem index.html em $dist"
}

# Zero URL remota no código. Exceções: namespaces XML (identificadores, não endereços) e os
# textos das licenças OFL/MIT, que são o aviso legal que acompanha as fontes redistribuídas.
$remote = Get-ChildItem -Path $dist -Recurse -File |
  Where-Object { $_.FullName -notlike (Join-Path $dist 'licenses\*') } |
  Select-String -Pattern 'https?://' |
  Where-Object { $_.Line -notmatch 'https?://www\.w3\.org/' }
if ($remote) {
  $remote | ForEach-Object { Write-Warning "URL remota em $($_.Path):$($_.LineNumber)" }
  throw 'O build referencia URL remota. A interface deve ser 100% local.'
}

Write-Host "OK: interface compilada em $dist" -ForegroundColor Green
Write-Host 'Abra http://127.0.0.1:8765/app/plant com o Edge em execução (forja run).'
