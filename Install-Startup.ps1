param(
    [string]$TaskName = 'MeetingServer-Organization',
    [switch]$Force,
    [switch]$StartNow
)
# Registers Meeting Server to start automatically:
#   - at Windows startup (before anyone signs in)
#   - again at sign-in (recovery if the startup run could not start)
#   - Start-Server-Auto.ps1 waits up to 3 minutes for a network connection,
#     then keeps the server running and restarts it if the process exits.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$IsAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $IsAdmin) { throw 'Run PowerShell as Administrator to register a startup task.' }
if (-not (Test-Path (Join-Path $Root '.venv\Scripts\python.exe'))) { throw 'Run Setup.ps1 first.' }
if (-not (Test-Path (Join-Path $Root 'Start-Server-Auto.ps1'))) { throw 'Start-Server-Auto.ps1 is missing from this folder.' }

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    if (-not $Force) { throw 'Task already exists. Re-run with -Force to replace it.' }
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Write-Host 'Use the same Windows account that ran Setup.ps1 and saved the Claude API key.'
Write-Host 'DPAPI binds that key to the account, so a different account would need the key entered again.'
$Credential = Get-Credential -Message 'Windows account to run Meeting Server after boot, even without interactive sign-in'
if (-not $Credential) { throw 'No account supplied.' }

$Action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}"' -f (Join-Path $Root 'Start-Server-Auto.ps1')) `
    -WorkingDirectory $Root

$Triggers = @(
    (New-ScheduledTaskTrigger -AtStartup),
    (New-ScheduledTaskTrigger -AtLogOn -User $Credential.UserName)
)

$Settings = New-ScheduledTaskSettingsSet `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -Compatibility Win8

$Principal = New-ScheduledTaskPrincipal -UserId $Credential.UserName -LogonType Password -RunLevel Limited
$Task = New-ScheduledTask -Action $Action -Trigger $Triggers -Settings $Settings -Principal $Principal

$Plain = $Credential.GetNetworkCredential().Password
try {
    Register-ScheduledTask -TaskName $TaskName -InputObject $Task -User $Credential.UserName -Password $Plain | Out-Null
}
finally {
    $Plain = $null
    $Credential = $null
}

if ($StartNow) { Start-ScheduledTask -TaskName $TaskName }

Write-Host 'Startup task registered: runs at boot and at sign-in, waits for the network, restarts on exit.'
Write-Host 'Log file: data\server.log   Health check: http://127.0.0.1:8765/health'
Write-Host 'Windows stores the task credential; no password was written into any script.'
