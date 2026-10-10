<#
.SYNOPSIS
  Instala ou atualiza o Forja KCM Intelligence neste computador (somente leitura).
.DESCRIPTION
  Rode em um PowerShell aberto como Administrador, dentro da pasta extraída do pacote:
    Set-ExecutionPolicy -Scope Process Bypass -Force
    .\install.ps1

  Instalação nova:
    - copia o programa para InstallDir (padrão: C:\Program Files\ForjaKCM);
    - prepara a pasta de dados em DataDir (padrão: C:\ProgramData\ForjaKCM) com a configuração
      inicial; bancos, logs e backups ficam em DataDir\var;
    - registra o serviço "Forja KCM Intelligence" (início automático atrasado, conta
      NT AUTHORITY\LocalService, reinício automático após falha) e o inicia;
    - cria o atalho "Forja KCM" na Área de Trabalho pública e no Menu Iniciar.

  Atualização (programa já instalado):
    - para o serviço e cria um backup dos bancos com a versão instalada antes de trocar o programa;
    - a pasta de dados nunca é apagada e a configuração existente nunca é sobrescrita.

  Nenhum passo fala com o KCM. Não precisa de internet.
.PARAMETER InstallDir
  Pasta do programa. Trocada inteira a cada atualização.
.PARAMETER DataDir
  Pasta de dados: configuração, conhecimento, bancos, logs e backups. Fora da pasta do programa.
.PARAMETER NoService
  Copia o programa e prepara os dados sem registrar o serviço nem criar atalhos (teste de bancada).
.PARAMETER NoShortcut
  Não cria os atalhos.
.EXAMPLE
  .\install.ps1
.EXAMPLE
  .\install.ps1 -DataDir D:\ForjaKCM
#>
[CmdletBinding()]
param(
  [string]$InstallDir = (Join-Path $env:ProgramFiles 'ForjaKCM'),
  [string]$DataDir = (Join-Path $env:ProgramData 'ForjaKCM'),
  [switch]$NoService,
  [switch]$NoShortcut
)

$ErrorActionPreference = 'Stop'
$ServiceName = 'ForjaKCM'
$DisplayName = 'Forja KCM Intelligence'
$Description = 'Observador somente leitura de controladores KCM: coleta, histórico, eventos e ' +
  'diagnóstico. Não envia comando ao equipamento.'
$ExeName = 'ForjaKCM.exe'
$ServiceAccount = 'NT AUTHORITY\LocalService'
$HealthTimeoutS = 60

function Write-Step([string]$Text) { Write-Host "> $Text" -ForegroundColor Cyan }
function Write-Ok([string]$Text) { Write-Host "OK: $Text" -ForegroundColor Green }

function Test-Admin {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($identity)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Invoke-Forja([string]$Exe, [string[]]$Arguments) {
  & $Exe @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "$ExeName $($Arguments -join ' ') falhou (código $LASTEXITCODE)."
  }
}

function Get-ConfiguredPort([string]$ConfigFile) {
  if (Test-Path -LiteralPath $ConfigFile) {
    $match = Select-String -LiteralPath $ConfigFile -Pattern '^\s*bind_port:\s*(\d+)' |
      Select-Object -First 1
    if ($match) { return [int]$match.Matches[0].Groups[1].Value }
  }
  return 8765
}

function Wait-Health([string]$BaseUrl) {
  $deadline = (Get-Date).AddSeconds($HealthTimeoutS)
  while ((Get-Date) -lt $deadline) {
    try {
      $response = Invoke-WebRequest -UseBasicParsing -Uri "$BaseUrl/health" -TimeoutSec 3
      if ($response.StatusCode -eq 200 -and $response.Content -match '"status"\s*:\s*"ok"') {
        return $true
      }
    }
    catch {
      Start-Sleep -Seconds 2
    }
  }
  return $false
}

function Install-ProgramFiles([string]$Source, [string]$Target) {
  # Troca em etapas: a cópia nova fica pronta ao lado antes de a antiga sair. Se a pasta atual
  # estiver em uso, a troca falha antes de apagar qualquer coisa; se a segunda etapa falhar, a
  # versão anterior volta para o lugar.
  $staging = "$Target.novo"
  $previous = "$Target.anterior"
  $targetLeaf = Split-Path $Target -Leaf
  foreach ($leftover in @($staging, $previous)) {
    if (Test-Path -LiteralPath $leftover) { Remove-Item -LiteralPath $leftover -Recurse -Force }
  }
  Copy-Item -LiteralPath $Source -Destination $staging -Recurse
  try {
    if (Test-Path -LiteralPath $Target) {
      Rename-Item -LiteralPath $Target -NewName (Split-Path $previous -Leaf)
    }
  }
  catch {
    Remove-Item -LiteralPath $staging -Recurse -Force
    throw
  }
  try {
    Rename-Item -LiteralPath $staging -NewName $targetLeaf
  }
  catch {
    if (Test-Path -LiteralPath $previous) { Rename-Item -LiteralPath $previous -NewName $targetLeaf }
    throw
  }
  if (Test-Path -LiteralPath $previous) { Remove-Item -LiteralPath $previous -Recurse -Force }
}

