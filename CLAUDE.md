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
- MediaPipe ObjectDetector ตรวจจับคน (**pin < 1.0** — 1.0.x crash บน macOS) โมเดลโหลดด้วย `./download-models.sh`
- Vanilla HTML/CSS/JS (frontend) — `app/static/`
- ffmpeg เป็น render engine (มีในเครื่องที่ `/opt/homebrew/bin/ffmpeg`)
- PySceneDetect — หา shot boundary
- OpenCV — อ่าน/วิเคราะห์เฟรม
- yt-dlp — โหลดคลิปจาก YouTube

**ห้ามใช้ `ultralytics` (YOLO)** — เป็น AGPL-3.0 และ Ultralytics ระบุเองว่า internal business tool แบบ clipcut ต้องซื้อ Enterprise License รวมถึงห้าม depend repo ที่ depend มันด้วย ใช้ MediaPipe (Apache 2.0) เป็นหลัก + RF-DETR รุ่น Nano/Small/Medium/Large (Apache 2.0) เมื่อต้องการ multi-person — เลี่ยงรุ่น XL/2XL ที่เป็น PML 1.0

**Output format ตัดสินแล้ว**: deliverable คือ `.mp4` 9:16 + `.srt` + checklist ไม่ใช่ project file — CapCut ไม่รองรับ import timeline จาก NLE อื่นเลย (ยืนยันจาก help center ของ CapCut เอง) แต่ import SRT ได้เป็น text clip แยกชิ้นที่แก้ได้ **ไม่ต้องทำ OTIO/EDL/FCPXML** และห้ามให้ draft-folder generation เป็นทางเดียวที่ output ออกได้ — ดู `docs/2026-08-25-research-nle-export.md`

**ยังไม่ตัดสินใจ**: OCR ภาษาไทยสำหรับ burned-in text (ยังไม่ได้วิจัย) และ Hyperframe รองรับ import อะไร (หาข้อมูลไม่เจอเลย ต้องเปิดโปรแกรมดูเอง)

## Running it

```
source .venv/bin/activate
uvicorn app.main:app --reload
```

แล้วเปิด http://127.0.0.1:8000

test: `pytest` (ต้องมี ffmpeg — test สร้างคลิปทดสอบเอง)

**สถานะตอนนี้**: รับไฟล์/URL YouTube → แบ่งซีน (4 ระดับ) → ตรวจจับคน → ตั้งแถบตัดซับ/โลโก้ (trim หรือ blur พร้อม preview) → เลือกซีน (ค่าตั้งต้นเลือกทั้งหมด) → ตัดสิน crop/pad ต่อซีน (คนพลิกเองได้) → render mp4 9:16 + `graphics-checklist.md`
ยังไม่ทำ: ตัดสั้นเฉพาะช่วงน่าสนใจ (hook detection), ตรวจจับตำแหน่งซับอัตโนมัติ

**บทเรียนที่ต้องจำ**: อย่าบังคับให้ตัวคน*ทั้งตัว*อยู่ในกรอบ 9:16 — เคยเขียนแบบนั้นแล้ว 23 จาก 25 ซีนกลายเป็น pad หมด สิ่งที่ต้องอยู่ในกรอบคือ*ตำแหน่ง*ของ subject
**ข้อจำกัดที่รู้แล้ว**: สกรีนช็อตที่มีรูปคนอยู่ข้างใน detector จะเห็นเป็นคนจริงแล้ว crop จนข้อความหาย — จึงต้องมีปุ่มให้คนพลิก
**การหาแถบซับอัตโนมัติทำไม่ได้ด้วยวิธีง่ายๆ** — ลอง edge density และ bright-pixel density แล้วทั้งคู่จมไปกับพื้นหลัง (กำแพงอิฐ/เสื้อขาว) ต้องใช้ text detection จริงซึ่งยังไม่ได้วิจัย ระหว่างนี้ให้คนเลื่อนเองพร้อม preview — คลิปช่องนี้ใช้เทมเพลตเดียวกันหมด ตั้งครั้งเดียวใช้ได้ทั้งชุด

## UI

ธีมเข้มเป็นหลัก (งานคือจ้อง thumbnail ทั้งวัน) accent เทียลตามโลโก้ของแบรนด์
ฟอนต์ Google Sans (SIL OFL) self-host ที่ `app/static/fonts/` — **มีอักษรไทยครบ 87 ตัว** จึงใช้ family เดียวทั้ง UI
subset เหลือ 111 KB จาก 4.6 MB แต่ต้องเก็บ GPOS ไว้ ไม่งั้นวรรณยุกต์ไทยลอย (ดู `app/static/fonts/README.md`)
- การ์ดซีนสลับได้ 2 มุมมอง: **ผลลัพธ์ 9:16** (คำนวณด้วย CSS ให้ตรงกับที่ ffmpeg เรนเดอร์) กับ **ภาพต้นฉบับ** ที่วาดกรอบทับให้เห็นว่าจะเสียอะไร — อันแรกเป็นค่าตั้งต้นเพราะคนตัดต่อไม่ต้องจินตนาการเอง
- **ปรับกรอบเองได้ต่อซีน** (เฉพาะโหมดเต็มจอ): เลื่อนซ้ายขวา · ซูม · ขึ้นลง เก็บเป็น `adjust: {dx, dy, scale}` ซึ่งเป็น**ส่วนต่างจากกรอบฐาน** (`crop_base`) ไม่ใช่ทับค่าไปเลย — กรอบจึงยังขยับตามคนตาม polynomial ได้อยู่ แค่เยื้องไปทั้งเส้น
  - `derive_crop()` ใน `app/plan.py` กับ `deriveCrop()` ใน `app.js` **ต้องแก้ให้ตรงกันเสมอ** ฝั่ง JS ใช้ทำพรีวิวสดตอนลากสไลเดอร์
  - **การตัดสินใจของคนต้องรอดจากการคำนวณใหม่** — `set_bands` เก็บ `included`, `manual_mode`, `adjust` ไว้แล้วใส่กลับ ไม่งั้นขยับแถบทีเดียวงานที่ตรวจไว้หายหมด
- คีย์ลัดบนการ์ด: `Space` เลือก/ไม่เลือก · `C`/`P` สลับโหมด · ลูกศรซ้ายขวาย้ายการ์ด (ต้องไล่ 40+ ซีนต่อคลิป เมาส์อย่างเดียวช้าเกิน)
- **แถบสร้างไฟล์ด้านล่างต้องเป็น `position: sticky` ห้ามใช้ `fixed`** — sticky กินที่ใน layout เองอยู่แล้ว ไม่ต้องวัดความสูงมาเผื่อที่ เคยใช้ `fixed` + ResizeObserver วัดความสูงไปตั้ง `--bar-h` แล้วเกิด feedback loop (padding เปลี่ยน → scrollbar โผล่ → ข้อความในแถบขึ้นบรรทัดใหม่ → แถบสูงขึ้น → วัดใหม่) จนแถบโตไม่หยุดบังทั้งหน้า
- `[hidden] { display: none !important }` จำเป็น เพราะ `display: grid/flex` ทับ `[hidden]`
- contrast ผ่าน WCAG AA ทั้งสองธีม **ตรวจด้วยการคำนวณจากค่า OKLCH ตรงๆ ไม่ใช่วัดในเบราว์เซอร์** — พื้นหลังที่มี alpha ทำให้วัดในเบราว์เซอร์เพี้ยน ต่ำสุดที่มีคือ 5.08 (dark) / 4.71 (light)

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
