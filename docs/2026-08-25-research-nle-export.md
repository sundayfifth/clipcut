# Research: export ไป CapCut / Hyperframe

วันที่: 2026-08-25 (อัปเดต 2026-08-26 หลัง resume)
สถิติ: สกัด 122 claim → verify 25 → **ผ่าน 9 · ตกรอบ 11 · โหวตพัง 5**

> **ข้อจำกัดของงานวิจัยรอบนี้** — รอบแรกโดน session limit ตัดกลางคัน รอบ resume เครื่อง sleep ระหว่างรัน (agent ตาย 14 ตัว) และ **synthesis step ไม่ได้รันทั้งสองรอบ** ผลที่ได้จึงเป็น claim ดิบที่ผ่าน verification ไม่ได้ผ่านการ merge/จัดอันดับ ผมสังเคราะห์เองจากในนี้
>
> มีจุดที่ **หลักฐานขัดกันเองระหว่างสองรอบ** ระบุไว้ข้างล่างแล้ว

---

## ข้อสรุป

**deliverable หลักคือ mp4 + srt ไม่ใช่ project file** — ซึ่งบังเอิญตรงกับที่ CapCut แนะนำเองด้วย

การเขียน CapCut draft folder ทำได้จริง แต่เปราะเกินกว่าจะให้เป็นทางเดียวที่ output ออกได้

## สิ่งที่ยืนยันแล้ว

### ✅ SRT คือช่องทางที่ใช้ได้จริง (2-0)

