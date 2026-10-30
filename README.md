# Meeting Server (Windows)

ระบบรับไฟล์ประชุม → ถอดเสียงในเครื่อง → ตรวจข้อความ → สรุปด้วย Claude API → อนุมัติโดยคน → ส่งออกเป็นเอกสาร สำหรับติดตั้งบนเครื่อง Windows ภายในองค์กร

## ความสามารถ

- เว็บแอปภาษาไทย เปิดจากเบราว์เซอร์ ไม่ต้องติดตั้งโปรแกรมที่เครื่องผู้ใช้
- ถอดเสียงด้วย Whisper (faster-whisper, CPU INT8) ในเครื่อง ไม่ส่งไฟล์เสียงออก
- สรุปด้วย Claude API ตามบัญชีที่องค์กรอนุมัติ พร้อมช่องยินยอมก่อนส่งข้อความทุกงาน
- ตรวจและอนุมัติโดยคน (AI ไม่มีสิทธิ์อนุมัติ) แก้ไขแล้วกลับเป็นฉบับร่างอัตโนมัติ
- ส่งออก Word (.docx), Word รุ่นเก่า (.doc), TXT, JSON และพิมพ์เป็น PDF
- แสดงสถานะการเชื่อมต่อ Claude API แบบตรวจจริง พร้อม latency และเวลาที่ตรวจ
- ฐานข้อมูล SQLite ในเครื่อง (`data\meeting.db`) ไม่ต้องมี DB server
- เริ่มทำงานอัตโนมัติเมื่อเปิดเครื่องและเครือข่ายพร้อม

## ติดตั้งครั้งเดียว

```powershell
powershell -ExecutionPolicy Bypass -File .\Install-All.ps1 -RegisterStartup
```

สคริปต์จะตรวจ/ติดตั้ง Python 3.12–3.13, FFmpeg, แพ็กเกจ Python, โมเดล Whisper, ฐานข้อมูล และบัญชีเริ่มต้นให้ครบ

- เครื่องที่ไม่มีอินเทอร์เน็ต: สร้างชุดออฟไลน์ด้วย `Make-OfflineBundle.ps1` แล้วติดตั้งด้วย `-OfflineWheels .\wheels -SkipModel`
- ติดตั้งเฉพาะซอฟต์แวร์พัฒนา: เพิ่ม `-WithDevTools` (Bun สำหรับ `bun run dev`)

## บัญชีเริ่มต้น

- ชื่อผู้ใช้ `Admin` รหัสผ่าน `11111111` (สร้างอัตโนมัติเมื่อติดตั้ง, ไม่แสดงบนหน้าเว็บ)
- เปลี่ยนรหัสผ่านทันที: `.\.venv\Scripts\python.exe manage.py reset-password`
- เพิ่มผู้ใช้: `manage.py add-user`

## เริ่มใช้งาน

เปิด http://127.0.0.1:8765 หรือรัน `Start-Server.cmd` / scheduled task ที่ติดตั้งไว้

1. อัปโหลดไฟล์เสียงหรือวิดีโอ ตั้งชื่อการประชุม
2. รอถอดเสียงเสร็จ แล้วตรวจชื่อ ตัวเลข และมติ
3. กดสรุปด้วย Claude API (ต้องยินยอมส่งข้อความของงานนั้น)
4. ตรวจร่างรายงาน แก้ถ้อยคำ แล้วอนุมัติ
5. ดาวน์โหลด .docx / .doc / .txt / JSON หรือพิมพ์เป็น PDF

## คำสั่งผู้ดูแล

```powershell
.\.venv\Scripts\python.exe manage.py check           # ตรวจระบบและแพ็กเกจ
.\.venv\Scripts\python.exe manage.py reset-password  # เปลี่ยนรหัสผ่าน
.\.venv\Scripts\python.exe manage.py clear-jobs --confirm  # ล้างรายการงานทั้งหมด
.\.venv\Scripts\python.exe manage.py backup --confirm      # สำรองฐานข้อมูลและไฟล์
```

## พัฒนา

```bash
bun run dev      # http://localhost:5173 พร้อม live reload และ proxy /api ไป 8765
bun run dev:web  # เฉพาะหน้าเว็บ
```

## เอกสาร

- `START-HERE-TH.md` — คู่มือติดตั้ง ตั้งค่า LAN/TLS ความปลอดภัย และ checklist ก่อนใช้งานจริง

## หมายเหตุความปลอดภัย

- ค่าเริ่มต้นผูกกับ 127.0.0.1, ปิดส่วนสรุปจนกว่าจะตั้งค่า, ไม่มี API key ในรีโป
- API key เก็บแบบเข้ารหัสผูกเครื่องด้วย DPAPI และไม่ถูกส่งกลับไปยังเบราว์เซอร์
- การเปิดใช้ใน LAN ต้องใช้ TLS (ดู `Enable-LAN.ps1`) และสำรอง IP ของเซิร์ฟเวอร์
