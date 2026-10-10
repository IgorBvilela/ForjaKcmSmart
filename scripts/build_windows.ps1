<#
.SYNOPSIS
  Gera o pacote de instalação do Windows: build\release\ForjaKCM-<versão>-win64.zip.
.DESCRIPTION
  Etapas, todas locais:
    1. interface: npm ci + npm run build (scripts\build_ui.ps1), salvo com -SkipUi;
    2. executável: PyInstaller (packaging\forja.spec) em modo pasta, com PYTHONHASHSEED fixo;
    3. teste do executável: init numa pasta temporária, sobe o Edge numa porta livre e confere
       /health = ok, /app = 200 e /docs = 404 (pacote nunca sai em modo desenvolvimento);
    4. pacote: programa + install.ps1 + uninstall.ps1 + LEIA-ME.txt + TERCEIROS.txt +
       SHA256SUMS.txt, compactado em .zip.
  Dependências travadas: requirements.lock.txt (Python) e frontend\package-lock.json (npm).
.EXAMPLE
  .\scripts\build_windows.ps1
  .\scripts\build_windows.ps1 -SkipUi
#>
[CmdletBinding()]
param(
  [switch]$SkipUi
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
$build = Join-Path $root 'build'
$dist = Join-Path $build 'dist'
$app = Join-Path $dist 'ForjaKCM'
$exe = Join-Path $app 'ForjaKCM.exe'

function Write-Step([string]$Text) { Write-Host "> $Text" -ForegroundColor Cyan }

function Invoke-Native([string]$What, [scriptblock]$Command) {
  # O código de saída decide o resultado. Aviso em stderr não é falha: com a saída redirecionada,
  # o PowerShell 5.1 transformaria cada linha de stderr em erro fatal.
  $saved = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try { & $Command 2>&1 | ForEach-Object { "$_" } }
  finally { $ErrorActionPreference = $saved }
  if ($LASTEXITCODE -ne 0) { throw "$What falhou (código $LASTEXITCODE)." }
}

if (-not (Test-Path -LiteralPath $python)) {
  throw ('Ambiente Python não encontrado em .venv. Crie com: py -3.14 -m venv .venv; ' +
    '.venv\Scripts\python -m pip install -r requirements.lock.txt; ' +
    '.venv\Scripts\python -m pip install -e . --no-deps')
}

if (-not $SkipUi) {
  Write-Step 'Interface'
  & (Join-Path $PSScriptRoot 'build_ui.ps1')
}

Write-Step 'Executável (PyInstaller)'
$env:PYTHONHASHSEED = '0'
Invoke-Native 'PyInstaller' {
  & $python -m PyInstaller (Join-Path $root 'packaging\forja.spec') --clean --noconfirm `
    --distpath $dist --workpath (Join-Path $build 'pyinstaller') --log-level WARN
}
if (-not (Test-Path -LiteralPath $exe)) { throw "Build terminou sem $exe." }
$version = (& $exe --version).Split(' ')[-1].Trim()

Write-Step 'Teste do executável'
$smokeHome = Join-Path $build 'smoke_home'
if (Test-Path -LiteralPath $smokeHome) { Remove-Item -LiteralPath $smokeHome -Recurse -Force }
Invoke-Native 'init' { & $exe init --home $smokeHome }
$listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, 0)
$listener.Start()
$port = $listener.LocalEndpoint.Port
$listener.Stop()
$edge = Start-Process -FilePath $exe -PassThru -WindowStyle Hidden `
  -ArgumentList @('run', '--home', "`"$smokeHome`"", '--port', $port)
try {
  $base = "http://127.0.0.1:$port"
  $healthy = $false
  for ($i = 0; $i -lt 60 -and -not $healthy; $i++) {
    try {
      $health = Invoke-WebRequest -UseBasicParsing -Uri "$base/health" -TimeoutSec 3
      $healthy = $health.Content -match '"status"\s*:\s*"ok"'
    }
    catch { Start-Sleep -Seconds 1 }
  }
  if (-not $healthy) { throw "O executável não respondeu em $base/health." }
  $ui = Invoke-WebRequest -UseBasicParsing -Uri "$base/app" -TimeoutSec 5
  if ($ui.StatusCode -ne 200) { throw "/app respondeu $($ui.StatusCode)." }
  $docsStatus = 0
  try {
    $docsStatus = (Invoke-WebRequest -UseBasicParsing -Uri "$base/docs" -TimeoutSec 5).StatusCode
  }
  catch { $docsStatus = [int]$_.Exception.Response.StatusCode }
  if ($docsStatus -ne 404) {
    throw "/docs respondeu ${docsStatus}; o pacote saiu em modo desenvolvimento."
  }
  Write-Host "OK: /health, /app e /docs fechado (porta $port)" -ForegroundColor Green
}
finally {
  if (-not $edge.HasExited) { Stop-Process -Id $edge.Id -Force }
}

Write-Step 'Pacote'
$releaseName = "ForjaKCM-$version"
$release = Join-Path $build "release\$releaseName"
$zip = Join-Path $build "release\$releaseName-win64.zip"
foreach ($old in @($release, $zip)) {
  if (Test-Path -LiteralPath $old) { Remove-Item -LiteralPath $old -Recurse -Force }
}
New-Item -ItemType Directory -Force -Path $release | Out-Null
Copy-Item -LiteralPath $app -Destination (Join-Path $release 'ForjaKCM') -Recurse
foreach ($file in @('install.ps1', 'uninstall.ps1')) {
  Copy-Item -LiteralPath (Join-Path $root "packaging\$file") -Destination $release
}
$readme = (Get-Content -LiteralPath (Join-Path $root 'packaging\LEIA-ME.txt') -Raw -Encoding UTF8)
$readme = $readme.Replace('@VERSAO@', $version)
$utf8Bom = New-Object Text.UTF8Encoding($true)
[IO.File]::WriteAllText((Join-Path $release 'LEIA-ME.txt'), $readme, $utf8Bom)
Invoke-Native 'TERCEIROS.txt' {
  & $python (Join-Path $root 'packaging\third_party.py') (Join-Path $release 'TERCEIROS.txt')
}

$sums = Get-ChildItem -LiteralPath $release -Recurse -File | Sort-Object FullName | ForEach-Object {
  $relative = $_.FullName.Substring($release.Length + 1).Replace('\', '/')
  "$((Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLower())  $relative"
}
[IO.File]::WriteAllLines((Join-Path $release 'SHA256SUMS.txt'), [string[]]$sums)
Compress-Archive -Path (Join-Path $release '*') -DestinationPath $zip

$zipHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $zip).Hash.ToLower()
$sizeMb = [math]::Round((Get-Item -LiteralPath $zip).Length / 1MB, 1)
Write-Host ''
Write-Host "OK: $zip ($sizeMb MB)" -ForegroundColor Green
Write-Host "SHA-256 do .zip: $zipHash"
Write-Host 'Instalação: extrair o .zip e rodar install.ps1 como Administrador (ver LEIA-ME.txt).'
