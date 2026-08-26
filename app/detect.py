"""ตรวจจับตัวคนในแต่ละ shot เพื่อใช้ตัดสินว่าจะ crop ตรงไหน

ใช้ MediaPipe ObjectDetector (Apache 2.0) ไม่ใช่ FaceDetector เพราะฟุตเทจของเรา
คนมักยืนห่างกล้อง — ทดสอบแล้วตรวจหน้าไม่เจอ แต่ตรวจ person เจอ

sample ที่ ~5 fps ตามที่ AutoFlip ทำ (ดู docs/2026-08-25-research-auto-reframe.md)
ไม่ต้องตรวจทุกเฟรม เปลืองเวลาโดยไม่ได้อะไรเพิ่ม
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python import vision

from app.analyze import AnalyzeError, Shot

MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "efficientdet_lite0.tflite"

SAMPLE_FPS = 5.0
MIN_SCORE = 0.35
PERSON = "person"


@dataclass
class Box:
    """กรอบในหน่วย pixel ของภาพต้นฉบับ"""

    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0

    @property
    def area(self) -> int:
        return max(0, self.width) * max(0, self.height)

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2

    def clamped(self, width: int, height: int) -> "Box":
        """detector คืนกรอบที่ล้นออกนอกเฟรมได้ ต้องหนีบก่อนใช้คำนวณ"""
        return Box(
            max(0, min(self.x0, width)), max(0, min(self.y0, height)),
            max(0, min(self.x1, width)), max(0, min(self.y1, height)),
        )

    def as_dict(self) -> dict:
        return {"x0": self.x0, "y0": self.y0, "x1": self.x1, "y1": self.y1}


@dataclass
class ShotDetections:
    shot_index: int
    frames_sampled: int
    frames_with_person: int
    # (เวลานับจากต้น shot, กรอบคนทุกคนเรียงจากใหญ่ไปเล็ก) เก็บเฉพาะเฟรมที่เจอคน
    # เก็บแยกคน ไม่ union เพราะการตัดสิน crop ต้องแยกให้ออกว่า
    # "คนเดียวตัวใหญ่" (crop ได้) กับ "สองคนอยู่คนละฝั่ง" (crop ไม่ได้)
    # เก็บเวลาไว้ด้วยเพื่อ fit เส้นทางกล้องให้กรอบขยับตามคนได้
    per_frame: list[tuple[float, list[Box]]]

    @property
    def boxes(self) -> list[list[Box]]:
        return [boxes for _, boxes in self.per_frame]

    @property
    def hit_rate(self) -> float:
        return self.frames_with_person / self.frames_sampled if self.frames_sampled else 0.0


def _make_detector() -> vision.ObjectDetector:
    if not MODEL_PATH.exists():
        raise AnalyzeError(
            f"ไม่พบไฟล์โมเดลที่ {MODEL_PATH.name} — ดูวิธีโหลดใน README"
        )
    return vision.ObjectDetector.create_from_options(
        vision.ObjectDetectorOptions(
            base_options=BaseOptions(model_asset_path=str(MODEL_PATH)),
            score_threshold=MIN_SCORE,
        )
    )


def detect_people(video: Path, shots: list[Shot], on_progress=None) -> list[ShotDetections]:
    """เดินไล่คลิปรอบเดียว เก็บกรอบคนของทุก shot

    อ่านไฟล์รอบเดียวแล้วแจกเข้า shot ตาม timestamp — เร็วกว่าเปิดไฟล์ใหม่ทีละ shot มาก
    """
    detector = _make_detector()
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise AnalyzeError(f"เปิดไฟล์ '{video.name}' ไม่ได้")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, round(fps / SAMPLE_FPS))

    results = [
        ShotDetections(shot_index=s.index, frames_sampled=0, frames_with_person=0, per_frame=[])
        for s in shots
    ]

    try:
        frame_no = 0
        shot_cursor = 0
        while True:
            if not cap.grab():
                break
            if frame_no % step == 0:
                seconds = frame_no / fps
                # shot เรียงตามเวลาอยู่แล้ว เลื่อน cursor ไปข้างหน้าอย่างเดียว
                while shot_cursor < len(shots) - 1 and seconds >= shots[shot_cursor].end:
                    shot_cursor += 1
                    if on_progress:
                        on_progress(shot_cursor / len(shots))

                ok, frame = cap.retrieve()
                if ok:
                    bucket = results[shot_cursor]
                    bucket.frames_sampled += 1
                    boxes = _detect_frame(detector, frame)
                    if boxes:
                        bucket.frames_with_person += 1
                        offset = max(0.0, seconds - shots[shot_cursor].start)
                        bucket.per_frame.append((offset, boxes))
            frame_no += 1
    finally:
        cap.release()
        detector.close()

    return results


def _detect_frame(detector: vision.ObjectDetector, frame) -> list[Box]:
    """คืนกรอบคนทุกคนในเฟรม เรียงจากใหญ่ไปเล็ก (ตัวใหญ่สุด = subject หลัก)"""
    height, width = frame.shape[:2]
    image = mp.Image(
        image_format=mp.ImageFormat.SRGB,
        data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
    )
    boxes = [
        Box(b.origin_x, b.origin_y, b.origin_x + b.width, b.origin_y + b.height)
        .clamped(width, height)
        for b in (
            d.bounding_box
            for d in detector.detect(image).detections
            if d.categories and d.categories[0].category_name == PERSON
        )
    ]
    return sorted((b for b in boxes if b.area > 0), key=lambda b: b.area, reverse=True)


def detections_to_dict(dets: list[ShotDetections]) -> list[dict]:
    """เก็บลงดิสก์เพื่อให้เปิดงานกลับมาทำต่อได้โดยไม่ต้องตรวจจับใหม่ (ช้าเป็นนาที)"""
    return [
        {
            "shot_index": d.shot_index,
            "frames_sampled": d.frames_sampled,
            "frames_with_person": d.frames_with_person,
            "per_frame": [
                [round(t, 3), [[b.x0, b.y0, b.x1, b.y1] for b in boxes]]
                for t, boxes in d.per_frame
            ],
        }
        for d in dets
    ]


def detections_from_dict(data: list[dict]) -> list[ShotDetections]:
    return [
        ShotDetections(
            shot_index=d["shot_index"],
            frames_sampled=d["frames_sampled"],
            frames_with_person=d["frames_with_person"],
            per_frame=[(t, [Box(*b) for b in boxes]) for t, boxes in d["per_frame"]],
        )
        for d in data
    ]
