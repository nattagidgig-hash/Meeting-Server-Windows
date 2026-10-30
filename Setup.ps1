$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
Write-Host 'Meeting Server setup: Windows x64, Python 3.12 or 3.13.'
if (-not [Environment]::Is64BitOperatingSystem) { throw 'A 64-bit Windows installation is required.' }
$Python = $null
foreach ($Version in @('-3.13','-3.12')) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        try { $Candidate = & py $Version -c 'import sys; print(sys.executable)' 2>$null } catch { $Candidate = $null; continue }
        if ($LASTEXITCODE -eq 0 -and $Candidate) { $Python = $Candidate.Trim(); break }
    }
}
if (-not $Python -and (Get-Command python -ErrorAction SilentlyContinue)) {
    $Candidate = & python -c 'import sys; print(sys.executable if sys.version_info[:2] in [(3,12),(3,13)] else "")' 2>$null
    if ($LASTEXITCODE -eq 0 -and $Candidate) { $Python = $Candidate.Trim() }
}
if (-not $Python) { throw 'Install a supported Python 3.13 or 3.12 x64 from https://www.python.org/downloads/windows/ including pip and the launcher, then run Setup.ps1 again.' }
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    & $Python -m venv '.venv'
    if ($LASTEXITCODE -ne 0) { throw 'Unable to create Python environment.' }
}
$Venv = Join-Path $Root '.venv\Scripts\python.exe'
& $Venv -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check network access, Python version, and Visual C++ x64 runtime. No firewall or system security settings were changed.' }
& $Venv manage.py init
if ($LASTEXITCODE -ne 0) { throw 'Account initialization failed.' }
# Limit meeting data to the installing account plus system administrators/SYSTEM.
$Account = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls (Join-Path $Root 'data') '/inheritance:r' '/grant:r' "${Account}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' '/T' '/Q'
if ($LASTEXITCODE -ne 0) { throw 'Could not apply data-folder permissions. Ask IT to correct ACLs before adding meeting data.' }
$Download = Read-Host 'Download and verify Whisper small now? Internet is required [Y/n]'
if ($Download -notmatch '^[nN]') {
    & $Venv manage.py download-model
    if ($LASTEXITCODE -ne 0) { throw 'Model download/load failed. Run .venv\Scripts\python.exe manage.py download-model after fixing network/runtime access.' }
}
& $Venv manage.py check
if ($LASTEXITCODE -ne 0) { throw 'System check failed.' }
Write-Host 'Setup complete. Summary/API remain disabled by default.'
Write-Host 'Run Start-Server.cmd, then open http://127.0.0.1:8765 on this computer.'
Write-Host 'LAN HTTPS and startup task are separate explicit steps in START-HERE-TH.md.'
