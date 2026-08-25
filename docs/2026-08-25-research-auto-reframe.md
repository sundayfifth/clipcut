# Research: auto-reframe 16:9 → 9:16 สำหรับ clipcut

วันที่: 2026-08-25
วิธี: deep-research harness — 5 search angle, ดึง 25 แหล่ง, สกัด 125 claim, verify แบบ adversarial 3 เสียงต่อ claim

## สรุปสั้น

**งานรอบนี้ตอบได้จริงแค่ 2 ใน 5 angle** — auto-reframe prior art กับ detector/license
angle ที่เหลือ (Thai OCR, export ไป CapCut/Hyperframe, highlight detection) **verification budget หมดก่อน ไม่ได้ถูกตรวจเลย**
ห้ามอ่านว่า "ไม่มีข้อมูล" — ให้อ่านว่า "ยังไม่ได้ยืนยัน" ต้องวิจัยรอบสอง

สถิติ: claim สกัดมา 125 → verify จริง 25 → ผ่าน 18 → ตกรอบ 7 → หลัง merge เหลือ 12 finding

---

## 1. crop vs pad ตัดสินยังไง — ตอบได้แล้ว

**AutoFlip ไม่ได้ใช้ heuristic ตามประเภทของ shot แต่เป็น geometric fallback** (ยืนยันระดับ source code, 3-0)

กติกาจริงใน `scene_cropping_calculator.cc`:

```
*apply_padding = scaled_width != target_width_ || scaled_height != target_height_;
```

แปลว่า: feature ที่ mark `is_required` ต้องถูกครอบให้หมด ถ้า crop window ที่ต้องใช้ครอบ required region ทั้งหมดแล้วมัน**กว้างเกิน 9:16** (เช่นคน 2 คนยืนห่างกันคนละมุมเฟรม) → shot นั้นสลับเป็น pad อัตโนมัติ
ไม่มี shot-type classifier อยู่ใน path เลย `apply_padding` เป็น bool ตัวเดียวต่อ scene = **ตัดสินใจต่อ shot จริง**

**นี่คือ rule ที่ clipcut ลอกได้ตรงตัว** และดีตรงที่มัน deterministic — อธิบายให้น้องตัดต่อฟังได้ว่าทำไมซีนนี้ถึงโดนย่อ

เกร็ดที่แก้ความเข้าใจผิด:
- **pad ไม่ได้เป็น blur เสมอ** — ถ้า BorderDetectionCalculator เจอว่าพื้นหลังเป็นสีเรียบ จะเติมเป็น solid interpolated color ไม่ blur ไม่หรี่ ไม่งั้นค่อย copy + GaussianBlur + ทับ black overlay (default `blur_cv_size: 200, overlay_opacity: 0.6`)
- blur นั้น copy มาจากเฟรมที่ crop+upscale แล้ว **ไม่ใช่ source frame**
- graph ที่ Google ship มา set `is_required: false` ให้ทุก signal → stock AutoFlip แทบไม่เคยเลือก pad เลย เป็น opt-in ที่ต้อง config เอง

## 2. temporal stability — อย่าใช้ EMA ต่อเฟรม

**prior art ทุกเจ้าไม่ smooth ต่อเฟรม แต่ fit เส้น camera path ทั้ง shot**

**AutoFlip** (ยืนยัน 3-0): fit polynomial ดีกรี 4 ต่อแกน x/y ด้วย Ceres least-squares + `CauchyLoss(0.5)` เป็น robust M-estimator
เหตุผลเป็นคำของ Google เอง — bounding box ดิบ "exhibit considerable jitter from frame-to-frame and, consequently, are not sufficient to define the cropping window"
ยังเลือก camera mode ต่อ scene 1 ใน 3 แบบด้วย: stationary / panning(sweeping) / tracking (`DecideCameraMotionType()`)

**Grundmann et al. CVPR 2011** (ยืนยัน 3-0) — ตั้งเป็น Linear Program minimize L1 norm ของ derivative ที่ 1/2/3 พร้อมกัน:

```
O(P) = w1|D(P)|₁ + w2|D²(P)|₁ + w3|D³(P)|₁      (w1=10, w2=1, w3=100)
```

L1 ทำให้คำตอบ sparse → path ออกมาเป็น segment แบบ **hold / pan / ease** จริง ไม่ใช่แค่กด jitter
paper บอกเองว่า L2 "always has some small non-zero motion" — คือ crop จะไหลไปเรื่อยๆ