# --- conferências antes de mexer em qualquer coisa -------------------------------------------

$source = Join-Path $PSScriptRoot 'ForjaKCM'
if (-not (Test-Path -LiteralPath (Join-Path $source $ExeName))) {
  throw ("Pacote incompleto: $source\$ExeName não encontrado. Extraia o .zip inteiro e rode " +
    'o install.ps1 de dentro da pasta extraída.')
}
$InstallDir = [IO.Path]::GetFullPath($InstallDir).TrimEnd('\')
$DataDir = [IO.Path]::GetFullPath($DataDir).TrimEnd('\')
if ($DataDir -ieq $InstallDir -or $DataDir.StartsWith("$InstallDir\", 'OrdinalIgnoreCase')) {
  throw ('A pasta de dados não pode ficar dentro da pasta do programa: a atualização troca a ' +
    'pasta do programa inteira.')
}
if ((Test-Path -LiteralPath $InstallDir) -and
    -not (Test-Path -LiteralPath (Join-Path $InstallDir $ExeName)) -and
    (Get-ChildItem -LiteralPath $InstallDir -Force | Select-Object -First 1)) {
  throw "$InstallDir já existe e não é uma instalação do Forja KCM. Escolha outra pasta."
}
if (-not $NoService -and -not (Test-Admin)) {
  throw ('Abra o PowerShell como Administrador (botão direito > Executar como administrador) ' +
    'e rode de novo.')
}

$exe = Join-Path $InstallDir $ExeName
$service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
$isUpdate = Test-Path -LiteralPath $exe
$wasRunning = $service -and $service.Status -ne 'Stopped'

# --- atualização: parar o serviço e guardar os bancos antes da troca ---------------------------

if ($wasRunning) {
  Write-Step 'Parando o serviço para atualizar'
  Stop-Service -Name $ServiceName -Force
  $service.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(90))
}
if ($isUpdate -and (Test-Path -LiteralPath $DataDir)) {
  Write-Step 'Backup dos bancos antes da atualização (com a versão instalada)'
  try {
    Invoke-Forja $exe @('backup', 'create', '--home', $DataDir)
  }
  catch {
    if ($wasRunning) { Start-Service -Name $ServiceName }
    throw "Atualização cancelada antes de qualquer troca: o backup falhou. $($_.Exception.Message)"
  }
}

# --- programa -----------------------------------------------------------------------------------

Write-Step "Copiando o programa para $InstallDir"
try {
  Install-ProgramFiles -Source $source -Target $InstallDir
}
catch {
  if ($wasRunning -and (Test-Path -LiteralPath $exe)) { Start-Service -Name $ServiceName }
  throw "Não foi possível trocar o programa (arquivo em uso?). $($_.Exception.Message)"
}

# --- dados --------------------------------------------------------------------------------------

Write-Step "Preparando a pasta de dados em $DataDir"
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
if (-not $NoService) {
  # Administradores e SYSTEM: controle total. Serviço (LocalService): modificar.
  # Usuários: só leitura (a configuração da coleta não pode ser trocada por qualquer conta).
  & icacls.exe $DataDir /inheritance:r /grant:r '*S-1-5-32-544:(OI)(CI)F' '*S-1-5-18:(OI)(CI)F' `
    '*S-1-5-19:(OI)(CI)M' '*S-1-5-32-545:(OI)(CI)RX' /Q | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "icacls falhou ao proteger $DataDir (código $LASTEXITCODE)." }
}
Invoke-Forja $exe @('init', '--home', $DataDir)
$port = Get-ConfiguredPort (Join-Path $DataDir 'config\forja.yaml')
$baseUrl = "http://127.0.0.1:$port"

if ($NoService) {
  Write-Ok "Programa em $InstallDir e dados em $DataDir (sem serviço)."
  Write-Host "Para subir o Edge neste terminal: & `"$exe`" run --home `"$DataDir`""
  Write-Host "Interface: $baseUrl/app"
  return
}

# --- serviço ------------------------------------------------------------------------------------

$binPath = "`"$exe`" service run"
if (-not $service) {
  Write-Step 'Registrando o serviço do Windows'
  New-Service -Name $ServiceName -BinaryPathName $binPath -DisplayName $DisplayName `
    -Description $Description -StartupType Automatic | Out-Null
}
$cim = Get-CimInstance -ClassName Win32_Service -Filter "Name='$ServiceName'"
$change = Invoke-CimMethod -InputObject $cim -MethodName Change -Arguments @{
  PathName      = $binPath
  StartName     = $ServiceAccount
  StartPassword = ''
}
if ($change.ReturnValue -ne 0) {
  throw "Não foi possível ajustar o serviço (Win32_Service.Change retornou $($change.ReturnValue))."
}
& sc.exe config $ServiceName start= delayed-auto | Out-Null
if ($LASTEXITCODE -ne 0) { throw "sc.exe config falhou (código $LASTEXITCODE)." }
& sc.exe failure $ServiceName reset= 86400 actions= restart/60000/restart/60000/restart/300000 |
  Out-Null
if ($LASTEXITCODE -ne 0) { throw "sc.exe failure falhou (código $LASTEXITCODE)." }

# Pasta de dados explícita no ambiente do serviço.
$serviceKey = "HKLM:\SYSTEM\CurrentControlSet\Services\$ServiceName"
New-ItemProperty -Path $serviceKey -Name Environment -PropertyType MultiString `
  -Value @("FORJA_HOME=$DataDir") -Force | Out-Null

# Fonte do Visualizador de Eventos (as mensagens ficam no módulo servicemanager do pacote).
$messageFile = Get-ChildItem -LiteralPath $InstallDir -Recurse -Filter 'servicemanager*.pyd' |
  Select-Object -First 1
if ($messageFile) {
  $eventKey = "HKLM:\SYSTEM\CurrentControlSet\Services\EventLog\Application\$ServiceName"
  if (-not (Test-Path $eventKey)) { New-Item -Path $eventKey | Out-Null }
  New-ItemProperty -Path $eventKey -Name EventMessageFile -PropertyType ExpandString `
    -Value $messageFile.FullName -Force | Out-Null
  New-ItemProperty -Path $eventKey -Name TypesSupported -PropertyType DWord -Value 7 -Force |
    Out-Null
}

