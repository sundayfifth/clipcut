"""render แต่ละ shot ตาม edit plan แล้วต่อกันเป็นไฟล์ 9:16 ไฟล์เดียว

pad ใช้พื้นหลังเบลอจากภาพเดิม ตามที่ AutoFlip ทำ
(AutoFlip เติมสีทึบแทนถ้าตรวจเจอว่าพื้นหลังเป็นสีเรียบ — ยังไม่ได้ทำ)

render ทีละ shot แล้วค่อย concat แทนที่จะยัด filter_complex เส้นเดียว
เพราะรายงาน progress ต่อ shot ได้ และ shot ไหนพังก็รู้ว่าพังตรงไหน
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from app.analyze import AnalyzeError

# ตั้งให้ตรงกันทุก segment ไม่งั้น concat แล้วภาพ/เสียงเพี้ยน
VIDEO_ARGS = ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p"]
AUDIO_ARGS = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]

BLUR_SIGMA = 25


def _crop_filter(crop: dict, tw: int, th: int) -> str:
    return (
        f"crop={crop['w']}:{crop['h']}:{crop['x']}:{crop['y']},"
        f"scale={tw}:{th}:flags=lanczos,setsar=1"
    )


def _pad_filter(tw: int, th: int) -> str:
    """ย่อภาพเต็มให้พอดีความกว้าง แล้วเติมบน-ล่างด้วยภาพเดิมที่ขยายจนเต็มแล้วเบลอ"""
    return (
        f"split=2[bg][fg];"
        f"[bg]scale={tw}:{th}:force_original_aspect_ratio=increase,"
        f"crop={tw}:{th},gblur=sigma={BLUR_SIGMA}[bgb];"
        f"[fg]scale={tw}:-2:flags=lanczos[fgs];"
        f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1"
    )


def render_shot(source: Path, shot_plan: dict, target: dict, dest: Path) -> None:
    tw, th = target["width"], target["height"]
    if shot_plan["mode"] == "crop":
        vf = _crop_filter(shot_plan["crop"], tw, th)
    else:
        vf = _pad_filter(tw, th)

    dest.parent.mkdir(parents=True, exist_ok=True)
    duration = shot_plan["end"] - shot_plan["start"]
    cmd = [
        "ffmpeg", "-nostdin", "-y", "-loglevel", "error",
        "-accurate_seek", "-ss", f"{shot_plan['start']:.3f}",
        "-i", str(source),
        "-t", f"{duration:.3f}",
        "-filter_complex", f"[0:v]{vf}[v]",
        "-map", "[v]", "-map", "0:a?",
        *VIDEO_ARGS, *AUDIO_ARGS,
        str(dest),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if result.returncode != 0 or not dest.exists():
        raise AnalyzeError(
            f"render ซีน {shot_plan['shot_index'] + 1} ไม่สำเร็จ: "
            f"{result.stderr.strip()[:300]}"
        )


def concat(segments: list[Path], dest: Path) -> None:
    """ต่อ segment ด้วย concat demuxer — ไม่ต้อง encode ซ้ำเพราะ setting ตรงกันหมด"""
    if not segments:
        raise AnalyzeError("ไม่มีซีนให้ต่อ")

    listing = dest.parent / "segments.txt"
    listing.write_text(
        "".join(f"file '{p.resolve().as_posix()}'\n" for p in segments),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            "ffmpeg", "-nostdin", "-y", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(listing),
            "-c", "copy", str(dest),
        ],
        capture_output=True, text=True, timeout=1800,
    )
    if result.returncode != 0 or not dest.exists():
        raise AnalyzeError(f"ต่อไฟล์ไม่สำเร็จ: {result.stderr.strip()[:300]}")


def render_plan(source: Path, plan: dict, work_dir: Path, dest: Path, on_progress=None) -> Path:
    segments_dir = work_dir / "segments"
    segments: list[Path] = []
    shots = plan["shots"]

    for i, shot_plan in enumerate(shots, start=1):
        seg = segments_dir / f"seg-{shot_plan['shot_index']:04d}.mp4"
        render_shot(source, shot_plan, plan["target_size"], seg)
        segments.append(seg)
        if on_progress:
            on_progress(i / len(shots))

    dest.parent.mkdir(parents=True, exist_ok=True)
    concat(segments, dest)
    return dest
