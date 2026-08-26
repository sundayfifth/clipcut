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

# ระดับความละเอียดของการแบ่งซีน: threshold ยิ่งต่ำยิ่งไวต่อการเปลี่ยนฉาก แบ่งถี่ขึ้น
# min_seconds กันไม่ให้ได้ซีนสั้นจู๋จากแสงกระพริบ/แฟลช ซึ่งไม่ใช่การตัดจริง
SENSITIVITY = {
    "coarse": (32.0, 1.0),
    "normal": (22.0, 0.6),
    "fine": (12.0, 0.4),
    "finest": (6.0, 0.3),
}
DEFAULT_SENSITIVITY = "fine"


class AnalyzeError(Exception):
    """ข้อความที่ปลอดภัยพอจะโชว์ให้ผู้ใช้อ่านได้ตรงๆ"""


# จำนวนเฟรมในแถบ sprite ต่อ 1 ซีน — ตัดสินการจัดเฟรมจากเฟรมเดียวคือการเดา
# ซีนสั้นไม่ต้องเยอะ ซีนยาวเอาเยอะหน่อยจะได้ scrub เห็นการเคลื่อนไหว
def frame_count(duration: float) -> int:
    return max(3, min(12, int(duration / 1.2) + 3))


@dataclass
class Shot:
    index: int
    start: float
    end: float
    thumbnail: str | None = None
    frames: int = 1

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


def detect_shots(video: Path, sensitivity: str = DEFAULT_SENSITIVITY) -> list[Shot]:
    """แบ่งคลิปเป็น shot ตามการเปลี่ยนฉาก

    sensitivity เลือกได้จาก SENSITIVITY — ยิ่งละเอียดยิ่งแบ่งถี่
    คลิปที่ไม่มีรอยตัดเลยจะได้ 1 shot ครอบทั้งคลิป ไม่ใช่ list ว่าง
    """
    if sensitivity not in SENSITIVITY:
        raise AnalyzeError(
            f"ระดับความละเอียด '{sensitivity}' ไม่ถูกต้อง "
            f"(เลือกได้: {', '.join(SENSITIVITY)})"
        )
    threshold, min_seconds = SENSITIVITY[sensitivity]

    info = probe(video)
    # แปลงเป็นจำนวนเฟรมให้ detector กรองตั้งแต่ต้นทาง ไม่ต้องมารวมทีหลัง
    min_frames = max(2, round(min_seconds * info.fps)) if info.fps else 2

    try:
        scenes = detect(
            str(video),
            ContentDetector(threshold=threshold, min_scene_len=min_frames),
        )
    except Exception as err:  # scenedetect โยน exception ได้หลายชนิด
        raise AnalyzeError(
            f"วิเคราะห์ '{video.name}' ไม่สำเร็จ — ไฟล์อาจเสียหรือเป็น codec ที่ไม่รองรับ"
        ) from err

    if not scenes:
        return [Shot(index=0, start=0.0, end=info.duration)]

    shots: list[Shot] = []
    for start, end in scenes:
        span = (round(start.seconds, 3), round(end.seconds, 3))
        # detector กรอง min_scene_len ให้แล้ว เหลือกันเศษท้ายคลิปที่สั้นผิดปกติ
        if shots and span[1] - span[0] < min_seconds / 2:
            shots[-1].end = span[1]
            continue
        shots.append(Shot(index=len(shots), start=span[0], end=span[1]))
    return shots


def extract_strip(video: Path, shot: Shot, dest: Path) -> int:
    """ดึงหลายเฟรมจากซีนมาต่อเป็นแถบเดียว (sprite) ด้วย ffmpeg รอบเดียว

    ทำเป็นแถบเดียวเพราะเรียก ffmpeg ทีละเฟรมกับ 40 กว่าซีนช้าเกินไป
    และหน้าเว็บ scrub ได้ลื่นกว่าเพราะไม่ต้องโหลดทีละภาพ
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    n = frame_count(shot.duration)
    # เว้นขอบหัวท้ายซีนเล็กน้อย กันเฟรมที่คาบเกี่ยวรอยตัด
    margin = min(0.12, shot.duration * 0.08)
    span = max(0.04, shot.duration - margin * 2)
    step = span / n

    result = subprocess.run(
        [
            "ffmpeg", "-nostdin", "-y", "-loglevel", "error",
            "-ss", f"{shot.start + margin:.3f}", "-t", f"{span:.3f}",
            "-i", str(video),
            "-vf", f"fps={1 / step:.6f},scale={ANALYSIS_WIDTH}:-2,tile={n}x1",
            "-frames:v", "1", "-q:v", "4",
            str(dest),
        ],
        capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0 or not dest.exists():
        raise AnalyzeError(
            f"ดึงภาพตัวอย่างซีน {shot.index + 1} ไม่สำเร็จ: {result.stderr.strip()[:200]}"
        )
    return n


def shot_to_dict(shot: Shot) -> dict:
    return {**asdict(shot), "duration": round(shot.duration, 3)}


def shot_from_dict(data: dict) -> Shot:
    return Shot(
        index=data["index"], start=data["start"], end=data["end"],
        thumbnail=data.get("thumbnail"), frames=data.get("frames", 1),
    )
