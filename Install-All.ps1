param(
    [switch]$RegisterStartup,
    [switch]$SkipModel,
    [switch]$WithDevTools,
    [string]$OfflineWheels = ''
)
# One-command installer for the Meeting Server Windows package.
# Installs or verifies Python 3.12/3.13, FFmpeg, Python packages, the Whisper
# model, the local SQLite database and the default administrator account.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$Log = Join-Path $Root 'install-log.txt'

function Write-Step([string]$Message) {
    $line = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss') + '  ' + $Message
    Write-Host $Message
    Add-Content -Path $Log -Value $line -Encoding UTF8
}
function Stop-Install([string]$Message) {
    Write-Step ('FAILED: ' + $Message)
    throw $Message
}

Write-Step 'Meeting Server - one-command install'
if (-not [Environment]::Is64BitOperatingSystem) { Stop-Install 'ต้องใช้ Windows 64-bit' }
Write-Step ('OS: ' + [Environment]::OSVersion.VersionString + ' | PowerShell ' + $PSVersionTable.PSVersion)

# ---------- Python 3.12 / 3.13 ----------
$Python = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    foreach ($Version in @('-3.13', '-3.12')) {
        $Candidate = $null
        try { $Candidate = & py $Version -c 'import sys;print(sys.executable)' 2>$null } catch { $Candidate = $null }
        if ($LASTEXITCODE -eq 0 -and $Candidate) { $Python = $Candidate.Trim(); break }
    }
}
if (-not $Python -and (Get-Command python -ErrorAction SilentlyContinue)) {
    $Candidate = & python -c 'import sys;print(sys.executable if sys.version_info[:2] in [(3,12),(3,13)] else "")' 2>$null
    if ($LASTEXITCODE -eq 0 -and $Candidate) { $Python = $Candidate.Trim() }
}
if (-not $Python) {
    Write-Step 'ไม่พบ Python 3.12/3.13 - กำลังติดตั้ง Python 3.12 ด้วย winget'
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Stop-Install 'ไม่พบ Python และไม่พบ winget กรุณาติดตั้ง Python 3.12 x64 จาก python.org (ติ๊ก Add to PATH และ py launcher)'
    }
    & winget install --id Python.Python.3.12 -e --silent --accept-package-agreements --accept-source-agreements
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $Candidate = & py -3.12 -c 'import sys;print(sys.executable)' 2>$null
        if ($LASTEXITCODE -eq 0 -and $Candidate) { $Python = $Candidate.Trim() }
    }
    if (-not $Python) { Stop-Install 'ติดตั้ง Python แล้วแต่ยังเรียกไม่พบ กรุณาเปิด PowerShell ใหม่แล้วรัน Install-All.ps1 อีกครั้ง' }
}
Write-Step ('Python: ' + (& $Python -c 'import sys;print(sys.version.split()[0], sys.executable)'))

# ---------- FFmpeg (optional: faster-whisper ships PyAV) ----------
if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
    Write-Step ('FFmpeg: ' + ((ffmpeg -version | Select-Object -First 1)))
} else {
    Write-Step 'ไม่พบ FFmpeg - ลองติดตั้งด้วย winget (ไม่บังคับ เพราะ faster-whisper ถอดเสียงได้ด้วย PyAV)'
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        try { & winget install --id Gyan.FFmpeg -e --silent --accept-package-agreements --accept-source-agreements } catch { Write-Step ('ข้าม FFmpeg: ' + $_.Exception.Message) }
    }
}

# ---------- Dev tools (optional) ----------
if ($WithDevTools -and -not (Get-Command bun -ErrorAction SilentlyContinue)) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Step 'ติดตั้ง Bun สำหรับงานพัฒนา (bun run dev)'
        try { & winget install --id Oven-sh.Bun -e --silent --accept-package-agreements --accept-source-agreements } catch { Write-Step ('ข้าม Bun: ' + $_.Exception.Message) }
    }
}

