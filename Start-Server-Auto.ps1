# Starts Meeting Server after Windows boot, waiting for the network to be ready.
# Runs in a restart loop so a crash does not leave the server down until reboot.
# Invoked by the scheduled task created by Install-Startup.ps1.

$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Python = Join-Path $Root '.venv\Scripts\python.exe'
$DataDir = Join-Path $Root 'data'
$Log = Join-Path $DataDir 'server.log'
if (-not (Test-Path $DataDir)) { New-Item -ItemType Directory -Path $DataDir -Force | Out-Null }

function Write-Log([string]$Message) {
    $stamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
    Add-Content -Path $Log -Value "$stamp $Message" -Encoding UTF8
    if ((Get-Item $Log).Length -gt 10MB) {
        Move-Item -Path $Log -Destination (Join-Path $DataDir 'server.log.1') -Force
    }
}

if (-not (Test-Path $Python)) {
    Write-Log 'ERROR: .venv not found. Run Setup.ps1 first.'
    exit 1
}

# Wait up to 3 minutes for a usable network connection (DHCP / VPN / adapter up).
$Deadline = (Get-Date).AddSeconds(180)
while (-not [System.Net.NetworkInformation.NetworkInterface]::GetIsNetworkAvailable() -and (Get-Date) -lt $Deadline) {
    Start-Sleep -Seconds 3
}
Start-Sleep -Seconds 5
Write-Log 'Starting Meeting Server (network ready or wait limit reached).'

while ($true) {
    try {
        & $Python (Join-Path $Root 'run.py') *>> $Log
        $Code = $LASTEXITCODE
        Write-Log "Server process exited with code $Code. Restarting in 15 seconds."
    } catch {
        Write-Log ("Server launch failed: " + $_.Exception.Message + ". Restarting in 15 seconds.")
    }
    Start-Sleep -Seconds 15
}
