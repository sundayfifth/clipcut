# clipcut

เครื่องมือ local สำหรับแปลงคลิปคอนเทนต์ของ แบรนด์คอนเทนต์สุขภาพ จาก 16:9 (YouTube) ให้เป็น 9:16 (TikTok) แบบกึ่งอัตโนมัติ

รับคลิปต้นฉบับ → วิเคราะห์ให้ว่าซีนไหน crop ได้ ซีนไหนต้องย่อ+เติมพื้นหลัง → render ไฟล์ 9:16 ที่พร้อมใช้เกือบสมบูรณ์ พร้อม checklist บอกว่ามี text/graphic ตรงไหนบ้างที่ต้องทำใหม่แล้วเติมเองใน CapCut/Hyperframe

**สิ่งที่เครื่องมือนี้ต้องทำ**
- รับ input ได้ทั้งไฟล์ในเครื่องและ URL YouTube
- แบ่ง shot แล้วตัดสินใจต่อ shot ว่า crop (ตามตัวคน) หรือ ย่อ+เติมพื้นหลัง
- ตรวจจับ text/graphic ที่ burn มากับต้นฉบับ แล้วรายงาน timecode + ตำแหน่ง + ข้อความ — **ไม่ลบและไม่ทับให้เอง**
- เลือกได้ตอนใช้ว่าจะเอาคลิปเท่าต้นฉบับ หรือตัดสั้นเฉพาะช่วงน่าสนใจ
- render ออกเป็น .mp4 9:16 + ไฟล์ checklist

## Stack

- Python 3.12 + FastAPI (backend) — `app/main.py`
- Vanilla HTML/CSS/JS (frontend) — `app/static/`
- ffmpeg เป็น render engine (มีในเครื่องที่ `/opt/homebrew/bin/ffmpeg`)
- PySceneDetect — หา shot boundary
- OpenCV — อ่าน/วิเคราะห์เฟรม
- yt-dlp — โหลดคลิปจาก YouTube

**ห้ามใช้ `ultralytics` (YOLO)** — เป็น AGPL-3.0 และ Ultralytics ระบุเองว่า internal business tool แบบ clipcut ต้องซื้อ Enterprise License รวมถึงห้าม depend repo ที่ depend มันด้วย ใช้ MediaPipe (Apache 2.0) เป็นหลัก + RF-DETR รุ่น Nano/Small/Medium/Large (Apache 2.0) เมื่อต้องการ multi-person — เลี่ยงรุ่น XL/2XL ที่เป็น PML 1.0

**ยังไม่ตัดสินใจ** (อย่าเพิ่งติดตั้งจนกว่าจะสรุป): OCR ภาษาไทยสำหรับ burned-in text และวิธี export ไป CapCut/Hyperframe — ดู `docs/2026-08-25-research-auto-reframe.md` หัวข้อ "ยังไม่ได้คำตอบ"

## Running it

```
source .venv/bin/activate
uvicorn app.main:app --reload
```

แล้วเปิด http://127.0.0.1:8000

test: `pytest`

## Docs

Project docs — specs, PRDs, research notes, ADRs — live under `docs/`.

อ่านก่อนเริ่มเขียน pipeline: [`docs/2026-08-25-research-auto-reframe.md`](docs/2026-08-25-research-auto-reframe.md) — กติกา crop-vs-pad, camera path smoothing, และข้อจำกัด license ที่ verify มาแล้ว

## Development rules

- แยก module ให้ขอบเขตชัด: `ingest` (รับไฟล์/URL) → `analyze` (shot, ตัวคน, text) → `plan` (สร้าง edit plan) → `render` (ffmpeg) → `report` (checklist กราฟฟิก)
- **edit plan JSON เป็น contract กลางของโปรเจกต์** ทุก module คุยกันผ่านมัน แก้ทีละ module ได้โดยไม่พังตัวอื่น เปลี่ยน schema เมื่อไหร่ให้จดเป็น ADR ใน `docs/`
- เขียน test สำหรับส่วนที่คนอื่นพึ่งพา — test behaviour ไม่ใช่ implementation
- handle error ที่เจอบ่อยให้ครบ: ไฟล์เสีย, codec ไม่รองรับ, YouTube โหลดไม่ได้, คลิปยาวจนแรมไม่พอ
- **ห้ามเขียนทับหรือลบไฟล์ใน `media/input/`** เด็ดขาด — ไฟล์ระหว่างทางไป `media/work/` ผลลัพธ์ไป `media/output/`
- งานที่กินเวลานาน (โหลด, วิเคราะห์, render) ต้องรายงาน progress กลับไปที่ UI ไม่ปล่อยให้หน้าจอค้างเงียบ
- commit ทีละก้อนเล็กที่รันได้ message เป็นภาษาอังกฤษสั้นๆ

## Notes

Real tool — others depend on this. Standards apply.

- ผู้ใช้จริงคือน้องตัดต่อ ไม่ใช่ developer — error message ต้องอ่านรู้เรื่องเป็นภาษาคน บอกว่าต้องทำอะไรต่อ
- **ซับไตเติลไม่ต้องทำในโปรเจกต์นี้** — ใช้ skill `subtitle-align` ที่มีอยู่แล้ว ต่อท้ายหลังได้ไฟล์ 9:16
- ปลายทางของ output คือ CapCut / Hyperframe เสมอ — คนยังต้องเก็บงานต่อ ไม่ต้องพยายามทำให้จบในตัว
