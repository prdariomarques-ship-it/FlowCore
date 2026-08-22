# FlowCore — Windows AI Machine Diagnostics
# Runs as Administrator in PowerShell.
# Read-only: does not change any configuration.

Write-Host "`n=== FlowCore — Diagnostico Windows ($(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')) ===" -ForegroundColor Cyan

# --- System info ---
Write-Host "`n--- Sistema ---" -ForegroundColor Yellow
$cs = Get-CimInstance Win32_ComputerSystem
$os = Get-CimInstance Win32_OperatingSystem
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$ramGB = [math]::Round($cs.TotalPhysicalMemory / 1GB, 1)

Write-Host "OS        : $($os.Caption) Build $($os.BuildNumber)"
Write-Host "CPU       : $($cpu.Name)"
Write-Host "RAM       : $ramGB GB"

# --- Disk ---
Write-Host "`n--- Armazenamento ---" -ForegroundColor Yellow
Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Used -or $_.Free } | ForEach-Object {
    $total = [math]::Round(($_.Used + $_.Free) / 1GB, 1)
    $used  = [math]::Round($_.Used / 1GB, 1)
    $free  = [math]::Round($_.Free / 1GB, 1)
    Write-Host ("Drive {0}: total={1} GB  usado={2} GB  livre={3} GB" -f $_.Name, $total, $used, $free)
}

# --- GPU via nvidia-smi ---
Write-Host "`n--- GPU NVIDIA ---" -ForegroundColor Yellow
$nvidiaSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($nvidiaSmi) {
    nvidia-smi --query-gpu=name,driver_version,memory.total,temperature.gpu,utilization.gpu,power.draw `
        --format=csv,noheader,nounits 2>&1 | ForEach-Object {
        $parts = $_ -split ', '
        if ($parts.Count -ge 6) {
            Write-Host "GPU       : $($parts[0])"
            Write-Host "Driver    : $($parts[1])"
            Write-Host "VRAM      : $($parts[2]) MiB"
            Write-Host "Temp      : $($parts[3]) C"
            Write-Host "Utilizacao: $($parts[4]) %"
            Write-Host "Consumo   : $($parts[5]) W"
        } else {
            Write-Host $_
        }
    }
    Write-Host ""
    nvidia-smi
} else {
    Write-Host "nvidia-smi nao encontrado. Instale o driver NVIDIA." -ForegroundColor Red
}

# --- WSL ---
Write-Host "`n--- WSL ---" -ForegroundColor Yellow
$wslExe = Get-Command wsl -ErrorAction SilentlyContinue
if ($wslExe) {
    Write-Host "wsl --status:"
    wsl --status 2>&1
    Write-Host ""
    Write-Host "wsl --version:"
    wsl --version 2>&1
    Write-Host ""
    Write-Host "wsl -l -v:"
    wsl -l -v 2>&1
} else {
    Write-Host "WSL nao encontrado." -ForegroundColor Red
}

# --- Docker Desktop ---
Write-Host "`n--- Docker ---" -ForegroundColor Yellow
$docker = Get-Command docker -ErrorAction SilentlyContinue
if ($docker) {
    docker --version
    docker info --format "Status: {{.ServerVersion}}" 2>&1
} else {
    Write-Host "Docker nao encontrado." -ForegroundColor Red
}

Write-Host "`n=== Diagnostico concluido ===" -ForegroundColor Cyan