# ---------- Disk space ----------
$FreeGB = [math]::Round((Get-PSDrive -Name ($Root.Substring(0, 1))).Free / 1GB, 1)
Write-Step ('พื้นที่ว่างไดรฟ์: ' + $FreeGB + ' GB')
if ($FreeGB -lt 8) { Stop-Install 'พื้นที่ว่างน้อยกว่า 8 GB กรุณาเพิ่มพื้นที่ก่อนติดตั้ง' }

# ---------- venv + packages ----------
$Venv = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Venv)) {
    Write-Step 'สร้าง .venv'
    & $Python -m venv '.venv'
    if ($LASTEXITCODE -ne 0) { Stop-Install 'สร้าง .venv ไม่สำเร็จ' }
}
Write-Step 'ติดตั้งแพ็กเกจ Python'
& $Venv -m pip install --upgrade pip | Out-Null
if ($OfflineWheels) {
    if (-not (Test-Path $OfflineWheels)) { Stop-Install ('ไม่พบโฟลเดอร์ wheels: ' + $OfflineWheels) }
    & $Venv -m pip install --no-index --find-links $OfflineWheels -r requirements.txt
} else {
    & $Venv -m pip install -r requirements.txt
}
if ($LASTEXITCODE -ne 0) { Stop-Install 'ติดตั้งแพ็กเกจไม่สำเร็จ ตรวจเครือข่ายหรือใช้ -OfflineWheels' }

# ---------- database + default account ----------
Write-Step 'สร้างฐานข้อมูล SQLite และบัญชีเริ่มต้น (data\meeting.db)'
& $Venv manage.py init
if ($LASTEXITCODE -ne 0) { Stop-Install 'manage.py init ไม่สำเร็จ' }

# ---------- Whisper model ----------
if (-not $SkipModel) {
    Write-Step 'ดาวน์โหลดโมเดล Whisper small (ต้องมีอินเทอร์เน็ตครั้งแรก)'
    & $Venv manage.py download-model
    if ($LASTEXITCODE -ne 0) { Stop-Install 'ดาวน์โหลดโมเดลไม่สำเร็จ ตรวจเครือข่าย Hugging Face หรือคัดลอกโฟลเดอร์ data\models จากชุดติดตั้งอื่น' }
} else {
    Write-Step 'ข้ามดาวน์โหลดโมเดลตามคำสั่ง -SkipModel'
}

# ---------- checks ----------
Write-Step 'ตรวจระบบ'
& $Venv manage.py check
if ($LASTEXITCODE -ne 0) { Stop-Install 'System check ไม่ผ่าน' }

# ---------- auto start ----------
if ($RegisterStartup) {
    Write-Step 'ลงทะเบียนเปิดอัตโนมัติเมื่อเปิดเครื่อง'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root 'Install-Startup.ps1') -StartNow
    if ($LASTEXITCODE -ne 0) { Write-Step 'ลงทะเบียน task ไม่สำเร็จ (ต้องรัน PowerShell as Administrator) ทำภายหลังได้ด้วย Install-Startup.ps1 -StartNow' }
}

Write-Step ''
Write-Step 'ติดตั้งเสร็จ'
Write-Step 'เปิดเว็บ: http://127.0.0.1:8765  (บัญชีเริ่มต้น Admin / 11111111 - เปลี่ยนรหัสด้วย manage.py reset-password)'
Write-Step 'เริ่มเซิร์ฟเวอร์ด้วย Start-Server.cmd หรือลงทะเบียน auto-start ด้วย Install-Startup.ps1 -StartNow'
Write-Step 'หน้าตั้งค่า Claude API มีปุ่มตรวจสอบการเชื่อมต่อ และแถบสถานะบนหัวเว็บจะแสดงเมื่อเชื่อมต่อได้'
Write-Step ('ล็อกการติดตั้ง: ' + $Log)
