# Research: ตรวจจับข้อความไทยที่ burn ในเฟรมวีดีโอ

วันที่: 2026-08-27
สถิติ: สกัด 117 claim → verify 25 → **ผ่าน 17 · ตกรอบ 8** · agent 106 ตัวไม่มีตาย

## ข้อสรุป: ใช้ Apple Vision

**ยืนยันด้วยการรันบนเครื่องนี้เอง ไม่ใช่แค่เชื่อเอกสาร**

```
rev3 + accurate = 18 ภาษา รวม th-TH  ← ใช้อันนี้
rev3 + fast     =  6 ภาษา ไม่มีไทย
rev4            = ไม่รองรับ
```

⚠️ **จุดที่พลาดง่ายมาก**: ค่า enum คือ `Accurate = 0`, `Fast = 1` (สลับกับที่คนส่วนใหญ่เดา)
ผมเองก็สลับตอนทดสอบครั้งแรกจนได้ข้อสรุปกลับด้าน ถ้าเผลอใช้ `fast` เพราะคิดว่าเร็วกว่า
จะได้ผลลัพธ์เป็นขยะ — ทดสอบจริงแล้ว `fast` อ่าน "เนื่องจากหลังการผ่าตัด" เป็น `InfrlAoni%HIGiA`

### ทำไมเลือกตัวนี้

| เหตุผล | รายละเอียด |
|---|---|
| เป็นตัวเดียวที่**พิสูจน์ได้**ว่ารองรับไทย | probe บนเครื่องเป้าหมายจริง ไม่ใช่ benchmark ในเปเปอร์ |
| **ไม่มีปัญหา license เลย** | system framework + `pyobjc-framework-Vision` (MIT) ผ่านเกณฑ์ห้าม AGPL แบบไม่ต้องถกเถียง |
| ไม่ต้องโหลดโมเดล ไม่ต้องต่อเน็ต | ต่างจาก OnnxTR/PaddleOCR ที่ดึง weights จาก HuggingFace |
| **เร็วพอ** | วัดบนเครื่องนี้ 131 ms/เฟรม (งานวิจัยวัดบน M2 base ได้ 179 ms) |

ที่ใช้จริง: 3 เฟรมต่อซีน → **~30-40 วินาทีต่อคลิป** (42 ซีน)

### ทำไม *ไม่* ใช้ `VNDetectTextRectanglesRequest`

ตอนแรกตั้งใจใช้ตัวนี้เพราะเป็น "detection อย่างเดียว" ไม่ต้อง recognize น่าจะเร็วกว่า **แต่ใช้ไม่ได้**

- คืนแค่ **character bounding box** ไม่ใช่กล่องระดับบรรทัด
- **ไม่มี language parameter** เลย
- Apple ไม่เคยเผยแพร่ตัวเลขความแม่นของมันกับภาษาใดทั้งสิ้น
- ถูกจัดอยู่ใต้หัวข้อ **"Legacy API"** แล้ว

ทางที่ถูกคือใช้ `VNRecognizeTextRequest` rev3 accurate **แล้วทิ้งข้อความ เอาแต่กล่อง** —
ได้กล่องระดับบรรทัดพร้อม confidence และบังเอิญได้ข้อความติดมาด้วยซึ่งมีประโยชน์กับ checklist

## ทางเลือกสำรอง (ถ้าวันหนึ่งต้องย้ายออกจาก macOS)

| ตัวเลือก | License | ข้อจำกัด |
|---|---|---|
| **OnnxTR** | Apache-2.0 ทั้ง code และ weights | มี `detection_predictor()` แบบ detection ล้วนจริง (default `fast_base`) auto-detect CoreML บน M-series · **แต่ไม่มีหลักฐานความแม่นกับไทย** |
| **PaddleOCR PP-OCRv5** | Apache-2.0 (ข้อกังวล AGPL จาก PyMuPDF หมดไปแล้วใน 3.x) | default rec **ไม่มีไทย** ต้องสลับไป `th_PP-OCRv5_mobile_rec` (82.68% self-reported) |
| **CRAFT** | MIT (NAVER) | ใช้เชิงพาณิชย์ได้ ไม่มี NC clause |

**ห้ามใช้ ultralytics ต่อไป** — PyPI ประกาศ AGPL-3.0 ชัดเจน

## สิ่งที่งานวิจัยตอบไม่ได้

