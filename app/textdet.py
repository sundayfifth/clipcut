"""หาข้อความที่ burn อยู่ในเฟรม ด้วย Apple Vision

ทำไมเลือก Apple Vision (ดู docs/2026-08-27-research-thai-ocr.md):
- เป็นตัวเดียวที่ยืนยันได้ว่ารองรับภาษาไทย โดย probe บนเครื่องนี้จริง
- ไม่มีปัญหา license เลย (system framework + pyobjc ซึ่งเป็น MIT)
- ไม่ต้องโหลดโมเดล ไม่ต้องต่อเน็ต
- วัดบนเครื่องนี้ได้ 131 ms/เฟรม พอสำหรับ 50 คลิป

**ต้องใช้ revision 3 + recognitionLevel accurate (=0) เท่านั้น**
ระดับ fast ไม่มีภาษาไทยเลยทุก revision — ถ้าใช้ fast จะได้ผลลัพธ์เป็นขยะ
(ดูตัวอย่างในงานวิจัย: fast อ่าน "เนื่องจากหลังการผ่าตัด" เป็น "InfrlAoni%HIGiA")

เราสนใจ *ตำแหน่ง* ของข้อความเป็นหลัก ไม่ใช่ตัวอักษร แต่ก็เก็บข้อความไว้ด้วย
เพราะช่วยให้คนตัดต่อรู้ว่าต้องทำกราฟฟิกอะไรใหม่โดยไม่ต้องเปิดคลิปดู
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path

from app.analyze import AnalyzeError, Shot

# ต่ำกว่านี้มักเป็นลายพื้นหลังที่ Vision เดาว่าเป็นตัวอักษร
MIN_CONFIDENCE = 0.30

# กี่เฟรมต่อซีน — ซับเปลี่ยนทุก 2-4 วิ เอา 3 เฟรมพอเห็นความเปลี่ยนแปลง
FRAMES_PER_SHOT = 3


@dataclass
class TextBox:
    """พิกัดแบบ 0-1 อ้างมุมซ้ายบน (Vision คืนมาแบบซ้ายล่าง แปลงแล้ว)"""

    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    confidence: float
    # โผล่ที่ตำแหน่งเดิมหลายซีน = โลโก้/ลายน้ำประจำช่อง ไม่ใช่กราฟฟิกรายซีน
    persistent: bool = False

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def center_y(self) -> float:
        return (self.y0 + self.y1) / 2

    def as_dict(self) -> dict:
        return {k: (round(v, 4) if isinstance(v, float) else v)
                for k, v in asdict(self).items()}


def available() -> bool:
    try:
        import Vision  # noqa: F401
        import Quartz  # noqa: F401
    except ImportError:
        return False
    return True


def _detect_image(path: Path) -> list[TextBox]:
    import Quartz
    import Vision

    url = Quartz.NSURL.fileURLWithPath_(str(path))
    source = Quartz.CGImageSourceCreateWithURL(url, None)
    if source is None:
        return []
    image = Quartz.CGImageSourceCreateImageAtIndex(source, 0, None)
    if image is None:
        return []

    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRevision_(3)
    request.setRecognitionLevel_(0)  # 0 = accurate — ระดับเดียวที่มีภาษาไทย
    request.setRecognitionLanguages_(["th-TH", "en-US"])
    request.setUsesLanguageCorrection_(True)

    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(image, None)
    handler.performRequests_error_([request], None)

    boxes: list[TextBox] = []
    for obs in request.results() or []:
        candidates = obs.topCandidates_(1)
        if not candidates:
            continue
        conf = float(candidates[0].confidence())
        if conf < MIN_CONFIDENCE:
            continue
        bb = obs.boundingBox()
        x, y, w, h = bb.origin.x, bb.origin.y, bb.size.width, bb.size.height
        boxes.append(TextBox(
            x0=float(x), x1=float(x + w),
            # Vision นับ y จากล่างขึ้นบน พลิกให้เป็นแบบเดียวกับพิกัดภาพ
            y0=float(1.0 - (y + h)), y1=float(1.0 - y),
            text=str(candidates[0].string()),
            confidence=conf,
        ))
    return boxes


def detect_shots_text(
    video: Path, shots: list[Shot], work_dir: Path, on_progress=None
) -> dict[int, list[TextBox]]:
    """คืน {shot_index: [TextBox]} โดย sample ไม่กี่เฟรมต่อซีน"""
    if not available():
        return {}

    frames_dir = work_dir / "textframes"
    frames_dir.mkdir(parents=True, exist_ok=True)
    out: dict[int, list[TextBox]] = {}

    for i, shot in enumerate(shots, start=1):
        found: list[TextBox] = []
        span = max(0.05, shot.duration)
        for k in range(FRAMES_PER_SHOT):
            at = shot.start + span * (k + 0.5) / FRAMES_PER_SHOT
            frame = frames_dir / f"s{shot.index:04d}-{k}.png"
            result = subprocess.run(
                ["ffmpeg", "-nostdin", "-y", "-loglevel", "error",
                 "-ss", f"{at:.3f}", "-i", str(video), "-frames:v", "1", str(frame)],
                capture_output=True, timeout=120,
            )
            if result.returncode != 0 or not frame.exists():
                continue
            try:
                found.extend(_detect_image(frame))
            finally:
                frame.unlink(missing_ok=True)

        out[shot.index] = _merge(found)
        if on_progress:
            on_progress(i / len(shots))
    return out


def _norm(text: str) -> str:
    return "".join(text.split()).lower()


def _merge(boxes: list[TextBox]) -> list[TextBox]:
    """รวมกล่องซ้ำจากหลายเฟรมในซีนเดียวกัน เก็บอันที่มั่นใจสุดไว้

    ซ้ำได้ 2 แบบ: ทับกันในตำแหน่ง (ข้อความนิ่ง) หรือข้อความเดียวกันคนละตำแหน่ง
    (กราฟฟิกเคลื่อนไหวเลื่อนเข้ามาระหว่างเฟรมที่ sample)
    """
    kept: list[TextBox] = []
    seen_text: set[str] = set()
    for box in sorted(boxes, key=lambda b: b.confidence, reverse=True):
        key = _norm(box.text)
        if key and key in seen_text:
            continue
        if any(_overlaps(box, other) for other in kept):
            continue
        kept.append(box)
        if key:
            seen_text.add(key)
    return sorted(kept, key=lambda b: (b.y0, b.x0))


def _overlaps(a: TextBox, b: TextBox, threshold: float = 0.4) -> bool:
    ix = max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0))
    iy = max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))
    inter = ix * iy
    if inter <= 0:
        return False
    smaller = min((a.x1 - a.x0) * (a.y1 - a.y0), (b.x1 - b.x0) * (b.y1 - b.y0))
    return smaller > 0 and inter / smaller >= threshold


def mark_persistent(text_by_shot: dict[int, list[TextBox]]) -> None:
    """ทำเครื่องหมายข้อความที่อยู่ตำแหน่งเดิมข้ามหลายซีน

    โลโก้ช่องโผล่ทุกซีนที่มุมเดิม ถ้ารายงานทีละซีนจะกลายเป็นรายการยาวเหยียด
    ที่คนตัดต่อไม่ได้ต้องทำอะไรกับมัน (เจอจริง: "โลโก้ช่อง" ขึ้น 9 ครั้ง)
    """
    if not text_by_shot:
        return
    threshold = max(3, round(len(text_by_shot) * 0.25))

    groups: list[tuple[float, float, set[int], list[TextBox]]] = []
    for shot_index, boxes in text_by_shot.items():
        for box in boxes:
            for i, (gx, gy, shots, members) in enumerate(groups):
                if abs(gx - box.x0) <= 0.04 and abs(gy - box.y0) <= 0.04:
                    shots.add(shot_index)
                    members.append(box)
                    break
            else:
                groups.append((box.x0, box.y0, {shot_index}, [box]))

    for _, _, shots, members in groups:
        if len(shots) >= threshold:
            for box in members:
                box.persistent = True


def _percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = q * (len(ordered) - 1)
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


def suggest_bands(text_by_shot: dict[int, list[TextBox]]) -> dict:
    """เดาแถบซับ/โลโก้จากข้อความที่เจอจริง

    สัญญาณที่ใช้คือ **ตำแหน่งเดิมซ้ำๆ ข้ามหลายซีน** ไม่ใช่แค่ "อยู่ล่าง"
    เพราะคลิปที่มีสกรีนช็อตเยอะจะมีข้อความเต็มไปหมดทุกตำแหน่ง
    (ทดสอบแล้ว: ถ้าดูแค่ตำแหน่ง จะแนะนำให้ตัดทิ้งครึ่งจอ)

    ซับจริงจะอยู่แถวเดิมทุกครั้งที่โผล่ ส่วนข้อความในสกรีนช็อตจะกระจาย
    """
    if not text_by_shot:
        return {"top": 0.0, "bottom": 0.0}

    total_shots = max(1, len(text_by_shot))
    min_shots = max(2, round(total_shots * 0.20))

    def cluster(pick_edge, keep, tolerance: float = 0.03) -> float | None:
        """จับกลุ่มกล่องที่ขอบอยู่ระดับเดียวกัน คืนขอบของกลุ่มที่โผล่ในซีนมากที่สุด"""
        rows: list[tuple[float, set[int]]] = []
        for shot_index, boxes in text_by_shot.items():
            for box in boxes:
                if not keep(box):
                    continue
                edge = pick_edge(box)
                for i, (value, shots) in enumerate(rows):
                    if abs(value - edge) <= tolerance:
                        shots.add(shot_index)
                        # ค่อยๆ ขยับค่ากลางของกลุ่มตามสมาชิกใหม่
                        rows[i] = ((value * len(shots) + edge) / (len(shots) + 1), shots)
                        break
                else:
                    rows.append((edge, {shot_index}))

        if not rows:
            return None
        edge, shots = max(rows, key=lambda r: len(r[1]))
        return edge if len(shots) >= min_shots else None

    # ซับ: กว้างพอควร อยู่ท่อนล่างของเฟรม
    sub_edge = cluster(
        lambda b: b.y0,
        lambda b: b.center_y > 0.75 and b.width > 0.20,
    )
    bottom = round(min(max(0.0, 1.0 - sub_edge) + 0.02, 0.45), 3) if sub_edge else 0.0

    # โลโก้: เล็ก อยู่ท่อนบนของเฟรม
    logo_edge = cluster(
        lambda b: b.y1,
        lambda b: b.center_y < 0.20 and b.width < 0.25,
    )
    top = round(min(logo_edge + 0.02, 0.45), 3) if logo_edge else 0.0

    return {"top": top, "bottom": bottom}
