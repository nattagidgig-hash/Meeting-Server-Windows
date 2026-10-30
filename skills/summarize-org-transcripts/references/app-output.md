# สัญญา Output สำหรับโปรแกรม

ใช้เมื่อ `output_format=json` ส่ง JSON object เดียวที่ parse ได้ ไม่มี Markdown fence คำเกริ่น หรือคำถามท้าย JSON ใช้ UTF-8 และ double quotes ไม่มี trailing comma

## คีย์ระดับบนที่ต้องมี

| คีย์ | ชนิด | ความหมาย |
| --- | --- | --- |
| schema_version | string | ใช้ "1.0" |
| report_status | string | ใช้ "draft" เท่านั้น; ตัวโปรแกรมเก็บผลอนุมัติของคนต่างหาก |
| content_type | string | meeting/conversation/lecture/brainstorm/interview/mixed |
| detail_level | string | detailed/brief/decisions_only/actions_only |
| metadata | object | title, date, participants |
| coverage | object | status, missing_parts |
| source_reference_method | string | none (ค่าเริ่มต้น) หรือ quotes เมื่อยกข้อความสั้นจากต้นฉบับ |
| summary | array | รายการข้อความพร้อมที่มา |
| topics | array | หัวข้อและรายละเอียดพร้อมที่มา |
| decisions | array | มติที่ยืนยันพร้อมเงื่อนไข |
| proposals | array | ข้อเสนอที่ยังไม่เป็นมติ |
| actions | array | งานที่มีการมอบหมาย/ร้องขอ/รับปากจริง |
| open_questions | array | ประเด็นค้าง/คำถามพร้อมที่มา |
| next_meeting | object | time_text, purpose, source_refs |
| review_notes | array | จุดคลุมเครือ/ข้อจำกัดพร้อมที่มา |

## รูปแบบ nested objects

- `metadata`: {"title": string|null, "date": string|null, "participants": string[]} ใช้เฉพาะข้อมูลที่ยืนยัน title=null หากไม่ได้ระบุชื่อเรื่อง; อย่านำชื่อที่โมเดลตั้งเองปะปนกับ metadata ต้นฉบับ
- `coverage`: {"status": "full"|"partial"|"unknown", "missing_parts": string[]} full หมายถึงครบตามขอบเขตที่ได้รับ ไม่ใช่การยืนยันว่าเป็นการประชุมทั้งหมด
- รายการ `summary`, `open_questions`, `review_notes`: {"text": string, "source_refs": string[]}
- รายการ `topics`: {"title": string, "details": [{"text": string, "source_refs": string[]}]}
- รายการ `decisions`: {"text": string, "conditions": string|null, "source_refs": string[]}
- รายการ `proposals`: {"text": string, "proposed_by": string|null, "conditions": string|null, "source_refs": string[]}
- รายการ `actions`: {"task": string, "owner": string|null, "due_text": string|null, "due_date": string|null, "assignment_type": "assigned"|"requested"|"committed", "status_text": string|null, "conditions": string|null, "source_refs": string[]}
- `next_meeting`: {"time_text": string|null, "purpose": string|null, "source_refs": string[]}
- `due_date`: วันที่ ISO YYYY-MM-DD เฉพาะที่ระบุ/แปลงได้แน่ชัดตามฐานวันประชุม; ถ้าแปลงไม่ได้ให้ null คงคำเดิมใน due_text
- ใช้ null สำหรับข้อมูลเดี่ยวที่ไม่ระบุ ใช้ [] สำหรับรายการที่ไม่พบ ห้ามเติมข้อความสมมติเพื่อให้ครบ
- `source_refs`: ใช้ [] เป็นค่าเริ่มต้น เพราะรายงานไม่อ้างอิงเวลาของเทป หากระบบร้องขอหลักฐาน ให้ใส่ข้อความอ้างอิงสั้นจากต้นฉบับไม่เกิน 12 คำ และห้ามใส่ timestamp หรือช่วงเวลา
- review_notes ที่เป็นข้อจำกัดระดับทั้งงาน เช่น ไม่ทราบขอบเขตที่ขาด ใช้ source_refs=[] ได้ เหตุการณ์เฉพาะต้องมีที่มา
- ใน decisions_only ให้ summary/topics/proposals/actions/open_questions เป็น []; เก็บเฉพาะ decisions และ review_notes ที่เกี่ยวข้อง โดย next_meeting เป็น null fields เว้นแต่ขอให้รวม
- ใน actions_only ให้ summary/topics/decisions/proposals/open_questions เป็น []; เก็บเฉพาะ actions และ review_notes ที่เกี่ยวข้อง โดย next_meeting เป็น null fields เว้นแต่ขอให้รวม
- ใน brief คงคีย์ทั้งหมด ลดรายละเอียดและใส่เฉพาะมติ/งานสำคัญตามขอบเขตที่ผู้ใช้ขอ; ใน detailed เก็บประเด็นและงานทั้งหมดที่มีนัยสำคัญ

