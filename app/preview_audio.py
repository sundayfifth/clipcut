"""ตัดเสียงมาให้ฟังก่อนตัดสินใจ

2 แบบ ตอบคนละคำถาม:
- shot  : "ซีนนี้พูดว่าอะไร" — เสียงของซีนนั้นตรงๆ
- join  : "ถ้าตัดซีนนี้ออก มันจะสะดุดมั้ย" — ท้ายซีนก่อนหน้าต่อกับหัวซีนถัดไป
          ใส่เฟดสั้นแบบเดียวกับตอน render จริง เสียงที่ได้ยินจะได้ตรงกับไฟล์จริง
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from app.analyze import AnalyzeError
from app.render import EDGE_FADE

# ฟังข้างละเท่านี้ก็พอรู้ว่าประโยคขาดมั้ย ยาวกว่านี้เสียเวลา
JOIN_CONTEXT = 1.6


def _extract(source: Path, start: float, duration: float, dest: Path) -> None:
    fade = min(EDGE_FADE, duration / 4)
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-y", "-loglevel", "error",
            "-accurate_seek", "-ss", f"{max(0.0, start):.3f}",
            "-i", str(source), "-t", f"{duration:.3f}",
            "-vn", "-af",
            f"afade=t=in:st=0:d={fade:.4f},"
            f"afade=t=out:st={max(0.0, duration - fade):.4f}:d={fade:.4f}",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "1",
            "-movflags", "+faststart", str(dest),
        ],
        capture_output=True, timeout=120, check=False,
    )


def shot_audio(source: Path, shot_plan: dict, dest: Path) -> Path:
    """เสียงของซีนนั้นตรงๆ"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    duration = shot_plan["end"] - shot_plan["start"]
    _extract(source, shot_plan["start"], duration, dest)
    if not dest.exists():
        raise AnalyzeError("ตัดเสียงไม่สำเร็จ — คลิปนี้อาจไม่มีเสียง")
    return dest


def join_audio(source: Path, plan: dict, shot_index: int, dest: Path) -> Path:
    """เสียงรอยต่อถ้าตัดซีนนี้ออก — ท้ายซีนก่อนหน้า + หัวซีนถัดไป

    สร้างด้วย ffmpeg รอบเดียวโดย encode ใหม่ ไม่ใช้ concat -c copy
    เพราะไฟล์ที่ได้จาก copy เบราว์เซอร์เล่นไม่ได้ (ffprobe อ่านได้ก็จริงแต่ browser เข้มกว่า)
    """
    shots = plan["shots"]
    at = next((i for i, s in enumerate(shots) if s["shot_index"] == shot_index), None)
    if at is None:
        raise AnalyzeError(f"ไม่พบซีนที่ {shot_index + 1}")

    # หาซีนก่อนหน้า/ถัดไปที่ "ถูกเลือกไว้" เพราะนั่นคือสิ่งที่จะมาต่อกันจริง
    before = next((s for s in reversed(shots[:at]) if s.get("included", True)), None)
    after = next((s for s in shots[at + 1:] if s.get("included", True)), None)
    if before is None and after is None:
        raise AnalyzeError("ไม่มีซีนข้างเคียงให้ต่อ")

    pieces: list[tuple[float, float]] = []
    if before is not None:
        span = min(JOIN_CONTEXT, before["end"] - before["start"])
        pieces.append((before["end"] - span, span))
    if after is not None:
        span = min(JOIN_CONTEXT, after["end"] - after["start"])
        pieces.append((after["start"], span))

    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-nostdin", "-y", "-loglevel", "error"]
    for start_at, span in pieces:
        cmd += ["-accurate_seek", "-ss", f"{max(0.0, start_at):.3f}",
                "-t", f"{span:.3f}", "-i", str(source)]

    # เฟดหัวท้ายแต่ละชิ้นเหมือนตอน render จริง เสียงที่ได้ยินจะได้ตรงกับไฟล์จริง
    chains = []
    for i, (_, span) in enumerate(pieces):
        fade = min(EDGE_FADE, span / 4)
        chains.append(
            f"[{i}:a]afade=t=in:st=0:d={fade:.4f},"
            f"afade=t=out:st={max(0.0, span - fade):.4f}:d={fade:.4f},"
            f"aresample=44100[p{i}]"
        )
    labels = "".join(f"[p{i}]" for i in range(len(pieces)))
    filter_complex = ";".join(chains) + f";{labels}concat=n={len(pieces)}:v=0:a=1[out]"

    cmd += ["-filter_complex", filter_complex, "-map", "[out]",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "1",
            "-movflags", "+faststart", str(dest)]

    result = subprocess.run(cmd, capture_output=True, timeout=180, text=True)
    if result.returncode != 0 or not dest.exists():
        raise AnalyzeError(
            f"ต่อเสียงรอยต่อไม่สำเร็จ: {result.stderr.strip()[:200]}"
        )
    return dest
