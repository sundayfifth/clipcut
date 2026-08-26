"""คิวงานวิเคราะห์/render แบบง่าย รันใน thread แยก

เป็น local single-user tool จึงเก็บ state ไว้ใน memory พอ — ไม่ต้องมี DB
งานกินเวลาหลายนาทีต่อคลิป UI จึงต้อง poll ดู progress ได้ (กติกาใน CLAUDE.md)

ไหลเป็น 2 ช่วง: วิเคราะห์อัตโนมัติ -> คนตรวจ/แก้การตัดสิน -> สั่ง render
คั่นด้วยคนตรงกลางเพราะการตัดสิน crop-vs-pad ผิดได้ เช่นสกรีนช็อตที่มีรูปคนอยู่ข้างใน
detector จะเห็นเป็นคนแล้ว crop จนข้อความหาย — ต้องให้คนพลิกกลับได้
"""

from __future__ import annotations

import json
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from app.analyze import (
    DEFAULT_SENSITIVITY,
    AnalyzeError,
    Shot,
    detect_shots,
    extract_thumbnail,
    probe,
    shot_to_dict,
)
from app.detect import detect_people
from app.plan import build_plan
from app.render import render_plan


@dataclass
class Job:
    id: str
    source: Path
    sensitivity: str = DEFAULT_SENSITIVITY
    status: str = "pending"  # pending | running | ready | rendering | done | error
    step: str = "รอเริ่ม"
    progress: float = 0.0
    error: str | None = None
    info: dict | None = None
    shots: list[Shot] = field(default_factory=list)
    plan: dict | None = None
    output: str | None = None

    def as_dict(self) -> dict:
        by_index = {s["shot_index"]: s for s in (self.plan or {}).get("shots", [])}
        return {
            "id": self.id,
            "name": self.source.name,
            "sensitivity": self.sensitivity,
            "status": self.status,
            "step": self.step,
            "progress": round(self.progress, 3),
            "error": self.error,
            "info": self.info,
            "output": self.output,
            "summary": (self.plan or {}).get("summary"),
            "shots": [
                {**shot_to_dict(s), "plan": by_index.get(s.index)} for s in self.shots
            ],
        }