> *"Subtitles will appear as individual text clips on the timeline, synced to your video."*
> — [CapCut Help](https://www.capcut.com/help/how-to-import-subtitles)

import SRT แล้วได้ **text clip แยกชิ้น แก้ทีละอันได้ ตรง timing กับวีดีโอ** — เป็นทางเดียวที่ push ข้อมูลแบบมี timecode เข้า CapCut ได้โดยไม่ต้องแตะ draft format เลย

**ต่อกับ skill `subtitle-align` ที่มีอยู่แล้วได้ทันที**

(ยังไม่ยืนยัน แต่จาก source เดียวกัน: CapCut รับเฉพาะ `.srt` กับ `.txt` เท่านั้น ไม่มี EDL/XML/FCPXML/AAF/OTIO และ CapCut Web รับแค่ `.srt`)

### ❌ ไม่มีทาง import timeline จาก NLE อื่น (2-0)

> *"CapCut currently does not support cross-draft editing or directly importing one project file into another."*

แม้แต่ draft ของ CapCut เองยัง import ข้าม project ไม่ได้ — **ทางออกที่ CapCut แนะนำเองคือ render เป็นไฟล์วีดีโอแล้ว import ไฟล์นั้น** (ข้อหลังยังไม่ผ่าน verification แต่ปรากฏใน help page 2 หน้าตรงกัน)

แปลว่า OTIO/EDL/FCPXML **ไม่ต้องเสียเวลาทำ** สำหรับ CapCut

### ⚠️ การเขียน draft folder — ทำได้ แต่มีเงื่อนไข

| ข้อเท็จจริง | โหวต |
|---|---|
| pyCapCut generate draft folder ที่ CapCut เปิดเป็น timeline แก้ได้จริง (audio/video/animation/transition/text) | 2-1 |
| **generate บน macOS ได้ แต่ auto-export ต้องใช้ CapCut ตัว Windows** | 3-0 |
| auto-export พึ่ง UI control เก่า ซึ่ง **v7+ ไม่มีแล้ว** | 3-0 |
| capcut-cli fixture-tested จริงแค่ **CapCut 6.2.8 เวอร์ชันเดียว** — 6.5–8.0 แค่ "คาดว่าน่าจะได้" | 3-0 |

**ข้อ "ต้องใช้ Windows" ไม่ได้บล็อกเราเท่าที่เห็น** — มันบล็อกแค่ขั้น *auto-export* (สั่งให้ CapCut render ให้อัตโนมัติ) ซึ่งเราไม่ต้องการอยู่แล้ว เพราะเรา render เองด้วย ffmpeg ส่วนขั้น **generate draft ทำบน macOS ได้**

### ❌ ทางที่ตัดทิ้งได้เลย

- **pyJianYingDraft (4.2k ดาว) ใช้กับ CapCut ไม่ได้** (3-0) — เจ้าของ repo เขียนเองว่าตัว CapCut แยกไปอยู่ pyCapCut ซึ่งยังพัฒนาไม่เสร็จ → ความ mature ของตัวจีน **ไม่ถ่ายทอดมา**
- **JianYing 6.0+ เข้ารหัส draft** (3-0) — capcut-cli ตรวจเจอว่าเข้ารหัสแต่ถอดไม่ได้ ตัวจีนเป็นทางตัน
- **capcut-export เป็น read-only** (3-0) — มันแค่อ่าน draft แล้วเรียก ffmpeg stream-copy ตัดคลิป **ไม่เคยเขียน draft** ไม่ใช่ candidate ตั้งแต่แรก

## 🔶 จุดที่หลักฐานขัดกันเอง

claim เรื่อง **CapCut 10.x reject draft ที่ tool เขียน** (ขึ้น "内容已损坏"):

- รอบแรก: **ผ่าน 3-0**
- รอบ resume: **ตก 0-3**

ต้นทางคือ `version-support.md` ไฟล์เดียวกัน ซึ่งใช้คำว่า **"reported"** ไม่ใช่ "tested" — อ่านแบบปลอดภัยที่สุดคือ *"มีรายงานว่า 10.x พัง แต่ไม่มี fixture ยืนยัน"* **อย่าเชื่อทั้งสองทาง ต้องทดสอบกับเครื่องจริง**

เช่นเดียวกับ issue #13 ของ pyCapCut (2026-08-18) ที่บอกว่าบน **CapCut 9.1.0 ทุกคลิปขึ้น "file inaccessible" ให้ relink เพราะ `draft_materials` ว่าง** — รอบแรกอยู่ในกอง "ยังไม่ตรวจ" รอบนี้ตก 1-2 คือ **ยังไม่นิ่ง แต่เป็นสัญญาณเตือนที่ตรงกับ use case เราพอดี (macOS)**

## เรื่องที่ claim ตกเพราะ "พูดแรงเกินหลักฐาน"

**อ่านให้ถูก: ตก ≠ ตรงข้ามเป็นจริง** pattern ที่เห็นชัดคือ verifier รับ "แกนข้อเท็จจริงแคบๆ" แต่ตัด "ข้อสรุปที่ต่อยอดเกิน" ทิ้ง เช่นข้อเดียวกันเรื่อง 6.2.8 ผ่านตอนพูดแค่ว่า fixture มีเวอร์ชันเดียว แต่ตกตอนเติมว่า "ดังนั้นจึงไม่ verified กับ CapCut ปัจจุบันเลย"

claim ที่ตกซึ่งยัง**ควรเผื่อใจไว้** เพราะมาจาก primary source: draft ไม่ใช่ไฟล์เดียว (มี `draft_content.json`, `draft_info.json`, `draft_meta_info.json`, `template-2.tmp` และ 8.7+ อาจไม่สนใจ `draft_content.json`), ชื่อไฟล์ต่างกันตาม OS (macOS = `draft_info.json` / Windows = `draft_content.json`), และ `capcut-export` ถูกประกาศ EOL เม.ย. 2024 เพราะ CapCut เริ่มเข้ารหัส

## โครงสร้าง draft_content.json (จากรอบแรก, 3-0)

schema เป็นแบบ **flat และ decoupled** — segment ใน track ไม่ฝัง media ไว้ข้างใน แต่อ้างด้วย `material_id` UUID พร้อม `target_timerange` (ตำแหน่งบน timeline), `source_timerange` (ช่วง trim), `extra_material_refs[]` (speed/mask/fade)

ถ้าจะ generate เอง ต้องเขียนให้ตรงกันทั้งใน `tracks[]` และ `materials.*`

## ❓ Hyperframe — ยังตอบไม่ได้

รอบนี้ดึงมา 2 candidate แต่**ไม่มี claim ไหนผ่าน verification เลยสักข้อ** ทั้งสองรอบ:

- https://hyperframe.ai/
- https://github.com/heygen-com/hyperframes (ของ HeyGen)

**ยังระบุไม่ได้ว่าตัวไหนคือที่น้องตัดต่อใช้** — เปิดโปรแกรมดูเมนู File → Import/Export เองเร็วกว่ารีเสิชรอบสาม

---

## ข้อเสนอ

*(design opinion สังเคราะห์จากหลักฐานข้างบน)*

```
media/output/<ชื่อคลิป>/
├── <ชื่อคลิป>_9x16.mp4        ← deliverable หลัก เปิดได้ทุกเวอร์ชัน ไม่มีวันพังเพราะ CapCut อัปเดต
├── <ชื่อคลิป>.srt             ← ซับจาก subtitle-align → CapCut import แล้วได้ text clip แก้ได้ทีละอัน
├── graphics-checklist.md      ← timecode + ตำแหน่ง + ข้อความเดิมที่ต้องทำกราฟฟิกใหม่
└── edit-plan.json             ← contract กลางของเรา เผื่อทำ exporter ทีหลัง
```

เหตุผล: นี่คือ **path ที่ CapCut รองรับอย่างเป็นทางการทั้งคู่** (flattened video + SRT) ไม่ต้องพึ่ง reverse engineering เลย

**ถ้าจะลอง draft generation** ให้ทำเป็น experiment แยกที่พังแล้วไม่กระทบ pipeline หลัก และต้องรู้ก่อนว่าน้องตัดต่อใช้ **CapCut เวอร์ชันอะไร บน OS ไหน** เพราะหลักฐานชี้ว่า 9.x/10.x มีปัญหา ส่วน library ที่มีอยู่ทดสอบจริงแค่ 6.2.8

ไอเดียที่ยังไม่ได้พิสูจน์: ถ้า SRT เข้าเป็น text clip ที่มี timecode ได้ อาจใช้ SRT อีกไฟล์เป็น **marker track ของ graphics checklist** ให้น้องตัดต่อเห็นบน timeline เลยว่าตรงไหนต้องเติมกราฟฟิก — ต้องลองจริงก่อน

## แหล่งอ้างอิง

- [CapCut Help — import subtitles](https://www.capcut.com/help/how-to-import-subtitles) · [import previous project](https://www.capcut.com/help/import-a-previous-project-into-the-current-project) · [export pro project](https://www.capcut.com/help/how-to-export-pro-project)
- [capcut-cli](https://github.com/renezander030/capcut-cli) · [version-support.md](https://raw.githubusercontent.com/renezander030/capcut-cli/master/docs/version-support.md) — ตรงไปตรงมาเรื่องข้อจำกัดตัวเองที่สุด
- [pyCapCut](https://github.com/GuanYixuan/pyCapCut) · [pyJianYingDraft](https://github.com/GuanYixuan/pyJianYingDraft) · [capcut-export](https://github.com/emosheeep/capcut-export)
- [gist: CapCut draft format notes](https://gist.github.com/renezander030/80823f1d47081c312d2c1f9edd20dc22)

**ยังไม่ได้ verify** — แหล่งของ angle 4-5 ที่ดึงมาแล้วแต่ verification ไม่ถึง: [PP-OCRv5 multi-language](http://www.paddleocr.ai/latest/en/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.html) · [typhoon-ocr-7b](https://huggingface.co/scb10x/typhoon-ocr-7b) · [Apple Vision supported languages](https://developer.apple.com/documentation/vision/vnrecognizetextrequest/supportedrecognitionlanguages(for:revision:)) · [DBNet](https://arxiv.org/abs/1911.08947) · [Opus Clip virality score](https://help.opus.pro/docs/article/virality-score) · [WhisperX](https://github.com/m-bain/whisperX) (word-level timestamp สำหรับตัดไม่ให้กลางคำ)