**ทำไมเรื่องนี้สำคัญกับ clipcut มาก:** ฟุตเทจสัมภาษณ์ผู้สูงอายุนั่งนิ่ง = เคสที่ L1/polynomial ให้ locked-off shot สวยๆ แต่ EMA จะ drift ตามที่ paper อธิบายไว้เลย

Caveat ที่ต้องเผื่อ:
- LP solve เป็น **batch ทั้ง shot** ไม่ใช่ causal filter — แต่ clipcut เป็น offline batch อยู่แล้ว ไม่ติดข้อจำกัดนี้
- retargeting ต้องใช้ feature-path formulation ไม่ใช่ camera-path — ลอกแค่ camera-path LP จะไม่ได้ retargeting ฟรี
- paper **ไม่เคย demo 16:9 → 9:16** (Fig.12 เป็น widescreen แคบลงธรรมดา) 9:16 จาก 16:9 = crop กว้างแค่ ~31.6% ของเฟรม ทิ้ง pixel ~68% อยู่นอกช่วงที่ evaluate ปี 2011
- saliency source เดิมของ Grundmann คือ KLT motion tracks (สมมติ foreground เคลื่อนไหว) → **ไม่เหมาะกับคนนั่งนิ่ง** ต้องสลับเป็น face/person detection (paper รองรับ, Fig.1 ใช้ face detector)

Solver: paper ใช้ COIN CLP simplex — Python เทียบเท่าคือ PuLP/CBC หรือ `scipy.optimize.linprog`

## 3. pipeline ที่ประหยัดของจริง — ลอกได้เลย

จาก `autoflip_graph.pbtxt` (ยืนยัน verbatim 3-0):

| ขั้น | ทำที่ resolution/rate ไหน |
|---|---|
| scale ลง | `target_width: 480` คง aspect |
| **shot boundary detection** | stream ที่ scale แล้ว **แต่ full frame rate** |
| face/object detection | thin เหลือ **5 fps** (`period: 200000` µs) |
| crop จริง | `video_raw` ความละเอียดเต็ม |

shot detection เป็น **OpenCV ล้วน ไม่มี model**: `cv::calcHist` RGB 3D histogram 8 bins/channel เทียบเฟรมก่อนหน้าด้วย `1 - compareHist(CV_COMP_CORREL)` แล้ว gate ด้วย sliding window (`min_shot_span 0.2, min_motion 0.3, window_size 15`)

→ **PySceneDetect ContentDetector ที่เราติดตั้งไว้แล้วทำงานแบบเดียวกัน** ใช้ได้เลย
ข้อจำกัดร่วมกัน: พลาด dissolve/fade และ false-fire ตอนแสงเปลี่ยน/แฟลช — ฟุตเทจ YouTube ที่มี transition จะเจอ

## 4. AutoFlip เอามาใช้เป็น library ไม่ได้

(ยืนยัน 3-0) เป็น **Legacy Solution ที่ Google ยุติ support ตั้งแต่ 1 มี.ค. 2023** build ต้องใช้ Bazel + **OpenCV 3 เท่านั้น** (ซึ่ง EOL ตั้งแต่ปี 2018 และหาบน Apple Silicon ไม่ได้ง่าย) ไม่มีบน PyPI — `pip install mediapipe` ให้ Python Solutions API ไม่ใช่ `run_autoflip`

**สรุป: ต้อง reimplement algorithm เอง ไม่ใช่ adopt library** ซึ่งทำได้เพราะทุก rule ข้างบน verify ได้ถึงระดับ source code

(มี `pyautoflip` เป็น third-party Python reimplementation ที่ pip ได้ ยังไม่ได้ประเมิน)

## 5. เลือก detector ตัวไหน — license เป็นตัวตัดสิน

**ultralytics YOLO มีปัญหา license กับเคสของเรา** (ยืนยัน 3-0)

Ultralytics เป็น dual-license (AGPL-3.0 ฟรี / Enterprise เสียเงิน) และหน้า license ของเขาระบุเองว่าต้องซื้อ Enterprise สำหรับ:
- "Internal business tools or private company applications"
- "Proprietary / closed-source software"
- "R&D projects that are not fully open-sourced"