Write-Step 'Iniciando o serviço'
try {
  Start-Service -Name $ServiceName
}
catch {
  throw ("O serviço não iniciou. Veja $DataDir\var\logs\forja.log e o Visualizador de Eventos " +
    "(Aplicativo, fonte ForjaKCM). $($_.Exception.Message)")
}
if (Wait-Health $baseUrl) {
  Write-Ok "Interface respondendo em $baseUrl/app"
}
else {
  Write-Warning ("O serviço iniciou, mas $baseUrl/health não respondeu em $HealthTimeoutS s. " +
    "Veja $DataDir\var\logs\forja.log e o Visualizador de Eventos (Aplicativo, fonte ForjaKCM).")
}

# --- atalhos ------------------------------------------------------------------------------------

if (-not $NoShortcut) {
  $shortcut = "[InternetShortcut]`r`nURL=$baseUrl/app`r`n"
  $folders = @(
    [Environment]::GetFolderPath('CommonDesktopDirectory'),
    (Join-Path ([Environment]::GetFolderPath('CommonStartMenu')) 'Programs')
  )
  foreach ($folder in $folders) {
    if ($folder -and (Test-Path -LiteralPath $folder)) {
      Set-Content -LiteralPath (Join-Path $folder 'Forja KCM.url') -Value $shortcut -Encoding ASCII
    }
  }
}

Write-Host ''
if ($isUpdate) { Write-Ok 'Forja KCM Intelligence atualizado (somente leitura).' }
else { Write-Ok 'Forja KCM Intelligence instalado (somente leitura).' }
Write-Host "  Programa:  $InstallDir"
Write-Host "  Dados:     $DataDir  (config, knowledge, var: bancos, logs e backups)"
Write-Host "  Serviço:   $DisplayName (automático, conta LocalService)"
Write-Host "  Interface: $baseUrl/app  (atalho 'Forja KCM')"
if (-not $isUpdate) {
  Write-Host ''
  Write-Host 'Próximo passo: na interface, KCM > Comunicação. Até a coleta real ser ativada, os'
  Write-Host 'dados aparecem como SIMULADOS.'
}