class JobStore:
    def __init__(self, work_dir: Path, output_dir: Path) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self.work_dir = work_dir
        self.output_dir = output_dir

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        with self._lock:
            return list(self._jobs.values())

    def submit(self, source: Path, sensitivity: str = DEFAULT_SENSITIVITY) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], source=source, sensitivity=sensitivity)
        with self._lock:
            self._jobs[job.id] = job
        threading.Thread(target=self._analyze, args=(job,), daemon=True).start()
        return job

    def set_mode(self, job: Job, shot_index: int, mode: str) -> None:
        """ให้คนพลิกการตัดสินของเครื่องได้ — pad ที่ควรเป็น crop หรือกลับกัน"""
        if job.status not in ("ready", "done"):
            raise AnalyzeError("ต้องรอวิเคราะห์เสร็จก่อนถึงจะแก้ได้")
        if mode not in ("crop", "pad"):
            raise AnalyzeError(f"โหมด '{mode}' ไม่ถูกต้อง (crop หรือ pad เท่านั้น)")

        for shot_plan in job.plan["shots"]:
            if shot_plan["shot_index"] == shot_index:
                if mode == "crop" and not shot_plan.get("crop"):
                    # เครื่องไม่ได้คำนวณกรอบไว้ให้ ใช้กรอบกลางเฟรมเป็นค่าตั้งต้น
                    shot_plan["crop"] = _center_crop(job.plan)
                shot_plan["mode"] = mode
                shot_plan["reason"] = "คนเลือกเอง"
                break
        else:
            raise AnalyzeError(f"ไม่พบซีนที่ {shot_index + 1}")

        shots = job.plan["shots"]
        job.plan["summary"] = {
            "total": len(shots),
            "crop": sum(1 for s in shots if s["mode"] == "crop"),
            "pad": sum(1 for s in shots if s["mode"] == "pad"),
        }

    def start_render(self, job: Job) -> None:
        if job.status not in ("ready", "done"):
            raise AnalyzeError("ต้องรอวิเคราะห์เสร็จก่อนถึงจะ render ได้")
        threading.Thread(target=self._render, args=(job,), daemon=True).start()

    # ------------------------------------------------------------------ งานเบื้องหลัง

    def _analyze(self, job: Job) -> None:
        try:
            job.status = "running"

            job.step = "อ่านข้อมูลไฟล์"
            info = probe(job.source)
            job.info = {
                "width": info.width,
                "height": info.height,
                "duration": round(info.duration, 2),
                "fps": info.fps,
                "aspect": info.aspect,
            }
            job.progress = 0.03

            job.step = "หารอยตัดระหว่างซีน"
            shots = detect_shots(job.source, job.sensitivity)
            job.shots = shots
            job.progress = 0.15

            job.step = "ดึงภาพตัวอย่าง"
            thumbs = self.work_dir / job.id / "thumbs"
            for i, shot in enumerate(shots, start=1):
                dest = thumbs / f"shot-{shot.index:04d}.jpg"
                try:
                    extract_thumbnail(job.source, shot.midpoint, dest)
                    shot.thumbnail = f"/api/jobs/{job.id}/thumbs/{dest.name}"
                except AnalyzeError:
                    shot.thumbnail = None  # ภาพเดียวพลาดไม่ควรล้มทั้งงาน
                job.progress = 0.15 + 0.20 * (i / len(shots))

            job.step = "ตรวจจับตัวคนในแต่ละซีน"
            detections = detect_people(
                job.source, shots,
                on_progress=lambda p: setattr(job, "progress", 0.35 + 0.55 * p),
            )
            job.progress = 0.92

            job.step = "ตัดสินว่าซีนไหน crop ได้ ซีนไหนต้องย่อ"
            job.plan = build_plan(job.source, info, shots, detections)
            _write_plan(self.work_dir / job.id / "edit-plan.json", job.plan)

            s = job.plan["summary"]
            job.step = f"พร้อม render — crop {s['crop']} ซีน · ย่อ+เติมพื้นหลัง {s['pad']} ซีน"
            job.status = "ready"
            job.progress = 1.0

        except Exception as err:
            self._fail(job, err)

    def _render(self, job: Job) -> None:
        try:
            job.status = "rendering"
            job.progress = 0.0
            job.step = "กำลัง render"

            out_dir = self.output_dir / _safe_stem(job.source)
            dest = out_dir / f"{_safe_stem(job.source)}_9x16.mp4"
            render_plan(
                job.source, job.plan, self.work_dir / job.id, dest,
                on_progress=lambda p: (
                    setattr(job, "progress", p),
                    setattr(job, "step", f"กำลัง render ซีนที่ {int(p * len(job.plan['shots'])) or 1}/{len(job.plan['shots'])}"),
                ),
            )
            _write_plan(out_dir / "edit-plan.json", job.plan)

            job.output = str(dest)
            job.step = f"เสร็จแล้ว — {dest.name}"
            job.status = "done"
            job.progress = 1.0

        except Exception as err:
            self._fail(job, err)

    def _fail(self, job: Job, err: Exception) -> None:
        if isinstance(err, AnalyzeError):
            job.error = str(err)
        else:
            traceback.print_exc()
            job.error = f"เกิดข้อผิดพลาดที่ไม่คาดคิด: {type(err).__name__}"
        job.status = "error"
        job.step = "หยุดเพราะมีปัญหา"


def _center_crop(plan: dict) -> dict:
    src, tgt = plan["source_size"], plan["target_size"]
    ratio = tgt["width"] / tgt["height"]
    w = min(src["width"], src["height"] * ratio)
    return {
        "x": int(round((src["width"] - w) / 2)),
        "y": 0,
        "w": int(round(w)),
        "h": src["height"],
    }


def _safe_stem(source: Path) -> str:
    """ชื่อโฟลเดอร์ output — ตัดอักขระที่ทำให้ path มีปัญหาออก"""
    stem = "".join(c for c in source.stem if c not in '/\\:*?"<>|').strip()
    return stem[:80] or "output"


def _write_plan(dest: Path, plan: dict) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
