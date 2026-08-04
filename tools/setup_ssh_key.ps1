#!/usr/bin/env pwsh
# FlowCore — Configura autenticacao SSH por chave no Termux (uma unica vez)
# Depois disso: flowcore_remote.ps1 funciona sem senha
#
# Uso:
#   .\tools\setup_ssh_key.ps1
#   .\tools\setup_ssh_key.ps1 -Port 8022

param(
    [int]$Port = 8022,
    [string]$Device = ""
)

Set-StrictMode -Off

function Find-ADB {
    foreach ($c in @("adb","$env:USERPROFILE\platform-tools\adb.exe","C:\platform-tools\adb.exe")) {
        if (Get-Command $c -ErrorAction SilentlyContinue) { return $c }
    }
    return $null
}

$ADB = Find-ADB
if (-not $ADB) {
    Write-Host "XX  ADB nao encontrado — coloca platform-tools no PATH" -ForegroundColor Red
    exit 1
}

# Port forward
& $ADB forward "tcp:$Port" "tcp:$Port" | Out-Null

# Gera chave se nao existir
$keyFile = "$env:USERPROFILE\.ssh\id_ed25519"
if (-not (Test-Path $keyFile)) {
    Write-Host "Gerando chave SSH ed25519..."
    & ssh-keygen -t ed25519 -f $keyFile -N "" -q
}

$pubKey = (Get-Content "$keyFile.pub" -Raw).Trim()
Write-Host "Chave publica: $pubKey" -ForegroundColor Gray
Write-Host ""
Write-Host "Conectando ao Termux (vai pedir senha UMA vez)..." -ForegroundColor Cyan

$cmd = "mkdir -p ~/.ssh && echo '$pubKey' >> ~/.ssh/authorized_keys && sort -u ~/.ssh/authorized_keys -o ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys && echo SUCCESS"

$result = & ssh -p $Port -o StrictHostKeyChecking=no -o ConnectTimeout=15 "127.0.0.1" $cmd 2>&1

if ($result -match "SUCCESS") {
    Write-Host "OK  Chave instalada com sucesso!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Testa agora:" -ForegroundColor Cyan
    Write-Host "  .\tools\flowcore_remote.ps1 status"
} else {
    Write-Host "XX  Falhou: $result" -ForegroundColor Red
    Write-Host ""
    Write-Host "Certifica que o Termux esta com sshd rodando:" -ForegroundColor Yellow
    Write-Host "  No celular: pkill sshd; sshd"
}