**clipcut = internal business tool ของบริษัท ตรงตัว**

⚠️ ข้อควรระวังเชิงกฎหมาย: นี่คือ**การตีความของ Ultralytics เอง** ไม่ใช่คำตัดสินทางกฎหมาย — GitHub issue #22458 (ต.ค. 2025, ปิดแบบ not planned) โต้ว่า private non-distributed use ไม่ trigger §5/§13 ของ AGPLv3 และไม่มี maintainer มาถอนคำ **เรื่องนี้ควรให้ฝ่ายกฎหมาย/ผู้บริหารตัดสิน ไม่ใช่ตัดสินจากงานวิจัยนี้** แต่ในทางปฏิบัติความเสี่ยงมีจริงพอที่จะเลี่ยง

**ทางที่สะอาด:**

| ตัวเลือก | License | หมายเหตุ |
|---|---|---|
| MediaPipe | Apache 2.0 | ไม่ต้องใช้ PyTorch, dependency เบา |
| RF-DETR (Nano/Small/Medium/Large + segmentation ทุกขนาด) | **Apache 2.0** | runtime deps ทั้งหมด Apache/BSD/MIT ไม่มี AGPL |
| RF-DETR XL/2XL detection, `rfdetr_plus` | PML 1.0 | ผูกกับ platform plan, สิทธิ์หายถ้า account ถูก suspend, ห้ามหลบ usage tracking — **เลี่ยง** |

**ไม่มี benchmark บน Apple Silicon เลยสักตัว** (ยืนยัน 3-0) — latency ทุกตัวเลขของ RF-DETR (2.3 ms Nano ถึง 17.2 ms 2XL) วัดบน **NVIDIA T4 + TensorRT FP16** ซึ่ง TensorRT ไม่มีบน macOS แถมยังใส่ buffer 200 ms ระหว่าง forward pass กัน thermal throttling → **ต้อง benchmark เองบนเครื่องจริง**

ข้อจำกัดของ MediaPipe ที่ต้องรู้ (medium, 2-1): Face Landmarker ทำ smoothing ให้**เฉพาะเมื่อ `num_faces = 1`** — ฟุตเทจที่มีผู้สัมภาษณ์ + ผู้สูงอายุในเฟรมจะไม่ได้ smoothing และ Pose Landmarker ไม่มี smoothing option เลย ต้องเขียน bounding-box filter เอง (ซึ่งเราจะเขียนอยู่แล้วตามข้อ 2)

---

## ข้อเสนอสถาปัตยกรรมสำหรับ clipcut

*(เป็น design opinion สังเคราะห์จาก finding ข้างบน ไม่ใช่ข้อเท็จจริงที่ verify ได้)*

```
1. shot detection   → PySceneDetect ContentDetector บน stream ที่ scale ลง 480px, full frame rate
2. detection        → MediaPipe face/pose ที่ ~5 fps บนภาพ 480px (+ RF-DETR person เมื่อต้องการ multi-person)
3. crop-vs-pad      → geometric rule ต่อ shot: required regions พอดี 9:16 มั้ย ถ้าไม่ → pad
4. camera path      → polynomial fit หรือ L1 LP ต่อ shot (ไม่ใช่ EMA ต่อเฟรม)
5. render           → ffmpeg crop/scale/pad บนไฟล์ความละเอียดเต็ม
```

**หลีกเลี่ยง ultralytics** ตลอดทั้งโปรเจกต์ รวมถึง repo ที่ depend มัน

## แหล่งอ้างอิงหลัก

