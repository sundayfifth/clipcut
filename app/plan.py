"""ตัดสินต่อ shot ว่าจะ crop หรือย่อ+เติมพื้นหลัง แล้วสร้าง edit plan

กติกาเป็น geometric fallback แบบ AutoFlip (docs/2026-08-25-research-auto-reframe.md):
ไม่เดาจากประเภทของ shot แต่ดูว่ากรอบ 9:16 ครอบสิ่งที่ต้องเห็นได้มั้ย

**สิ่งที่ "ต้องเห็น" คือตำแหน่งของ subject ไม่ใช่ตัว subject ทั้งตัว** — จุดนี้สำคัญ
รอบแรกเขียนผิดโดยบังคับให้ตัวคนทั้งตัวต้องอยู่ในกรอบ ผลคือ 23 จาก 25 ซีน
กลายเป็น pad หมด ทั้งที่คนตัวใหญ่เต็มเฟรมแค่ crop เข้าไปที่ตัวเขาก็พอ
(ตรงกับที่ผู้ใช้บอกเองว่า "บางซีนอยากให้เห็นภาพคน ก็เห็นได้บางส่วน")

งานวิจัยเตือนไว้ด้วยว่า graph ที่ AutoFlip ship มา set is_required: false ให้ทุก signal
แปลว่า pad เป็น opt-in ไม่ใช่ default — เราจึง pad เฉพาะเคสที่ crop แล้วเสียของจริงๆ:
  1. ไม่เจอคนเลย (มักเป็นภาพหน้าจอ/กราฟฟิก ซึ่ง crop แล้วข้อความหาย)
  2. subject ขยับแนวนอนกว้างเกินกว่ากรอบนิ่งจะตามไหว
  3. มีคนสำคัญหลายคนอยู่คนละฝั่งจนกรอบเดียวครอบไม่ได้
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np

from app.analyze import Shot, VideoInfo
from app.bands import Bands
from app.detect import Box, ShotDetections

# ขนาด output มาตรฐานของ TikTok
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920
TARGET_RATIO = TARGET_WIDTH / TARGET_HEIGHT  # 0.5625

# ถ้าเจอคนน้อยกว่านี้ ถือว่าการตรวจจับไม่น่าเชื่อถือพอจะเอามาตัดสิน crop
MIN_HIT_RATE = 0.30

# subject ขยับได้ไม่เกินสัดส่วนนี้ของกรอบ ถ้าเกินแปลว่ากรอบนิ่งตามไม่ทัน
MAX_CENTER_DRIFT = 0.55

# คนที่ตัวใหญ่อย่างน้อยเท่านี้เทียบกับคนหลัก ถือว่าเป็น subject ร่วม ไม่ใช่คนเดินผ่าน
CO_SUBJECT_AREA_RATIO = 0.40

# ถ้ามี subject ร่วมที่ครอบไม่ไหวเกินสัดส่วนนี้ของเฟรม ให้ pad
CO_SUBJECT_FRAME_RATIO = 0.50

# ขยับน้อยกว่านี้ถือว่านิ่ง ใช้กรอบคงที่ไปเลย — กล้องที่ขยับนิดเดียวดูกวนตามากกว่านิ่งสนิท
STATIC_THRESHOLD_PX = 24.0

# ดีกรีสูงสุดของเส้นทางกล้อง ต่ำไว้กันเส้นแกว่งตอน extrapolate (งานวิจัย: AutoFlip ใช้ 4)
MAX_PATH_DEGREE = 3

# ถ้า crop แล้วข้อความจะหายตั้งแต่เท่านี้จุดขึ้นไป ให้ย่อทั้งภาพแทน
# ย่อแล้วข้อความอยู่ครบ ไม่ต้องทำกราฟฟิกใหม่เลย แลกกับภาพเล็กลงในซีนนั้น
# วัดกับคลิปจริง: เกณฑ์ 3 พลิก 4 ซีน ประหยัดงาน 39 จาก 42 จุด
# ส่วนเกณฑ์ 1-2 พลิกเพิ่มอีก 2 ซีนแลกกับแค่ 3 จุด ไม่คุ้ม
TEXT_LOSS_LIMIT = 3


@dataclass
class ShotPlan:
    shot_index: int
    start: float
    end: float
    mode: str  # "crop" | "pad"
    reason: str
    crop: dict | None  # {x, y, w, h} ในหน่วย pixel (เฉพาะ mode=crop)
    confidence: float  # สัดส่วนเฟรมที่เจอคน
    included: bool = True  # เอาซีนนี้ไปประกอบเป็นไฟล์ 9:16 มั้ย
    path: dict | None = None  # เส้นทางกล้อง {kind: static|poly, coeffs: [...]}
    # กรอบฐานที่เครื่องคำนวณ เก็บไว้เพื่อให้คนปรับเป็น "ส่วนต่าง" ได้โดยไม่เสียการ tracking
    crop_base: dict | None = None
    adjust: dict | None = None  # {dx, dy, scale} — dx/dy เป็นสัดส่วนของกรอบ
    # มีเสียงพูดในซีนนี้มั้ย ใช้เตือนตอนคนจะตัดซีนออก
    has_speech: bool = False
    audio_db: float | None = None
    # ข้อความที่ burn อยู่ในเฟรม (พิกัด 0-1 อ้างมุมซ้ายบน)
    text_boxes: list | None = None

    def as_dict(self) -> dict:
        return {**asdict(self), "duration": round(self.end - self.start, 3)}


def _percentile(values: list[float], q: float) -> float:
    """percentile แบบง่าย ไม่ต้องลาก numpy เข้ามา"""
    if not values:
        raise ValueError("empty")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = q * (len(ordered) - 1)
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


def _fit_path(times: list[float], centers: list[float]) -> dict | None:
    """fit เส้นทางกล้องเป็น polynomial ดีกรีต่ำ ตามที่ AutoFlip ทำ

    งานวิจัยบอกว่าอย่า smooth กรอบทีละเฟรม (jitter) และอย่าใช้ EMA (กรอบจะไหลไม่หยุด)
    ให้ fit เส้นทั้ง shot ทีเดียว — ดู docs/2026-08-25-research-auto-reframe.md
    """
    if len(times) < 4:
        return None
    degree = min(MAX_PATH_DEGREE, len(times) - 1)
    try:
        coeffs = np.polyfit(np.array(times), np.array(centers), degree)
    except Exception:
        return None
    if not np.all(np.isfinite(coeffs)):
        return None
    # polyfit คืนดีกรีสูงก่อน กลับด้านให้เป็น c0 + c1*t + c2*t^2 ... อ่านง่ายฝั่ง render
    return {"kind": "poly", "coeffs": [float(c) for c in reversed(coeffs)]}


def _co_subject_conflicts(frames: list[list[Box]], crop_w: float) -> float:
    """สัดส่วนเฟรมที่มี subject ร่วมอยู่ไกลจนกรอบเดียวครอบทั้งคู่ไม่ได้"""
    conflicts = 0
    for boxes in frames:
        if len(boxes) < 2:
            continue
        primary = boxes[0]
        peers = [b for b in boxes[1:] if b.area >= primary.area * CO_SUBJECT_AREA_RATIO]
        if not peers:
            continue
        centers = [primary.center_x] + [b.center_x for b in peers]
        if max(centers) - min(centers) > crop_w:
            conflicts += 1
    return conflicts / len(frames) if frames else 0.0


DEFAULT_ADJUST = {"dx": 0.0, "dy": 0.0, "scale": 1.0}

# ซูมเข้าได้ถึง 40% ของกรอบเต็ม แคบกว่านั้นภาพจะแตกเพราะต้องขยายขึ้น 1080px
MIN_SCALE = 0.40
MAX_SCALE = 1.00


def clamp_adjust(adjust: dict | None) -> dict:
    a = {**DEFAULT_ADJUST, **(adjust or {})}
    return {
        "dx": max(-1.0, min(1.0, float(a["dx"]))),
        "dy": max(-1.0, min(1.0, float(a["dy"]))),
        "scale": max(MIN_SCALE, min(MAX_SCALE, float(a["scale"]))),
    }


def derive_crop(base: dict, adjust: dict | None, info: VideoInfo) -> dict:
    """กรอบจริง = กรอบฐานที่เครื่องคำนวณ + ส่วนต่างที่คนปรับ

    เก็บเป็นส่วนต่างแทนที่จะทับค่าไปเลย เพื่อให้ยัง fit เส้นทางกล้องตามคนได้อยู่
    แค่เลื่อน/ย่อกรอบทั้งเส้นตามที่คนสั่ง
    """
    a = clamp_adjust(adjust)
    w = base["w"] * a["scale"]
    h = base["h"] * a["scale"]

    center_x = base["center_x"] + a["dx"] * base["w"]
    left = max(0.0, min(center_x - w / 2, info.width - w))

    # ย่อกรอบแล้วเหลือที่ให้ขยับแนวตั้ง — เลื่อนจากกึ่งกลางของแถบที่ใช้ได้
    span_top = base["y"]
    span_h = base["h"]
    center_y = span_top + span_h / 2 + a["dy"] * span_h / 2
    top = max(float(span_top), min(center_y - h / 2, span_top + span_h - h))

    return {"x": int(round(left)), "y": int(round(top)),
            "w": int(round(w)), "h": int(round(h))}


def plan_shot(
    shot: Shot, info: VideoInfo, dets: ShotDetections, bands: Bands | None = None
) -> ShotPlan:
    bands = bands or Bands()
    # แถบที่ตัดทิ้งทำให้ความสูงที่ใช้ได้ลดลง กรอบ 9:16 จึงแคบลงตาม
    crop_h = bands.effective_height(info.height)
    crop_y = bands.offset_y(info.height)
    crop_w = crop_h * TARGET_RATIO
    if crop_w > info.width:  # ต้นฉบับแคบกว่า 9:16 อยู่แล้ว
        crop_w = info.width
        crop_h = min(crop_h, int(crop_w / TARGET_RATIO))

    common = {
        "shot_index": shot.index,
        "start": shot.start,
        "end": shot.end,
        "confidence": round(dets.hit_rate, 3),
    }

    if not dets.per_frame:
        return ShotPlan(
            mode="pad",
            reason="ไม่เจอคนในซีนนี้ น่าจะเป็นภาพหน้าจอหรือกราฟฟิก ย่อไว้จะได้เห็นครบ",
            crop=None, **common,
        )
    if dets.hit_rate < MIN_HIT_RATE:
        return ShotPlan(
            mode="pad",
            reason="เห็นคนไม่ชัดตลอดซีน ย่อไว้ก่อนปลอดภัยกว่า",
            crop=None, **common,
        )

    conflict_rate = _co_subject_conflicts(dets.boxes, crop_w)
    if conflict_rate >= CO_SUBJECT_FRAME_RATIO:
        return ShotPlan(
            mode="pad",
            reason="มีคนสำคัญหลายคนอยู่คนละฝั่ง ถ้าเต็มจอจะเห็นไม่ครบ",
            crop=None, **common,
        )

    # ติดตามเฉพาะ subject หลัก (คนตัวใหญ่สุดในเฟรม)
    times = [t for t, _ in dets.per_frame]
    centers = [boxes[0].center_x for _, boxes in dets.per_frame]
    lo, hi = _percentile(centers, 0.10), _percentile(centers, 0.90)
    drift = hi - lo

    if drift > crop_w * MAX_CENTER_DRIFT:
        return ShotPlan(
            mode="pad",
            reason="คนเดินไปมากว้างเกินไป ถ้าเต็มจอจะหลุดเฟรม",
            crop=None, **common,
        )

    base = {"center_x": (lo + hi) / 2, "w": crop_w, "h": crop_h, "y": crop_y}
    crop = derive_crop(base, None, info)
    common["crop_base"] = base

    if drift <= STATIC_THRESHOLD_PX:
        return ShotPlan(
            mode="crop",
            reason="คนอยู่นิ่ง กรอบล็อกอยู่กับที่",
            crop=crop, path={"kind": "static"}, **common,
        )

    path = _fit_path(times, centers)
    if path is None:
        return ShotPlan(
            mode="crop",
            reason="คนอยู่ในกรอบตลอดซีน",
            crop=crop, path={"kind": "static"}, **common,
        )

    return ShotPlan(
        mode="crop",
        reason="กรอบขยับตามคนตลอดซีน",
        crop=crop, path=path, **common,
    )


def annotate_lost_text(shot_plan: dict, info: VideoInfo, bands: Bands) -> None:
    """ทำเครื่องหมายว่ากล่องข้อความไหนจะหายไปหลังตัดแถบ/crop

    "หาย" หมายถึงถูกตัดออกไปเกินครึ่งกล่อง — เหลือครึ่งเดียวก็อ่านไม่รู้เรื่องแล้ว
    """
    boxes = shot_plan.get("text_boxes") or []
    if not boxes:
        return

    top = bands.top
    bottom = 1.0 - bands.bottom
    crop = shot_plan.get("crop") if shot_plan.get("mode") == "crop" else None
    left = crop["x"] / info.width if crop else 0.0
    right = (crop["x"] + crop["w"]) / info.width if crop else 1.0

    for box in boxes:
        w = max(1e-6, box["x1"] - box["x0"])
        h = max(1e-6, box["y1"] - box["y0"])
        visible_w = max(0.0, min(box["x1"], right) - max(box["x0"], left))
        visible_h = max(0.0, min(box["y1"], bottom) - max(box["y0"], top))
        kept = (visible_w / w) * (visible_h / h)
        box["kept"] = round(kept, 3)
        box["lost"] = kept < 0.5
        # แยกให้ออกว่าหายเพราะโดนตัดแถบ (ซับ ซึ่งจะใส่ใหม่อยู่แล้ว)
        # หรือหายเพราะ crop ข้าง (กราฟฟิก ซึ่งต้องทำใหม่)
        box["cause"] = (
            "band" if visible_h / h < 0.5 else "crop" if visible_w / w < 0.5 else ""
        )
        # โลโก้ประจำช่องไม่นับเป็นงานรายซีน รายงานรวมทีเดียวใน checklist แทน
        if box.get("persistent"):
            box["cause"] = "persistent" if box["lost"] else box["cause"]


def prefer_pad_over_losing_text(shot_plan: dict, info: VideoInfo, bands: Bands) -> None:
    """ซีนที่ crop แล้วข้อความหายเยอะ ให้ย่อทั้งภาพแทน

    เหตุผล: ย่อแล้วข้อความอยู่ครบทั้งหมด ไม่ต้องทำกราฟฟิกใหม่เลย
    แลกกับภาพเล็กลงในซีนนั้น ซึ่งคุ้มกว่าการนั่งทำกราฟฟิกใหม่ทีละชิ้น

    ไม่แตะซีนที่คนเลือกโหมดเอง
    """
    if shot_plan.get("mode") != "crop" or shot_plan.get("manual_mode"):
        return

    # โลโก้ประจำช่องไม่นับ — รายงานรวมทีเดียวอยู่แล้ว วางใหม่ครั้งเดียวคลุมทั้งคลิป
    losing = [
        b for b in (shot_plan.get("text_boxes") or [])
        if b.get("lost") and b.get("cause") == "crop" and not b.get("persistent")
    ]
    if len(losing) < TEXT_LOSS_LIMIT:
        return

    shot_plan["mode"] = "pad"
    shot_plan["reason"] = (
        f"ถ้าเต็มจอ ข้อความจะหาย {len(losing)} จุด ย่อทั้งภาพแทนจะได้ไม่ต้องทำกราฟฟิกใหม่"
    )
    shot_plan["auto_pad_for_text"] = True
    # โหมดเปลี่ยนแล้ว สาเหตุการหายของแต่ละกล่องเปลี่ยนตาม ต้องคำนวณใหม่
    annotate_lost_text(shot_plan, info, bands)


def summarise(shots: list[dict]) -> dict:
    included = [s for s in shots if s.get("included", True)]
    dropped_speech = [
        s for s in shots if not s.get("included", True) and s.get("has_speech")
    ]
    return {
        "total": len(shots),
        "included": len(included),
        "crop": sum(1 for s in included if s["mode"] == "crop"),
        "pad": sum(1 for s in included if s["mode"] == "pad"),
        "duration": round(sum(s["end"] - s["start"] for s in included), 2),
        # ตัดซีนที่มีคนพูดออก = ประโยคขาดกลางคัน ต้องเตือน
        "dropped_with_speech": len(dropped_speech),
    }


def build_plan(
    source: Path,
    info: VideoInfo,
    shots: list[Shot],
    detections: list[ShotDetections],
    bands: Bands | None = None,
    audio: dict[int, dict] | None = None,
    text: dict | None = None,
    text_detection: bool = True,
) -> dict:
    """edit plan — contract กลางที่ทุก module คุยกันผ่านมัน (ดู CLAUDE.md)"""
    bands = bands or Bands()
    by_index = {d.shot_index: d for d in detections}
    plans = [plan_shot(s, info, by_index[s.index], bands) for s in shots]
    shot_dicts = [p.as_dict() for p in plans]
    for d in shot_dicts:
        level = (audio or {}).get(d["shot_index"]) or {}
        d["has_speech"] = bool(level.get("has_speech"))
        d["audio_db"] = level.get("db")
        d["text_boxes"] = [b.as_dict() for b in (text or {}).get(d["shot_index"], [])]
        annotate_lost_text(d, info, bands)
        prefer_pad_over_losing_text(d, info, bands)
    return {
        "version": 2,
        "source": source.name,
        "source_size": {"width": info.width, "height": info.height},
        "target_size": {"width": TARGET_WIDTH, "height": TARGET_HEIGHT},
        "bands": bands.as_dict(),
        # เครื่องนี้อ่านข้อความในเฟรมได้มั้ย (Apple Vision มีเฉพาะบน macOS)
        # ถ้าไม่ได้ ห้ามสรุปว่า "ไม่มีข้อความหาย" เพราะจริงๆ คือมองไม่เห็น
        "text_detection": bool(text_detection),
        "shots": shot_dicts,
        "summary": summarise(shot_dicts),
    }
