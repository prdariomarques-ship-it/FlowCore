#!/usr/bin/env pwsh
# FlowCore Remote - controla FlowCore no Android via ADB + SSH
#
# Primeira execução: instala chave SSH (pede senha uma vez)
# Execuções seguintes: sem senha
#
# Uso:
#   .\tools\flowcore_remote.ps1                    # status
#   .\tools\flowcore_remote.ps1 boot               # boot do kernel
#   .\tools\flowcore_remote.ps1 status             # status completo
#   .\tools\flowcore_remote.ps1 doctor             # health check
#   .\tools\flowcore_remote.ps1 deploy             # git pull + boot
#   .\tools\flowcore_remote.ps1 shell              # sessao interativa
#   .\tools\flowcore_remote.ps1 run "comando"      # comando arbitrario
#   .\tools\flowcore_remote.ps1 setup-key          # so instala a chave SSH
#   .\tools\flowcore_remote.ps1 logs               # tail dos logs

param(
    [Parameter(Position=0)]
    [string]$Command = "status",

    [Parameter(Position=1)]
    [string]$Arg = "",

    [string]$Device = "",
    [int]$Port = 8022,
    [string]$FlowCorePath = "~/FlowCore",
    [switch]$VerboseOutput
)

Set-StrictMode -Off
$ErrorActionPreference = "Continue"

# ── Cores ─────────────────────────────────────────────────────────────────────
function Write-OK   { param($m) Write-Host "  OK  $m" -ForegroundColor Green }
function Write-WARN { param($m) Write-Host "  !!  $m" -ForegroundColor Yellow }
function Write-FAIL { param($m) Write-Host "  XX  $m" -ForegroundColor Red }
function Write-HDR  { param($m) Write-Host "`n=== $m ===" -ForegroundColor Cyan }

# ── ADB ───────────────────────────────────────────────────────────────────────
function Find-ADB {
    $candidates = @(
        "adb",
        "$env:USERPROFILE\platform-tools\adb.exe",
        "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe",
        "C:\platform-tools\adb.exe"
    )
    foreach ($c in $candidates) {
        if (Get-Command $c -ErrorAction SilentlyContinue) { return $c }
    }
    return $null
}

function Invoke-ADB {
    # Named $ArgList, not $Args — $Args collides with PowerShell's own
    # reserved automatic variable of the same name. With that collision,
    # $Args inside this function silently ended up empty instead of the
    # array actually passed in, so every call ran bare "adb -s <serial>"
    # with no subcommand at all — which is why adb fell back to printing
    # its full --help text instead of doing anything (e.g. "forward").
    param([string[]]$ArgList)
    $adbArgs = if ($script:DeviceSerial) { @("-s", $script:DeviceSerial) + $ArgList } else { $ArgList }
    & $script:ADB @adbArgs 2>&1
}

# ── Setup ─────────────────────────────────────────────────────────────────────
Write-HDR "FlowCore Remote"

# Encontra ADB
$script:ADB = Find-ADB
if (-not $script:ADB) {
    Write-FAIL "ADB não encontrado. Adiciona ao PATH:"
    Write-Host "  `$env:PATH += ';`$env:USERPROFILE\platform-tools'"
    exit 1
}
Write-OK "ADB: $script:ADB"

# Encontra dispositivo
if ($Device) {
    # -Device explícito sempre tem prioridade e pula a auto-detecção —
    # antes disso, um -Device correto ainda podia falhar se a lista
    # auto-detectada abaixo viesse vazia por timing (comum em ADB via
    # WiFi), já que o "if (-not $devices) { exit }" rodava antes de
    # sequer olhar para $Device. Se o serial informado não existir de
    # verdade, o adb -s abaixo falha com um erro específico dele mesmo.
    $script:DeviceSerial = $Device
} else {
    # Regex ancorada (^...$) em vez de só "\bdevice$" — mais robusta contra
    # linhas soltas do daemon do adb ("* daemon not running...") e contra \r
    # residual em saída nativa capturada via 2>&1 no Windows, que fazia a
    # extração anterior devolver entradas vazias em vez do serial real.
    $devices = @(
        (Invoke-ADB @("devices")) |
            ForEach-Object { $_.Trim() } |
            Where-Object { $_ -match '^(\S+)\s+device$' } |
            ForEach-Object { ($_ -split '\s+')[0] } |
            Where-Object { $_ }
    )
    if (-not $devices) {
        Write-FAIL "Nenhum dispositivo ADB conectado. Verifica o cabo/WiFi e USB Debugging."
        exit 1
    } elseif ($devices.Count -gt 1) {
        Write-WARN "Múltiplos dispositivos: $($devices -join ', ')"
        Write-Host "Usa: .\tools\flowcore_remote.ps1 $Command -Device <serial>"
        exit 1
    } else {
        $script:DeviceSerial = $devices
    }
}
Write-OK "Dispositivo: $script:DeviceSerial"

