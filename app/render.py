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
from app.bands import Bands, band_filter

# ตั้งให้ตรงกันทุก segment ไม่งั้น concat แล้วภาพ/เสียงเพี้ยน
VIDEO_ARGS = ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p"]
AUDIO_ARGS = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"]

BLUR_SIGMA = 25


class RenderCancelled(Exception):
    """คนกดยกเลิกระหว่าง render"""


def _path_expression(shot_plan: dict) -> str:
    """ตำแหน่ง x ของกรอบ — คงที่ หรือขยับตาม polynomial ที่ fit ไว้ทั้ง shot

    ffmpeg ประเมิน expression ใหม่ทุกเฟรม ใช้ t เป็นวินาทีนับจากต้น segment
    clip() กันไม่ให้กรอบหลุดออกนอกภาพตอนเส้นแกว่งช่วงปลาย

    ถ้าคนเลื่อนกรอบเอง จะบวก offset เข้าไปทั้งเส้น — กรอบยังตามคนอยู่ แค่เยื้องไปตามที่สั่ง
    """
    crop, path = shot_plan["crop"], shot_plan.get("path")
    if not path or path.get("kind") != "poly":
        return str(crop["x"])

    base = shot_plan.get("crop_base") or {}
    adjust = shot_plan.get("adjust") or {}
    offset = float(adjust.get("dx", 0.0)) * float(base.get("w", crop["w"]))

    terms = []
    for power, c in enumerate(path["coeffs"]):
        value = c + offset if power == 0 else c
        terms.append(f"{value:.6f}" if power == 0
                     else f"{value:.6f}*" + "*".join(["t"] * power))
    centre = "+".join(terms).replace("+-", "-")
    return f"clip(({centre})-{crop['w'] / 2:.1f},0,in_w-out_w)"


def _crop_filter(shot_plan: dict, tw: int, th: int) -> str:
    crop = shot_plan["crop"]
    return (
        f"crop={crop['w']}:{crop['h']}:'{_path_expression(shot_plan)}':{crop['y']},"
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


def render_shot(
    source: Path, shot_plan: dict, target: dict, dest: Path,
    bands: Bands | None = None, source_size: dict | None = None,
) -> None:
    tw, th = target["width"], target["height"]

    stages = []
    # โหมด trim ตัดแถบทิ้งก่อน ทำให้กรอบที่ plan คำนวณไว้อ้างอิงภาพหลังตัดแล้ว
    if bands and bands.active and source_size:
        pre = band_filter(bands, source_size["width"], source_size["height"])
        if pre:
            stages.append(pre)
            if bands.mode == "trim":
                # crop ซ้อน crop — y ถูกหักไปกับ stage แรกแล้ว
                shot_plan = {**shot_plan, "crop": {**shot_plan["crop"], "y": 0}} \
                    if shot_plan.get("crop") else shot_plan

    if shot_plan["mode"] == "crop":
        stages.append(_crop_filter(shot_plan, tw, th))
    else:
        stages.append(_pad_filter(tw, th))
    vf = ",".join(stages) if len(stages) == 1 else _join_stages(stages)

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


def _join_stages(stages: list[str]) -> str:
    """ต่อ filter หลาย stage — stage ที่มี label ในตัว (blur band) ต่อด้วย ; ไม่ใช่ ,"""
    out = ""
    for i, stage in enumerate(stages):
        if i == 0:
            out = stage
        elif ";" in out or ";" in stage:
            out = f"{out}[s{i}];[s{i}]{stage}"
        else:
            out = f"{out},{stage}"
    return out


def render_plan(source: Path, plan: dict, work_dir: Path, dest: Path,
                on_progress=None, should_cancel=None) -> Path:
    segments_dir = work_dir / "segments"
    segments: list[Path] = []
    shots = [s for s in plan["shots"] if s.get("included", True)]
    if not shots:
        raise AnalyzeError("ยังไม่ได้เลือกซีนไหนเลย — เลือกอย่างน้อย 1 ซีนก่อน")

    bands = Bands.from_dict(plan.get("bands"))
    for i, shot_plan in enumerate(shots, start=1):
        # เช็คก่อนเริ่มแต่ละซีน — ยกเลิกกลางคันจะได้ไม่ต้องรอจนจบทั้งคลิป
        if should_cancel and should_cancel():
            raise RenderCancelled()
        seg = segments_dir / f"seg-{shot_plan['shot_index']:04d}.mp4"
        render_shot(
            source, shot_plan, plan["target_size"], seg,
            bands=bands, source_size=plan.get("source_size"),
        )
        segments.append(seg)
        if on_progress:
            on_progress(i / len(shots))

    if should_cancel and should_cancel():
        raise RenderCancelled()

    dest.parent.mkdir(parents=True, exist_ok=True)
    concat(segments, dest)
    return dest