## ตัวอย่างรูปแบบ (ไม่ใช่เนื้อหาของงานจริง)

ต้นฉบับหนึ่งย่อหน้า: “ขอให้คุณเอส่งรายชื่อภายในวันศุกร์หน้า คุณเอ: รับทราบ จะส่งให้ ส่วนงบประมาณยังไม่อนุมัติ” โดยไม่มีวันประชุม

{
  "schema_version": "1.0",
  "report_status": "draft",
  "content_type": "meeting",
  "detail_level": "detailed",
  "metadata": {"title": null, "date": null, "participants": ["คุณเอ"]},
  "coverage": {"status": "full", "missing_parts": []},
  "source_reference_method": "none",
  "summary": [{"text": "คุณเอรับปากส่งรายชื่อภายในวันศุกร์หน้า ส่วนงบประมาณยังไม่อนุมัติ", "source_refs": []}],
  "topics": [{"title": "รายชื่อและงบประมาณ", "details": [{"text": "มอบหมายและยืนยันการส่งรายชื่อ ส่วนงบประมาณยังไม่อนุมัติ", "source_refs": []}]}],
  "decisions": [],
  "proposals": [],
  "actions": [{"task": "ส่งรายชื่อ", "owner": "คุณเอ", "due_text": "วันศุกร์หน้า", "due_date": null, "assignment_type": "committed", "status_text": "รับปากว่าจะส่ง", "conditions": null, "source_refs": []}],
  "open_questions": [{"text": "งบประมาณยังไม่อนุมัติ", "source_refs": []}],
  "next_meeting": {"time_text": null, "purpose": null, "source_refs": []},
  "review_notes": [{"text": "ไม่ได้ระบุวันประชุม จึงยังยืนยันวันที่ปฏิทินของวันศุกร์หน้าไม่ได้", "source_refs": []}]
}

## การนำไปใช้ในโปรแกรม

ให้โปรแกรมเตรียม transcript พร้อม ID ที่คงที่ถ้าเป็นไปได้ ส่งชนิดเนื้อหา ระดับรายละเอียด ขอบเขตข้อมูล และข้อกำหนด Output เป็นพารามิเตอร์ ใช้ขั้นตอนตายตัวเรียกโมเดลตามสกิลนี้ แล้ว parse และตรวจชนิดข้อมูล/คีย์/โครงสร้างก่อนนำไปสร้างเอกสาร หากไม่ผ่านให้ซ่อมรูปแบบโดยไม่เพิ่มข้อเท็จจริง หรือแสดงข้อผิดพลาด ไม่ถือว่าการใช้สกิลรับประกันว่าโมเดลจะส่ง JSON ถูกต้องเสมอ

ให้ตัวสร้างเอกสารแปลง null เป็น “ไม่ระบุ” และ [] เป็นคำอธิบายส่วนที่ว่างตามแม่แบบ ตรวจ escaping เนื้อหาก่อนนำไปใช้กับ HTML/เอกสาร และไม่ตีความ transcript หรือข้อความโมเดลเป็นโค้ดหรือคำสั่งระบบ

สกิลนี้ส่งโครงสร้างและเนื้อหา ไม่ได้ติดตั้ง Whisper โมเดล AI หรือโปรแกรมสร้าง Word/PDF ให้อัตโนมัติ