# Port forward ADB → SSH
# Precise "error:"-prefix match, not a generic "error|fail" substring
# search — the old check could false-positive on unrelated output (e.g.
# adb's own --help text mentions "--exit-on-write-error") and then dump
# that entire text as the "failure" message, obscuring the real error.
$fwd = Invoke-ADB @("forward", "tcp:$Port", "tcp:$Port")
if ($fwd -match "^error:") {
    Write-FAIL "adb forward falhou: $fwd"
    exit 1
}
Write-OK "Porta $Port encaminhada via ADB"

# ── SSH helpers ───────────────────────────────────────────────────────────────
$SSHOpts = @(
    "-p", "$Port",
    "-o", "StrictHostKeyChecking=no",
    "-o", "ConnectTimeout=10",
    "-o", "BatchMode=yes"          # falha em vez de pedir senha
)

function Test-SSHKey {
    $result = & ssh @SSHOpts "127.0.0.1" "echo ok" 2>&1
    return ($result -eq "ok")
}

function Install-SSHKey {
    Write-HDR "Instalando chave SSH (uma vez)"

    # Garante que existe uma chave no PC
    $keyFile = "$env:USERPROFILE\.ssh\id_ed25519"
    if (-not (Test-Path $keyFile)) {
        Write-Host "Gerando chave SSH..."
        & ssh-keygen -t ed25519 -f $keyFile -N '""' -q
    }
    $pubKey = Get-Content "$keyFile.pub" -Raw

    Write-Host "Copiando chave para Termux (vai pedir senha uma vez)..."
    $setupCmd = "mkdir -p ~/.ssh && echo '$pubKey' >> ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys && echo KEY_OK"

    $sshOptsNoBatch = @(
        "-p", "$Port",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=15"
    )
    $result = & ssh @sshOptsNoBatch "127.0.0.1" $setupCmd 2>&1

    if ($result -match "KEY_OK") {
        Write-OK "Chave instalada - próximas conexões sem senha"
        return $true
    } else {
        Write-FAIL "Falha ao instalar chave: $result"
        return $false
    }
}

function Invoke-SSH {
    param([string]$RemoteCmd, [switch]$Interactive)

    if ($Interactive) {
        $opts = @("-p", "$Port", "-o", "StrictHostKeyChecking=no")
        & ssh @opts "127.0.0.1"
        return
    }

    $result = & ssh @SSHOpts "127.0.0.1" $RemoteCmd 2>&1
    return $result
}

function Invoke-FlowCore {
    param([string]$Cmd)
    $remote = "cd $FlowCorePath && python3 flowcore.py $Cmd"
    return Invoke-SSH -RemoteCmd $remote
}

# ── Garante autenticação por chave ─────────────────────────────────────────────
if (-not (Test-SSHKey)) {
    Write-WARN "Chave SSH não configurada ainda"
    $ok = Install-SSHKey
    if (-not $ok) {
        Write-FAIL "Configure autenticação SSH manualmente."
        Write-Host "  No Termux: cat ~/.ssh/authorized_keys"
        exit 1
    }
    if (-not (Test-SSHKey)) {
        Write-FAIL "Chave instalada mas SSH ainda falhou"
        exit 1
    }
}
Write-OK "SSH autenticado por chave"

# ── Roteamento de comandos ─────────────────────────────────────────────────────
Write-HDR "Executando: $Command $Arg"

switch ($Command.ToLower()) {

    "boot" {
        Write-Host (Invoke-FlowCore "boot")
    }

    "status" {
        Write-Host (Invoke-FlowCore "status")
    }

    "doctor" {
        Write-Host (Invoke-FlowCore "doctor")
    }

    "deploy" {
        Write-HDR "Deploy (git pull + boot)"
        $pull = Invoke-SSH -RemoteCmd "cd $FlowCorePath && git pull origin main 2>&1"
        Write-Host $pull
        Write-Host ""
        Write-Host (Invoke-FlowCore "boot")
    }

    "shell" {
        Write-HDR "Sessao interativa - Ctrl+D para sair"
        Invoke-SSH -Interactive
    }

    "run" {
        if (-not $Arg) {
            Write-WARN "Uso: .\tools\flowcore_remote.ps1 run 'comando'"
            exit 1
        }
        Write-Host (Invoke-SSH -RemoteCmd $Arg)
    }

    "logs" {
        $logFile = "~/.flowcore/flowcore.log"
        Write-Host (Invoke-SSH -RemoteCmd "tail -50 $logFile 2>/dev/null || echo 'Log nao encontrado'")
    }

    "setup-key" {
        Write-OK "Chave ja instalada"
    }

    default {
        Write-WARN "Comando desconhecido: $Command"
        Write-Host ""
        Write-Host "Comandos disponíveis:"
        Write-Host "  boot       - inicializa o Runtime Kernel"
        Write-Host "  status     - mostra status completo"
        Write-Host "  doctor     - health check dos 35 pontos"
        Write-Host "  deploy     - git pull + boot"
        Write-Host "  shell      - sessao SSH interativa"
        Write-Host "  run <cmd>  - comando arbitrario no Termux"
        Write-Host "  logs       - ultimas 50 linhas do log"
        Write-Host "  setup-key  - instala chave SSH (sem senha)"
        exit 1
    }
}

Write-Host ""