1. **ไม่มีหลักฐานเปรียบเทียบความแม่นกับข้อความไทยเลยแม้แต่ชิ้นเดียว** — claim ที่เทียบ DBNet++ vs CRAFT และ claim ThaiOCRBench ถูกโหวตตก 0-3 ทั้งคู่ · FAST paper ทดสอบ 4 dataset ไม่มีไทยสักชุด (`"Thai"` = 0 hit ทั้งเปเปอร์)
2. **angle 4 (เทคนิคเฉพาะกับ burned-in subtitle) และ angle 5 (VAD) ไม่มี claim รอดเลย** — เป็นปัญหา budget allocation ซ้ำรอบที่ 3 ทั้งที่โจทย์เตือนไว้แล้ว
3. ตัวเลขความเร็วทั้งหมดวัดด้วยภาพภาษาอังกฤษ ไม่ใช่ซับไทยบนเฟรมวีดีโอ
4. **มีรายงาน memory leak** ~3-15 MB ต่อการเรียก `VNRecognizeTextRequest` (Apple Developer Forums 815812) — ที่ 3 เฟรม/ซีน ยังไม่กระทบ แต่ถ้าเพิ่ม sampling ต้องเฝ้า

## สิ่งที่ทดสอบเองแล้วได้คำตอบ (งานวิจัยไม่ได้ตอบ)

### การเดาตำแหน่งแถบซับ

**ดูแค่ "ข้อความอยู่ล่าง" ใช้ไม่ได้** — คลิปที่มีสกรีนช็อตเยอะจะมีข้อความทุกตำแหน่ง
ทดสอบแล้วมันแนะนำให้ตัดทิ้ง **บน 21% ล่าง 31% = ครึ่งจอ**

สัญญาณที่ใช้ได้คือ **ตำแหน่งเดิมซ้ำๆ ข้ามหลายซีน** (ซับอยู่แถวเดิมทุกครั้ง สกรีนช็อตกระจาย)
จับกลุ่มกล่องที่ขอบอยู่ระดับเดียวกัน (±0.03) แล้วเลือกกลุ่มที่โผล่ในซีนมากที่สุด ต้องเจอ ≥20% ของซีน

ผลหลังแก้:

| คลิป | แนะนำ | ตรงกับความจริงมั้ย |
|---|---|---|
| ความรู้สึกเมื่อคุณแม่ฯ (มีซับ burn) | บน 13% ล่าง 14% | ✅ โลโก้จบที่ 13% ซับเริ่มที่ 14% |
| ทำไมต้องให้ศูนย์ดูแลฯ (สกรีนช็อตเยอะ ไม่มีซับ) | บน 12% **ล่าง 0%** | ✅ ไม่มีซับ burn จริง |

**ไม่ใส่ให้อัตโนมัติ** — โชว์เป็นข้อเสนอให้กดรับ เพราะเดาพลาดได้

### VAD — ไม่ต้องใช้

งานวิจัยตอบ angle นี้ไม่ได้ แต่ทดสอบเองแล้ว **วัด RMS ต่อซีนพอ** ไม่ต้องเพิ่ม dependency

| ประเภทซีน | ระดับเสียง |
|---|---|
| มีเสียงพูด | -13 ถึง -17 dB |
| เงียบจริง | -37 และ -48 dB |

ห่างกัน 20 dB ไม่มีจุดกำกวม · วัด 25 ซีนใช้ 0.09 วินาที

**สิ่งที่ค้นพบระหว่างทาง**: เสียงบรรยายพูดคลุมทับ b-roll และสกรีนช็อตด้วย
23 จาก 25 ซีนมีเสียงพูด — จึงเตือนเฉพาะตอนคน*ตัดซีนออกจริง* ไม่โชว์ค้างทุกใบ

## แหล่งอ้างอิงหลัก

- [supportedRecognitionLanguages(for:revision:)](https://developer.apple.com/documentation/vision/vnrecognizetextrequest/supportedrecognitionlanguages(for:revision:)) — Apple ระบุเองว่า "A language supported in one recognition level may not be available in another"
- [VNDetectTextRectanglesRequest](https://developer.apple.com/documentation/vision/vndetecttextrectanglesrequest) · [VNTextObservation](https://developer.apple.com/documentation/vision/vntextobservation)
- [ocrmac](https://github.com/straussmaximilian/ocrmac) (MIT) — ตัวอย่างการเรียกจาก Python
- [OnnxTR](https://github.com/felixdittrich92/OnnxTR) · [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) · [CRAFT](https://github.com/clovaai/CRAFT-pytorch)
- [FAST paper](https://arxiv.org/abs/2111.02394) — ตัวเลข 152/600 FPS วัดบน NVIDIA 1080Ti/V100 ทั้งหมด ไม่มี CPU/ARM benchmark

## ยังค้าง

- แยก "ซับ" ออกจาก "กราฟฟิก/lower-third" ด้วยสัญญาณอะไรนอกจากตำแหน่ง — ตอนนี้ใช้ตำแหน่ง+ความสม่ำเสมอ ซึ่งพอใช้ แต่ยังไม่ได้ทดสอบกับคลิปที่มี lower-third เยอะ
- ความแม่นของ Vision เทียบกับ OnnxTR/PaddleOCR กับซับไทย — ต้อง benchmark เองถ้าจะย้าย
