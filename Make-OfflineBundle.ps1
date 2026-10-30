param(
    [string]$Output = '.\offline-bundle',
    [string]$PythonVersion = '3.12'
)
# Builds a self-contained folder (and zip) that installs on a Windows machine
# without internet: wheels for win_amd64 + the Whisper model + the project files.
# Run this on a machine that already completed Install-All.ps1 and has the model.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$Venv = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Venv)) { throw 'Run Install-All.ps1 on this machine first (need .venv and data\models).' }
if (-not (Test-Path (Join-Path $Root 'data\models'))) { throw 'data\models is missing. Run manage.py download-model first.' }

$Target = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $Output))
New-Item -ItemType Directory -Force -Path $Target, (Join-Path $Target 'wheels') | Out-Null

Write-Host 'Downloading wheels for Windows x64 / Python' $PythonVersion
& $Venv -m pip download -r requirements.txt -d (Join-Path $Target 'wheels') --only-binary=:all: --platform win_amd64 --python-version $PythonVersion --implementation cp
if ($LASTEXITCODE -ne 0) { throw 'pip download failed. Check network or run on the target platform.' }

Write-Host 'Copying project files'
$Files = @('app', 'web', 'skills', 'tests', 'scripts', 'package.json', 'requirements.txt', 'manage.py', 'run.py',
           'Setup.ps1', 'Install-All.ps1', 'Install-Startup.ps1', 'Start-Server-Auto.ps1', 'Enable-LAN.ps1',
           'Start-Server.cmd', 'Check-System.cmd', 'Configure-Summary.cmd', 'START-HERE-TH.md')
foreach ($Item in $Files) {
    $Path = Join-Path $Root $Item
    if (Test-Path $Path) { Copy-Item -Recurse -Force $Path (Join-Path $Target $Item) }
}

Write-Host 'Copying Whisper model (this is the large part)'
Copy-Item -Recurse -Force (Join-Path $Root 'data\models') (Join-Path $Target 'models')

@'
ติดตั้งแบบออฟไลน์
1. คัดลอกโฟลเดอร์นี้ไปยังเครื่องปลายทาง (ไม่ต้องต่ออินเทอร์เน็ต)
2. เปิด PowerShell ที่โฟลเดอร์นี้ แล้วรัน:
   powershell -ExecutionPolicy Bypass -File Install-All.ps1 -OfflineWheels .\wheels -SkipModel
3. คัดลอกโฟลเดอร์ models ไปไว้ที่ data\models ของเครื่องปลายทาง (สร้างจาก Install-All ก่อนหนึ่งครั้ง หรือคัดลอกทับ)
4. เริ่มใช้งาน: Start-Server.cmd หรือ Install-Startup.ps1 -StartNow
'@ | Set-Content -Path (Join-Path $Target 'OFFLINE-INSTALL.txt') -Encoding UTF8

$Zip = $Target.TrimEnd('\') + '.zip'
if (Test-Path $Zip) { Remove-Item $Zip -Force }
Write-Host 'Compressing' $Zip
Compress-Archive -Path (Join-Path $Target '*') -DestinationPath $Zip -CompressionLevel Optimal
Write-Host ('Bundle ready: ' + $Target)
Write-Host ('Zip: ' + $Zip)
