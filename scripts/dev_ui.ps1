<#
.SYNOPSIS
  Sobe o Vite em modo desenvolvimento com proxy para o Edge local.
.DESCRIPTION
  O front roda em http://localhost:5173/app/ e encaminha /api e /health para o Edge
  (padrão http://127.0.0.1:8765). Suba o Edge antes: .\.venv\Scripts\forja.exe run [--port N].
.EXAMPLE
  .\scripts\dev_ui.ps1
  .\scripts\dev_ui.ps1 -ApiPort 8799
#>
[CmdletBinding()]
param(
  [int]$ApiPort = 8765,
  [string]$ApiHost = '127.0.0.1'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path $root 'frontend'

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
  Write-Error 'npm não encontrado. Instale o Node.js (LTS) e abra um terminal novo.'
}
if (-not (Test-Path (Join-Path $frontend 'node_modules'))) {
  Write-Host 'node_modules ausente; rodando npm ci...' -ForegroundColor Yellow
  Push-Location $frontend
  try { npm ci; if ($LASTEXITCODE -ne 0) { throw 'npm ci falhou' } } finally { Pop-Location }
}

$env:FORJA_API = "http://$ApiHost`:$ApiPort"
Write-Host "Proxy /api e /health -> $env:FORJA_API" -ForegroundColor Cyan
Write-Host 'Interface: http://localhost:5173/app/plant' -ForegroundColor Cyan

Push-Location $frontend
try {
  npm run dev
}
finally {
  Pop-Location
}
