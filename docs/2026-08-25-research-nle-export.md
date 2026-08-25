# Research: export ไป CapCut / Hyperframe

วันที่: 2026-08-25
สถานะ: **ผลบางส่วน — รอบวิจัยถูกตัดกลางคัน** (session limit) กำลัง resume อยู่ จะอัปเดตไฟล์นี้เมื่อครบ

สถิติรอบนี้: สกัด 119 claim → verify ได้ 25 → **ผ่าน 4 · ตกรอบ 7 · โหวตพัง 14** (agent 43 ตัวจาก 107 ตาย synthesis ไม่ได้รัน)

---

## ข้อสรุปที่ใช้ตัดสินใจได้แล้ว

**อย่าเอาสถาปัตยกรรมของ clipcut ไปผูกกับการเขียน CapCut draft folder** หลักฐานที่ผ่าน verification ชี้ไปทางเดียวกันหมดว่ามันเปราะ

## สิ่งที่ยืนยันแล้ว

### โครงสร้าง draft_content.json (3-0)

schema เป็นแบบ **flat และ decoupled** — segment ใน track ไม่ได้ฝัง media ไว้ข้างใน แต่อ้างด้วย `material_id` UUID พร้อม:

| field | ความหมาย |
|---|---|
| `target_timerange` | ตำแหน่งบน timeline |
| `source_timerange` | ช่วงที่ trim จากไฟล์ต้นทาง |
| `extra_material_refs[]` | speed, mask, fade |

แปลว่าถ้าจะ generate เอง ต้องเขียนให้ตรงกันทั้งใน `tracks[]` และ `materials.*` — พลาดข้างเดียวคือพัง

### version support แคบมาก (3-0)

capcut-cli ซึ่งเป็น tool ที่ document ดีที่สุดที่เจอ ระบุเองว่า:

- **fixture-tested จริงแค่ CapCut 6.2.8 เวอร์ชันเดียว**
- 6.5–9.x = "expected-compatible / unverified" ไม่มี fixture ที่สร้างจากแอปจริง
- **10.x (ทั้ง Mac และ Windows) รายงานว่า reject draft ที่ tool เขียน โดยขึ้นว่า "内容已损坏" (เนื้อหาเสียหาย)** — คำสั่งที่เขียนไฟล์จะปฏิเสธไม่ทำงานถ้าไม่ใส่ `--force-write`

repo เขียนตรงๆ ว่า *"There is no blanket 6.x–9.x tested claim. Only versions with committed fixtures receive that label."*

### ความเสี่ยงเชิงโครงสร้าง (2-1)

- schema บนดิสก์ของ CapCut **ไม่มีเอกสารทางการ**
- แอป **อัปเดตตัวเองและ migrate draft ทับที่** ตอนเปิดไฟล์ — พอ migrate แล้ว tool เก่าอาจ round-trip ไฟล์นั้นไม่ได้อีก
- **ไม่มีวิธีที่ vendor รองรับให้ pin เวอร์ชันแอป**
- capcut-cli รับมือด้วย tripwire ที่ **เตือนอย่างเดียว ไม่เคยปฏิเสธ**

คือความเสี่ยงพังไม่ใช่ "ถ้าพัง" แต่เป็น "เมื่อไหร่" และเราคุมไม่ได้เลย

## claim ที่ไม่ผ่าน verification

**อ่านให้ถูก: "ไม่ผ่าน" = ถ้อยคำของ claim นั้นแรงเกินหลักฐาน ไม่ได้แปลว่าข้อเท็จจริงตรงข้ามเป็นจริง** ส่วนใหญ่ตกเพราะ overreach

| claim ที่ตก | ผลต่อเรา |
|---|---|
| "CapCut International กับ JianYing ใช้ schema เดียวกัน ต่างแค่ field `app_source` (cc/lv)" (0-3) | **ห้ามเหมาว่าความรู้จาก pyJianYingDraft (4.2k ดาว) ใช้กับ CapCut ได้** ต้องพิสูจน์แยก |
| "capcut-cli เขียน draft แล้วเปิดใน CapCut ได้เป็น timeline หลาย track ที่แก้ต่อได้จริง" (0-3) | ข้ออ้างว่า "ทำได้จริงแล้ว" ยังไม่มีหลักฐานรองรับ |
| "text material เก็บข้อความใน field `content` ที่ใช้ offset แบบ UTF-16 LE" (0-3) | อย่าเพิ่งวางแผนรับมือปัญหาภาษาไทยบนสมมติฐานนี้ ยังไม่ยืนยัน |
| "JianYing 6.0+ เข้ารหัส draft" (0-3) | รายละเอียดเรื่อง encryption ยังไม่นิ่ง |

## ยังไม่ได้ตรวจ — โหวตพังเพราะ session limit (14 claim)

**ข้อพวกนี้มาจาก primary source และสำคัญมาก แต่ยังไม่ผ่านการยืนยัน อย่าเพิ่งเชื่อ**

🔴 **เรื่องที่กระทบเราตรงที่สุด** — บน **CapCut International 9.1.0 (macOS)** draft ที่ pyCapCut สร้างเปิดขึ้นมาแล้วทุกคลิปขึ้น *"file inaccessible"* ให้ relink เพราะ `draft_materials` ถูกปล่อยว่าง เป็น issue ที่ยังเปิดค้างอยู่ ณ 2026-08-18 — **เราใช้ macOS พอดี**

