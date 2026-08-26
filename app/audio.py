"""วัดระดับเสียงต่อซีน เพื่อเตือนว่าตัดซีนนี้ออกแล้วประโยคจะขาด

ทดสอบกับคลิปจริงแล้วพบว่าเสียงบรรยายพูดคลุมทับ b-roll และสกรีนช็อตด้วย
ซีนที่ "เงียบจริง" จึงมีน้อย และค่า RMS แยกออกจากกันชัด (-19 dB vs -38/-50 dB)
ระดับเสียงจึงเพียงพอสำหรับการ "เตือน" ไม่ต้องลาก VAD เข้ามาเพิ่ม

decode เสียงทั้งคลิปรอบเดียวเป็น PCM 8 kHz mono แล้วคำนวณในหน่วยความจำ
เร็วกว่าเรียก ffmpeg ทีละซีน 25 รอบมาก
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from app.analyze import AnalyzeError, Shot

SAMPLE_RATE = 8000

# ซีนที่เบากว่าค่าเฉลี่ยทั้งคลิปเกินเท่านี้ ถือว่าไม่มีเสียงพูดสำคัญ
QUIET_MARGIN_DB = 10.0

# เบากว่านี้ถือว่าเงียบสนิท ไม่ว่าคลิปโดยรวมจะเบาแค่ไหน
FLOOR_DB = -45.0


def _rms_db(samples: np.ndarray) -> float:
    """คืนค่าเป็น float ของ Python ไม่ใช่ np.float64 — ไม่งั้น json.dumps เขียนไม่ได้
    แล้วงานจะเซฟลงดิสก์ไม่ได้ (เคยพลาดมาแล้ว test จับได้)"""
    if samples.size == 0:
        return FLOOR_DB - 20
    rms = float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))
    return float(20 * np.log10(rms)) if rms > 1e-9 else FLOOR_DB - 20


def measure_shots(video: Path, shots: list[Shot]) -> dict[int, dict]:
    """คืน {shot_index: {"db": ระดับเสียง, "has_speech": bool}}"""
    result = subprocess.run(
        [
            "ffmpeg", "-nostdin", "-v", "error", "-i", str(video),
            "-map", "0:a:0?", "-f", "f32le", "-ac", "1", "-ar", str(SAMPLE_RATE), "-",
        ],
        capture_output=True, timeout=600,
    )
    if result.returncode != 0 or not result.stdout:
        # คลิปไม่มีเสียง — ไม่ใช่ error เตือนอะไรไม่ได้ก็ไม่ต้องเตือน
        return {s.index: {"db": None, "has_speech": False} for s in shots}

    audio = np.frombuffer(result.stdout, dtype=np.float32)
    overall = _rms_db(audio)
    threshold = max(FLOOR_DB, overall - QUIET_MARGIN_DB)

    out: dict[int, dict] = {}
    for shot in shots:
        lo = int(shot.start * SAMPLE_RATE)
        hi = min(len(audio), int(shot.end * SAMPLE_RATE))
        db = _rms_db(audio[lo:hi]) if hi > lo else FLOOR_DB - 20
        out[shot.index] = {
            "db": round(float(db), 1),
            "has_speech": bool(db >= threshold),
        }
    return out
