"""หา shot boundary และดึงภาพตัวอย่างต่อ shot

กติกามาจากงานวิจัย (docs/2026-08-25-research-auto-reframe.md):
AutoFlip หา shot ด้วย histogram บน stream ที่ scale ลงแล้วที่ full frame rate
PySceneDetect ContentDetector ทำงานแบบเดียวกัน จึงใช้แทนได้เลย
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path

from scenedetect import ContentDetector, detect

# ความละเอียดที่ใช้วิเคราะห์ — AutoFlip ใช้ 480px กว้าง งานตรวจ shot ไม่ต้องใช้ภาพเต็ม
ANALYSIS_WIDTH = 480

# shot ที่สั้นกว่านี้มักเป็น false positive จากแสงเปลี่ยน/แฟลช ไม่ใช่การตัดจริง
MIN_SHOT_SECONDS = 0.4


class AnalyzeError(Exception):
    """ข้อความที่ปลอดภัยพอจะโชว์ให้ผู้ใช้อ่านได้ตรงๆ"""


@dataclass
class Shot:
    index: int
    start: float
    end: float
    thumbnail: str | None = None

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def midpoint(self) -> float:
        return self.start + self.duration / 2


@dataclass
class VideoInfo:
    width: int
    height: int
    duration: float
    fps: float

    @property
    def aspect(self) -> str:
        return f"{self.width}x{self.height}"


def probe(video: Path) -> VideoInfo:
    """อ่าน metadata ด้วย ffprobe"""
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height,r_frame_rate",
                "-show_entries", "format=duration",
                "-of", "json", str(video),
            ],
            capture_output=True, text=True, timeout=60, check=True,
        ).stdout
    except subprocess.CalledProcessError as err:
        raise AnalyzeError(
            f"อ่านไฟล์ '{video.name}' ไม่ได้ — ไฟล์อาจเสียหรือเป็นฟอร์แมตที่ไม่รองรับ"
        ) from err
    except subprocess.TimeoutExpired as err:
        raise AnalyzeError(f"อ่านไฟล์ '{video.name}' นานเกินไป") from err

    data = json.loads(out)
    if not data.get("streams"):
        raise AnalyzeError(f"ไฟล์ '{video.name}' ไม่มี video track")

    stream = data["streams"][0]
    num, _, den = stream.get("r_frame_rate", "0/1").partition("/")
    fps = float(num) / float(den) if float(den or 0) else 0.0

    return VideoInfo(
        width=int(stream["width"]),
        height=int(stream["height"]),
        duration=float(data.get("format", {}).get("duration", 0.0)),
        fps=round(fps, 3),
    )


def detect_shots(video: Path) -> list[Shot]:
    """แบ่งคลิปเป็น shot

    คลิปที่ไม่มีรอยตัดเลยจะได้ 1 shot ครอบทั้งคลิป ไม่ใช่ list ว่าง
    """
    try:
        scenes = detect(str(video), ContentDetector())
    except Exception as err:  # scenedetect โยน exception ได้หลายชนิด
        raise AnalyzeError(
            f"วิเคราะห์ '{video.name}' ไม่สำเร็จ — ไฟล์อาจเสียหรือเป็น codec ที่ไม่รองรับ"
        ) from err

    if not scenes:
        info = probe(video)
        return [Shot(index=0, start=0.0, end=info.duration)]

    shots: list[Shot] = []
    for start, end in scenes:
        span = (round(start.seconds, 3), round(end.seconds, 3))
        # รวม shot ที่สั้นเกินเข้ากับ shot ก่อนหน้า แทนที่จะทิ้ง
        if shots and span[1] - span[0] < MIN_SHOT_SECONDS:
            shots[-1].end = span[1]
            continue
        shots.append(Shot(index=len(shots), start=span[0], end=span[1]))
    return shots


def extract_thumbnail(video: Path, at_second: float, dest: Path) -> None:
    """ดึง 1 เฟรมที่วินาทีที่ระบุ ย่อเหลือ ANALYSIS_WIDTH"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "ffmpeg", "-nostdin", "-y", "-loglevel", "error",
            "-ss", f"{at_second:.3f}", "-i", str(video),
            "-frames:v", "1",
            "-vf", f"scale={ANALYSIS_WIDTH}:-2",
            str(dest),
        ],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0 or not dest.exists():
        raise AnalyzeError(
            f"ดึงภาพตัวอย่างที่วินาที {at_second:.1f} ไม่สำเร็จ: {result.stderr.strip()[:200]}"
        )


def shot_to_dict(shot: Shot) -> dict:
    return {**asdict(shot), "duration": round(shot.duration, 3)}