- CapCut Help Center ระบุว่า **ไม่รองรับ import/export project file จากโปรแกรมตัดต่ออื่น** (ระบุชื่อ Premiere Pro ตรงๆ) ← ถ้ายืนยันได้ นี่คือคำตอบสุดท้ายของ angle 2
- `capcut-export` ถูกประกาศ **End of Life ตั้งแต่ 2024-04-15** เพราะ CapCut/JianYing เริ่มเข้ารหัส draft
- path ที่ CapCut เก็บ draft ต่างกันตาม OS: macOS = `~/Movies/CapCut/User Data/Projects/com.lveditor.draft` ใช้ชื่อ `draft_info.json` / Windows = `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft` ใช้ `draft_content.json`
- draft folder ต้องมีอย่างน้อย 2 ไฟล์: `draft_content.json` (timeline) + `draft_meta_info.json` (manifest ที่ CapCut ใช้ตัดสินว่า media ไหนถูก import จริง จับคู่ด้วย `file_Path`) — **เขียนแค่ draft_content.json ไม่พอ**
- pyCapCut เป็นคนละ repo กับ pyJianYingDraft และ **ยังอยู่ระหว่างพัฒนา**

## Hyperframe — ยังตอบไม่ได้

รอบนี้ดึงมา 2 candidate แต่**ไม่มี claim ไหนผ่าน verification เลย** ยังระบุไม่ได้ว่าตัวไหนคือที่น้องตัดต่อใช้:

- https://hyperframe.ai/
- https://github.com/heygen-com/hyperframes (ของ HeyGen)

**ทางที่เร็วกว่ารีเสิช: เปิดโปรแกรมแล้วดูเมนู File → Import/Export เองเลย** แล้วบอกผมว่าเห็นอะไรบ้าง จะได้ตัดจบ

---

## ข้อเสนอชั่วคราว

*(design opinion จากหลักฐานเท่าที่ verify ได้ ไม่ใช่ข้อสรุปสุดท้าย)*

**deliverable หลักควรเป็นไฟล์ + sidecar ไม่ใช่ project file**

```
media/output/<ชื่อคลิป>/
├── <ชื่อคลิป>_9x16.mp4        ← ไฟล์ที่เปิดใน CapCut/Hyperframe ได้ทุกเวอร์ชัน
├── graphics-checklist.md      ← timecode + ตำแหน่ง + ข้อความเดิมที่ต้องทำใหม่
└── edit-plan.json             ← contract กลางของเรา เผื่อทำ exporter ทีหลัง
```

เหตุผล: mp4 ไม่มีวันพังเพราะ CapCut อัปเดต ส่วนการ generate draft folder ให้ถือเป็น **experiment แยก** ที่ถ้าพังก็ไม่กระทบ pipeline หลัก — ห้ามให้เป็นทางเดียวที่ output ออกได้

ถ้าจะลอง draft generation จริง ต้องรู้ก่อนว่าน้องตัดต่อใช้ **CapCut เวอร์ชันอะไร บน OS ไหน** เพราะหลักฐานบอกว่า 10.x reject และ 9.1.0 บน macOS มีปัญหา relink

## แหล่งอ้างอิง

- [capcut-cli](https://github.com/renezander030/capcut-cli) · [version-support.md](https://raw.githubusercontent.com/renezander030/capcut-cli/master/docs/version-support.md) — document ดีที่สุดที่เจอ ตรงไปตรงมาเรื่องข้อจำกัดตัวเอง
- [gist: CapCut draft format notes](https://gist.github.com/renezander030/80823f1d47081c312d2c1f9edd20dc22)
- [pyCapCut](https://github.com/GuanYixuan/pyCapCut) · [pyJianYingDraft](https://github.com/GuanYixuan/pyJianYingDraft) · [capcut-export](https://github.com/emosheeep/capcut-export)
- [CapCut Help — export pro project](https://www.capcut.com/help/how-to-export-pro-project) · [import subtitles](https://www.capcut.com/help/how-to-import-subtitles) · [import previous project](https://www.capcut.com/help/import-a-previous-project-into-the-current-project)
- [OTIO adapters](https://opentimelineio.readthedocs.io/en/latest/tutorials/adapters.html) · [otio-fcpx-xml-adapter](https://github.com/OpenTimelineIO/otio-fcpx-xml-adapter)

แหล่งของ angle 4-5 ที่ดึงมาแล้วแต่ยังไม่ได้ verify: [PP-OCRv5 multi-language](http://www.paddleocr.ai/latest/en/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html) · [typhoon-ocr-7b](https://huggingface.co/scb10x/typhoon-ocr-7b) · [Apple Vision supported languages](https://developer.apple.com/documentation/vision/vnrecognizetextrequest/supportedrecognitionlanguages(for:revision:)) · [DBNet (arXiv 1911.08947)](https://arxiv.org/abs/1911.08947) · [Opus Clip virality score](https://help.opus.pro/docs/article/virality-score) · [WhisperX](https://github.com/m-bain/whisperX) (word-level timestamp สำหรับตัดไม่ให้กลางคำ)