- [AutoFlip docs](https://github.com/google-ai-edge/mediapipe/blob/master/docs/solutions/autoflip.md) · [autoflip_graph.pbtxt](https://github.com/google-ai-edge/mediapipe/blob/master/mediapipe/examples/desktop/autoflip/autoflip_graph.pbtxt)
- [Google Research blog — AutoFlip](https://research.google/blog/autoflip-an-open-source-framework-for-intelligent-video-reframing/) (2020)
- [Grundmann et al., Auto-Directed Video Stabilization with Robust L1 Optimal Camera Paths](https://cpl.cc.gatech.edu/projects/videostabilization/) — CVPR 2011, DOI 10.1109/CVPR.2011.5995525
- [Ultralytics license](https://www.ultralytics.com/license) · [issue #22458](https://github.com/ultralytics/ultralytics/issues/22458)
- [RF-DETR](https://github.com/roboflow/rf-detr) · [benchmarks](https://rfdetr.roboflow.com/develop/learn/benchmarks/)
- [MediaPipe Face Landmarker](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker)

source ที่ต้องระวัง: [auto-vertical-reframe](https://github.com/KazKozDev/auto-vertical-reframe) ใช้เป็น existence proof ของ spring-damper smoothing แบบง่ายได้ แต่ **19 ดาว 2 forks commit ทั้งหมด push ใน 10 ชม. self-described Beta** และตัวมันเอง MIT แต่ depend AGPL ultralytics — ห้ามอ้างเป็น best practice

---

## ยังไม่ได้คำตอบ — ต้องวิจัยรอบสอง

**verification budget หมดก่อนถึง 3 angle นี้ ไม่ใช่ว่าหาไม่เจอ** แหล่งถูกดึงมาแล้วแต่ไม่ได้ผ่านการตรวจ

### 1. Thai OCR / burned-in text detection
ตัวไหนแม่นจริงกับข้อความไทยบนวีดีโอ และ text *detection* อย่างเดียว (DBNet/CRAFT/EAST) พอมั้ยสำหรับ use case ที่แค่ต้องรายงานตำแหน่งกล่องข้อความ

lead ที่ยังไม่ได้ verify: [PP-OCRv5 multi-language](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.en.md) · [typhoon-ocr (SCB 10X, ไทยโดยเฉพาะ)](https://github.com/scb-10x/typhoon-ocr) · [Apple Vision supported languages](https://developer.apple.com/documentation/vision/vnrecognizetextrequest/supportedrecognitionlanguages(for:revision:)) · arXiv 2511.04479

### 2. export ไป CapCut / Hyperframe — **ความเสี่ยงสูงสุดของโปรเจกต์**
กระทบ output format ทั้งหมด ถ้า export timeline ได้จะข้ามขั้น "ประกอบใหม่" ไปเลย

lead ที่ยังไม่ได้ verify: [pyCapCut](https://github.com/GuanYixuan/pyCapCut) · [capcut-cli](https://github.com/renezander030/capcut-cli) · [capcut-export](https://github.com/emosheeep/capcut-export) · [OTIO adapters](https://opentimelineio.readthedocs.io/en/latest/tutorials/adapters.html) · [otio-fcp-adapter](https://github.com/OpenTimelineIO/otio-fcp-adapter)

**ไม่เจอข้อมูลเรื่อง Hyperframe เลยแม้แต่แหล่งเดียว**

### 3. highlight / hook detection จาก transcript
lead ที่ยังไม่ได้ verify: [Opus Clip virality score](https://help.opus.pro/docs/article/virality-score) · arXiv 2505.23908, 2412.08879, 2511.11594

### 4. คำถามที่ต้องทดสอบกับ footage จริง ไม่ใช่รีเสิช
- MediaPipe face/pose แม่นพอมั้ยกับฟุตเทจในบ้าน แสงไม่ดี ผู้สูงอายุ 2 คนในเฟรม เทียบกับ RF-DETR
- บน M-series วิ่งได้กี่ fps จริง — จะ detect ทุกเฟรมได้ หรือต้อง 5 fps แบบ AutoFlip
- **threshold ของ "ครอบไม่หมด" ควรตั้งเท่าไหร่** เมื่อ 9:16 กินแค่ ~31.6% ของความกว้างเฟรม
- เมื่อครอบไม่หมดจริงๆ ควร pad+blur, แยกเป็น 2 crop แล้วตัดสลับ (prior art ที่ verify มาไม่มีใครทำ), หรือส่งต่อให้คนตัดสิน

## หมายเหตุเรื่องความสดของข้อมูล

AutoFlip = ระบบที่แช่แข็งแล้ว (EOL 2023) blog ปี 2020, Grundmann ปี 2011 — ใช้อ้างได้ในฐานะ **formulation** ที่ยัง valid ไม่ใช่ current best practice วงการย้ายไป learned stabilization แล้ว
license terms ของ Ultralytics/Roboflow ต้องเช็คซ้ำตอนจะ pin version จริง
path source code ในรีโป mediapipe อ่านจาก branch master ณ ส.ค. 2026 — เป็น legacy code อาจถูกย้าย/ลบได้
