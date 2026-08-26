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

from app.analyze import Shot, VideoInfo
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


@dataclass
class ShotPlan:
    shot_index: int
    start: float
    end: float
    mode: str  # "crop" | "pad"
    reason: str
    crop: dict | None  # {x, y, w, h} ในหน่วย pixel ของต้นฉบับ (เฉพาะ mode=crop)
    confidence: float  # สัดส่วนเฟรมที่เจอคน

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


def plan_shot(shot: Shot, info: VideoInfo, dets: ShotDetections) -> ShotPlan:
    # กรอบ 9:16 ที่ครอบได้มากที่สุดจากเฟรมต้นฉบับ
    crop_h = info.height
    crop_w = crop_h * TARGET_RATIO
    if crop_w > info.width:  # ต้นฉบับแคบกว่า 9:16 อยู่แล้ว
        crop_w = info.width
        crop_h = crop_w / TARGET_RATIO

    common = {
        "shot_index": shot.index,
        "start": shot.start,
        "end": shot.end,
        "confidence": round(dets.hit_rate, 3),
    }

    if not dets.per_frame:
        return ShotPlan(
            mode="pad",
            reason="ไม่เจอคนในซีนนี้ — น่าจะเป็นภาพหน้าจอหรือกราฟฟิก ย่อลงให้เห็นครบดีกว่า",
            crop=None, **common,
        )
    if dets.hit_rate < MIN_HIT_RATE:
        return ShotPlan(
            mode="pad",
            reason=f"เจอคนแค่ {dets.hit_rate:.0%} ของเฟรม ไม่มั่นใจพอจะ crop",
            crop=None, **common,
        )

    conflict_rate = _co_subject_conflicts(dets.per_frame, crop_w)
    if conflict_rate >= CO_SUBJECT_FRAME_RATIO:
        return ShotPlan(
            mode="pad",
            reason=f"มีคนสำคัญหลายคนอยู่คนละฝั่งใน {conflict_rate:.0%} ของเฟรม กรอบเดียวครอบไม่ไหว",
            crop=None, **common,
        )

    # ติดตามเฉพาะ subject หลัก (คนตัวใหญ่สุดในเฟรม)
    centers = [boxes[0].center_x for boxes in dets.per_frame]
    lo, hi = _percentile(centers, 0.10), _percentile(centers, 0.90)
    drift = hi - lo

    if drift > crop_w * MAX_CENTER_DRIFT:
        return ShotPlan(
            mode="pad",
            reason=f"คนขยับซ้ายขวา {drift:.0f}px กว้างเกินกว่ากรอบนิ่งจะตามไหว",
            crop=None, **common,
        )

    # crop ได้ — วางกรอบไว้กลางช่วงที่ subject อยู่ แล้วดันกลับเข้าเฟรมถ้าล้น
    left = (lo + hi) / 2 - crop_w / 2
    left = max(0.0, min(left, info.width - crop_w))

    return ShotPlan(
        mode="crop",
        reason=f"ตาม subject หลักได้ (ขยับ {drift:.0f}px ในกรอบ {crop_w:.0f}px)",
        crop={
            "x": int(round(left)),
            "y": 0,
            "w": int(round(crop_w)),
            "h": int(round(crop_h)),
        },
        **common,
    )


def build_plan(
    source: Path, info: VideoInfo, shots: list[Shot], detections: list[ShotDetections]
) -> dict:
    """edit plan — contract กลางที่ทุก module คุยกันผ่านมัน (ดู CLAUDE.md)"""
    by_index = {d.shot_index: d for d in detections}
    plans = [plan_shot(s, info, by_index[s.index]) for s in shots]
    return {
        "version": 1,
        "source": source.name,
        "source_size": {"width": info.width, "height": info.height},
        "target_size": {"width": TARGET_WIDTH, "height": TARGET_HEIGHT},
        "shots": [p.as_dict() for p in plans],
        "summary": {
            "total": len(plans),
            "crop": sum(1 for p in plans if p.mode == "crop"),
            "pad": sum(1 for p in plans if p.mode == "pad"),
        },
    }
