param(
    [Parameter(Mandatory=$true)][string]$CertificatePath,
    [Parameter(Mandatory=$true)][string]$PrivateKeyPath
)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $IsAdmin) { throw 'Run PowerShell as Administrator to add the scoped firewall rule.' }
& '.\.venv\Scripts\python.exe' manage.py lan --cert $CertificatePath --key $PrivateKeyPath
if ($LASTEXITCODE -ne 0) { throw 'TLS configuration failed. Firewall was not changed.' }
if (-not (Get-NetFirewallRule -Name 'MeetingServer-HTTPS-LAN' -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name 'MeetingServer-HTTPS-LAN' -DisplayName 'Meeting Server HTTPS - Private local subnet only' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8765 -RemoteAddress LocalSubnet -Profile Private | Out-Null
}
Write-Host 'HTTPS configured. Only Private-profile local-subnet traffic is allowed on TCP 8765.'
Write-Host 'Restart Meeting Server and open the hostname/IP listed in the trusted certificate.'
Write-Host 'For Domain-profile networks, IT must review and create the appropriate scoped rule; this script does not open Domain/Public networks.'
