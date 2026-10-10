<#
.SYNOPSIS
  Remove o Forja KCM Intelligence deste computador. Por padrão, preserva os dados.
.DESCRIPTION
  Rode em um PowerShell aberto como Administrador:
    Set-ExecutionPolicy -Scope Process Bypass -Force
    .\uninstall.ps1

  Para o serviço, remove o registro do serviço, a fonte do Visualizador de Eventos, os atalhos e a
  pasta do programa. A pasta de dados (histórico, configuração, logs e backups) fica intacta, e
  uma instalação nova reaproveita tudo. Com -RemoveData, apaga também os dados, após confirmação.
.PARAMETER InstallDir
  Pasta do programa.
.PARAMETER DataDir
  Pasta de dados. Sem este parâmetro, usa a pasta registrada no serviço ou a padrão.
.PARAMETER RemoveData
  Apaga também a pasta de dados. Pede para digitar APAGAR, exceto com -Force.
.PARAMETER Force
  Não pede confirmação para -RemoveData.
#>
[CmdletBinding()]
param(
  [string]$InstallDir = (Join-Path $env:ProgramFiles 'ForjaKCM'),
  [string]$DataDir,
  [switch]$RemoveData,
  [switch]$Force
)

$ErrorActionPreference = 'Stop'
$ServiceName = 'ForjaKCM'
$ExeName = 'ForjaKCM.exe'

function Write-Step([string]$Text) { Write-Host "> $Text" -ForegroundColor Cyan }
function Write-Ok([string]$Text) { Write-Host "OK: $Text" -ForegroundColor Green }

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw ('Abra o PowerShell como Administrador (botão direito > Executar como administrador) ' +
    'e rode de novo.')
}

$serviceKey = "HKLM:\SYSTEM\CurrentControlSet\Services\$ServiceName"
if (-not $DataDir) {
  $environment = (Get-ItemProperty -Path $serviceKey -Name Environment -ErrorAction SilentlyContinue).Environment
  $fromService = $environment | Where-Object { $_ -like 'FORJA_HOME=*' } | Select-Object -First 1
  if ($fromService) { $DataDir = $fromService.Substring('FORJA_HOME='.Length) }
  else { $DataDir = Join-Path $env:ProgramData 'ForjaKCM' }
}
$InstallDir = [IO.Path]::GetFullPath($InstallDir).TrimEnd('\')
$DataDir = [IO.Path]::GetFullPath($DataDir).TrimEnd('\')

$service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($service) {
  if ($service.Status -ne 'Stopped') {
    Write-Step 'Parando o serviço'
    Stop-Service -Name $ServiceName -Force
    $service.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(90))
  }
  Write-Step 'Removendo o serviço'
  & sc.exe delete $ServiceName | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "sc.exe delete falhou (código $LASTEXITCODE)." }
}

$eventKey = "HKLM:\SYSTEM\CurrentControlSet\Services\EventLog\Application\$ServiceName"
if (Test-Path $eventKey) { Remove-Item -Path $eventKey -Recurse -Force }

$shortcutFolders = @(
  [Environment]::GetFolderPath('CommonDesktopDirectory'),
  (Join-Path ([Environment]::GetFolderPath('CommonStartMenu')) 'Programs')
)
foreach ($folder in $shortcutFolders) {
  $link = Join-Path $folder 'Forja KCM.url'
  if (Test-Path -LiteralPath $link) { Remove-Item -LiteralPath $link -Force }
}

if (Test-Path -LiteralPath $InstallDir) {
  if (-not (Test-Path -LiteralPath (Join-Path $InstallDir $ExeName))) {
    throw "$InstallDir não parece ser uma instalação do Forja KCM ($ExeName ausente). Nada apagado."
  }
  Write-Step "Removendo o programa de $InstallDir"
  Remove-Item -LiteralPath $InstallDir -Recurse -Force
}

if (-not $RemoveData) {
  Write-Ok 'Forja KCM Intelligence removido.'
  Write-Host "Dados preservados em $DataDir (histórico, configuração, logs e backups)."
  return
}
if (-not (Test-Path -LiteralPath $DataDir)) {
  Write-Ok "Forja KCM Intelligence removido. Pasta de dados $DataDir não existe."
  return
}
if (-not (Test-Path -LiteralPath (Join-Path $DataDir 'config\forja.yaml'))) {
  throw "$DataDir não parece ser uma pasta de dados do Forja KCM (config\forja.yaml ausente). Nada apagado."
}
if (-not $Force) {
  Write-Warning "Isto apaga histórico, configuração, logs e backups em $DataDir."
  $answer = Read-Host 'Digite APAGAR para confirmar'
  if ($answer -cne 'APAGAR') {
    Write-Ok 'Forja KCM Intelligence removido. Dados preservados.'
    return
  }
}
Remove-Item -LiteralPath $DataDir -Recurse -Force
Write-Ok "Forja KCM Intelligence e dados em $DataDir removidos."
