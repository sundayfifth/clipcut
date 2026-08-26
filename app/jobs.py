"""คิวงานวิเคราะห์/render แบบง่าย รันใน thread แยก

เป็น local single-user tool จึงเก็บ state ไว้ใน memory พอ — ไม่ต้องมี DB
งานกินเวลาหลายนาทีต่อคลิป UI จึงต้อง poll ดู progress ได้ (กติกาใน CLAUDE.md)

ไหลเป็น 2 ช่วง: วิเคราะห์อัตโนมัติ -> คนตรวจ/แก้การตัดสิน -> สั่ง render
คั่นด้วยคนตรงกลางเพราะการตัดสิน crop-vs-pad ผิดได้ เช่นสกรีนช็อตที่มีรูปคนอยู่ข้างใน
detector จะเห็นเป็นคนแล้ว crop จนข้อความหาย — ต้องให้คนพลิกกลับได้
"""

from __future__ import annotations

import copy
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
    extract_strip,
    probe,
    shot_from_dict,
    shot_to_dict,
)
from app.audio import measure_shots
from app.bands import Bands
from app.detect import (
    ShotDetections,
    detect_people,
    detections_from_dict,
    detections_to_dict,
)
from app.ingest import download_youtube, is_youtube_url
from app.plan import build_plan, clamp_adjust, derive_crop, summarise
from app.render import RenderCancelled, render_plan
from app.report import build_checklist
from app.textdet import TextBox, detect_shots_text, suggest_bands


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
    checklist: str | None = None
    source_url: str | None = None
    # วินาทีที่น่าจะเห็นซับชัดสุด ใช้เป็นเฟรมตั้งต้นของ preview แถบซับ
    subtitle_hint: float = 0.0
    # เก็บผลตรวจจับไว้ เพื่อคำนวณแผนใหม่ตอนคนขยับแถบซับได้ทันทีโดยไม่ต้องตรวจซ้ำ
    detections: list[ShotDetections] = field(default_factory=list)
    audio: dict = field(default_factory=dict)
    text: dict = field(default_factory=dict)
    suggested_bands: dict | None = None
    # ประวัติ plan สำหรับ undo — งานตรวจ 40 กว่าซีนพลาดทีนึงแล้วย้อนไม่ได้คือฝันร้าย
    history: list[dict] = field(default_factory=list)
    cancel: bool = False

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
            "checklist": self.checklist,
            "can_undo": bool(self.history),
            "bands": (self.plan or {}).get("bands"),
            "subtitle_hint": self.subtitle_hint,
            "suggested_bands": self.suggested_bands,
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

    MAX_HISTORY = 60

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _snapshot(self, job: Job) -> None:
        """เก็บ plan ก่อนแก้ เพื่อให้ undo ได้"""
        if job.plan is None:
            return
        job.history.append(copy.deepcopy(job.plan))
        del job.history[:-self.MAX_HISTORY]

    def undo(self, job: Job) -> None:
        if not job.history:
            raise AnalyzeError("ไม่มีอะไรให้ย้อนกลับแล้ว")
        job.plan = job.history.pop()
        self.save(job)

    def list(self) -> list[Job]:
        with self._lock:
            return list(self._jobs.values())

    # ── เก็บ/กู้งาน ────────────────────────────────────────────────

    def save(self, job: Job) -> None:
        """เขียนสถานะลงดิสก์ทุกครั้งที่คนแก้อะไร — ปิด server แล้วเปิดใหม่ต้องทำต่อได้"""
        if job.plan is None:
            return
        dest = self.work_dir / job.id / "job.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "id": job.id,
            "source": str(job.source),
            "sensitivity": job.sensitivity,
            "info": job.info,
            "shots": [shot_to_dict(s) for s in job.shots],
            "plan": job.plan,
            "output": job.output,
            "checklist": job.checklist,
            "detections": detections_to_dict(job.detections),
            "subtitle_hint": job.subtitle_hint,
            "audio": {str(k): v for k, v in job.audio.items()},
            "text": {str(k): [b.as_dict() for b in v] for k, v in job.text.items()},
            "suggested_bands": job.suggested_bands,
        }
        tmp = dest.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(dest)  # เขียนทับแบบ atomic กันไฟล์พังถ้าดับกลางคัน

    def restore(self) -> int:
        """อ่านงานที่เคยทำค้างไว้กลับมาตอน server เริ่ม"""
        found = 0
        if not self.work_dir.is_dir():
            return 0
        for path in sorted(self.work_dir.glob("*/job.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                source = Path(data["source"])
                if not source.is_file():
                    continue  # ไฟล์ต้นฉบับหายไปแล้ว เปิดต่อไม่ได้
                job = Job(
                    id=data["id"], source=source, sensitivity=data["sensitivity"],
                    status="done" if data.get("output") else "ready",
                    step="เปิดงานที่ค้างไว้กลับมา", progress=1.0,
                    info=data["info"], plan=data["plan"],
                    output=data.get("output"), checklist=data.get("checklist"),
                    shots=[shot_from_dict(x) for x in data["shots"]],
                    detections=detections_from_dict(data.get("detections", [])),
                    subtitle_hint=data.get("subtitle_hint", 0.0),
                    audio={int(k): v for k, v in (data.get("audio") or {}).items()},
                    text={
                        int(k): [TextBox(**b) for b in v]
                        for k, v in (data.get("text") or {}).items()
                    },
                    suggested_bands=data.get("suggested_bands"),
                )
                with self._lock:
                    self._jobs[job.id] = job
                found += 1
            except Exception:  # noqa: BLE001 — ไฟล์เสียหนึ่งอันไม่ควรทำให้ server ไม่ขึ้น
                traceback.print_exc()
        return found

    def submit(self, source: Path, sensitivity: str = DEFAULT_SENSITIVITY) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], source=source, sensitivity=sensitivity)
        with self._lock:
            self._jobs[job.id] = job
        threading.Thread(target=self._analyze, args=(job,), daemon=True).start()
        return job

    def submit_url(self, url: str, input_dir: Path, sensitivity: str = DEFAULT_SENSITIVITY) -> Job:
        if not is_youtube_url(url):
            raise AnalyzeError("รองรับเฉพาะลิงก์ YouTube เท่านั้น")
        job = Job(
            id=uuid.uuid4().hex[:12], source=Path(url), sensitivity=sensitivity, source_url=url
        )
        with self._lock:
            self._jobs[job.id] = job
        threading.Thread(
            target=self._download_then_analyze, args=(job, url, input_dir), daemon=True
        ).start()
        return job

    def set_bands(self, job: Job, bands: Bands) -> None:
        """ขยับแถบซับแล้วคำนวณแผนใหม่ทันที — ไม่ต้องตรวจจับคนซ้ำ"""
        if job.status not in ("ready", "done") or not job.detections:
            raise AnalyzeError("ต้องรอวิเคราะห์เสร็จก่อนถึงจะตั้งแถบได้")
        self._snapshot(job)

        # การตัดสินใจของคนต้องรอดจากการคำนวณใหม่ ไม่งั้นขยับแถบทีเดียวงานที่ตรวจไว้หายหมด
        keep = {s["shot_index"]: s for s in job.plan["shots"]}
        info = _info_from(job)
        job.plan = build_plan(
            job.source, info, job.shots, job.detections, bands,
            audio=job.audio, text=job.text,
        )

        for shot_plan in job.plan["shots"]:
            old = keep.get(shot_plan["shot_index"])
            if not old:
                continue
            shot_plan["included"] = old.get("included", True)

            if old.get("manual_mode"):
                shot_plan["mode"] = old["mode"]
                shot_plan["manual_mode"] = True
                shot_plan["reason"] = "คนเลือกเอง"
                if old["mode"] == "crop" and not shot_plan.get("crop_base"):
                    # เครื่องคำนวณให้เป็น pad รอบนี้ จึงไม่มีกรอบฐาน สร้างจากกลางเฟรมแทน
                    shot_plan["crop_base"] = _base_from_center(job.plan, bands, info)

            adjust = old.get("adjust")
            if adjust and shot_plan.get("crop_base"):
                shot_plan["adjust"] = adjust
                shot_plan["crop"] = derive_crop(shot_plan["crop_base"], adjust, info)
            elif shot_plan.get("crop_base"):
                shot_plan["crop"] = derive_crop(shot_plan["crop_base"], None, info)

        job.plan["summary"] = summarise(job.plan["shots"])
        self.save(job)

    def set_crop_adjust(self, job: Job, shot_index: int, adjust: dict) -> None:
        """เลื่อน/ย่อกรอบเอง — เก็บเป็นส่วนต่างจากกรอบที่เครื่องคำนวณ"""
        if job.status not in ("ready", "done"):
            raise AnalyzeError("ต้องรอวิเคราะห์เสร็จก่อนถึงจะปรับกรอบได้")
        self._snapshot(job)

        for shot_plan in job.plan["shots"]:
            if shot_plan["shot_index"] != shot_index:
                continue
            if shot_plan["mode"] != "crop":
                raise AnalyzeError("ปรับกรอบได้เฉพาะซีนที่เป็นโหมดเต็มจอ")
            base = shot_plan.get("crop_base")
            if not base:
                raise AnalyzeError("ซีนนี้ไม่มีกรอบฐานให้ปรับ")
            clean = clamp_adjust(adjust)
            shot_plan["adjust"] = clean
            shot_plan["crop"] = derive_crop(base, clean, _info_from(job))
            self.save(job)
            return
        raise AnalyzeError(f"ไม่พบซีนที่ {shot_index + 1}")

    def set_included(self, job: Job, shot_index: int, included: bool) -> None:
        if job.status not in ("ready", "done"):
            raise AnalyzeError("ต้องรอวิเคราะห์เสร็จก่อนถึงจะเลือกซีนได้")
        self._snapshot(job)
        for shot_plan in job.plan["shots"]:
            if shot_plan["shot_index"] == shot_index:
                shot_plan["included"] = included
                break
        else:
            raise AnalyzeError(f"ไม่พบซีนที่ {shot_index + 1}")
        job.plan["summary"] = summarise(job.plan["shots"])
        self.save(job)

    def set_mode(self, job: Job, shot_index: int, mode: str) -> None:
        """ให้คนพลิกการตัดสินของเครื่องได้ — pad ที่ควรเป็น crop หรือกลับกัน"""
        if job.status not in ("ready", "done"):
            raise AnalyzeError("ต้องรอวิเคราะห์เสร็จก่อนถึงจะแก้ได้")
        if mode not in ("crop", "pad"):
            raise AnalyzeError(f"โหมด '{mode}' ไม่ถูกต้อง (crop หรือ pad เท่านั้น)")
        self._snapshot(job)

        for shot_plan in job.plan["shots"]:
            if shot_plan["shot_index"] == shot_index:
                if mode == "crop" and not shot_plan.get("crop"):
                    # เครื่องไม่ได้คำนวณกรอบไว้ให้ ใช้กรอบกลางเฟรมเป็นค่าตั้งต้น
                    shot_plan["crop"] = _center_crop(job.plan)
                if mode == "crop" and not shot_plan.get("crop_base"):
                    c = shot_plan["crop"]
                    shot_plan["crop_base"] = {
                        "center_x": c["x"] + c["w"] / 2, "w": c["w"],
                        "h": c["h"], "y": c["y"],
                    }
                shot_plan["mode"] = mode
                shot_plan["manual_mode"] = True
                shot_plan["reason"] = "คนเลือกเอง"
                break
        else:
            raise AnalyzeError(f"ไม่พบซีนที่ {shot_index + 1}")

        job.plan["summary"] = summarise(job.plan["shots"])
        self.save(job)

    def start_render(self, job: Job) -> None:
        if job.status not in ("ready", "done"):
            raise AnalyzeError("ต้องรอวิเคราะห์เสร็จก่อนถึงจะ render ได้")
        job.cancel = False
        threading.Thread(target=self._render, args=(job,), daemon=True).start()

    def cancel_render(self, job: Job) -> None:
        if job.status != "rendering":
            raise AnalyzeError("ตอนนี้ไม่ได้กำลัง render อยู่")
        job.cancel = True
        job.step = "กำลังยกเลิก"

    # ------------------------------------------------------------------ งานเบื้องหลัง

    def _download_then_analyze(self, job: Job, url: str, input_dir: Path) -> None:
        try:
            job.status = "running"
            job.step = "กำลังโหลดคลิปจาก YouTube"
            path = download_youtube(
                url, input_dir,
                on_progress=lambda p: setattr(job, "progress", p * 0.25),
            )
            job.source = path
            job.progress = 0.25
        except Exception as err:
            self._fail(job, err)
            return
        self._analyze(job)

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
                    shot.frames = extract_strip(job.source, shot, dest)
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

            job.step = "หาข้อความที่ติดมากับภาพ"
            try:
                job.text = detect_shots_text(
                    job.source, shots, self.work_dir / job.id,
                    on_progress=lambda p: setattr(job, "progress", 0.90 + 0.06 * p),
                )
                job.suggested_bands = suggest_bands(job.text)
            except Exception:  # noqa: BLE001 — ตรวจข้อความพลาดไม่ควรล้มทั้งงาน
                traceback.print_exc()
                job.text, job.suggested_bands = {}, None

            job.step = "วัดระดับเสียงแต่ละซีน"
            try:
                job.audio = measure_shots(job.source, shots)
            except Exception:  # noqa: BLE001 — วัดเสียงไม่ได้ไม่ควรล้มทั้งงาน
                job.audio = {}

            job.step = "ตัดสินว่าซีนไหน crop ได้ ซีนไหนต้องย่อ"
            job.detections = detections
            # ไม่ใส่แถบให้เอง — การเดาพลาดได้กับคลิปที่มีสกรีนช็อตเยอะ
            # โชว์เป็นข้อเสนอให้คนกดรับแทน
            job.plan = build_plan(
                job.source, info, shots, detections,
                audio=job.audio, text=job.text,
            )
            job.subtitle_hint = _subtitle_hint(shots, detections)
            _write_plan(self.work_dir / job.id / "edit-plan.json", job.plan)

            s = job.plan["summary"]
            job.step = f"พร้อมสร้างไฟล์ — เต็มจอ {s['crop']} ซีน · ย่อทั้งภาพ {s['pad']} ซีน"
            job.status = "ready"
            job.progress = 1.0
            self.save(job)

        except Exception as err:
            self._fail(job, err)

    def _render(self, job: Job) -> None:
        try:
            job.status = "rendering"
            job.progress = 0.0
            job.step = "กำลัง render"

            out_dir = self.output_dir / _safe_stem(job.source)
            dest = out_dir / f"{_safe_stem(job.source)}_9x16.mp4"
            total = sum(1 for s in job.plan["shots"] if s.get("included", True))
            render_plan(
                job.source, job.plan, self.work_dir / job.id, dest,
                on_progress=lambda p: (
                    setattr(job, "progress", p),
                    setattr(job, "step", f"กำลังสร้างไฟล์ ซีนที่ {max(1, round(p * total))}/{total}"),
                ),
                should_cancel=lambda: job.cancel,
            )
            _write_plan(out_dir / "edit-plan.json", job.plan)

            checklist = out_dir / "graphics-checklist.md"
            checklist.write_text(build_checklist(job.plan), encoding="utf-8")
            job.checklist = str(checklist)

            job.output = str(dest)
            job.step = f"เสร็จแล้ว — {dest.name}"
            job.status = "done"
            job.progress = 1.0
            self.save(job)

        except Exception as err:
            self._fail(job, err)

    def _fail(self, job: Job, err: Exception) -> None:
        if isinstance(err, RenderCancelled):
            job.status = "ready"
            job.step = "ยกเลิกแล้ว"
            job.progress = 1.0
            job.cancel = False
            return
        if isinstance(err, AnalyzeError):
            job.error = str(err)
        else:
            traceback.print_exc()
            job.error = f"เกิดข้อผิดพลาดที่ไม่คาดคิด: {type(err).__name__}"
        job.status = "error"
        job.step = "หยุดเพราะมีปัญหา"


def _info_from(job: Job):
    from app.analyze import VideoInfo

    i = job.info
    return VideoInfo(width=i["width"], height=i["height"], duration=i["duration"], fps=i["fps"])


def _subtitle_hint(shots: list[Shot], detections: list[ShotDetections]) -> float:
    """เดาว่าควรโชว์เฟรมไหนตอนตั้งแถบซับ

    ซับที่ burn มามักอยู่บนซีนที่คนพูด ไม่ใช่ b-roll หรือสกรีนช็อต
    จึงเลือกซีนที่ยาวสุดในบรรดาซีนที่เจอคนแทบทุกเฟรม
    (เคยลองหาจากความหนาแน่นของขอบแล้วมันไปเลือกสกรีนช็อต Google แทน)
    """
    by_index = {d.shot_index: d for d in detections}
    talking = [s for s in shots if by_index.get(s.index) and by_index[s.index].hit_rate >= 0.8]
    pick = max(talking or shots, key=lambda s: s.duration, default=None)
    return round(pick.midpoint, 2) if pick else 0.0


def _base_from_center(plan: dict, bands, info) -> dict:
    """กรอบฐานกลางเฟรม ใช้ตอนคนสั่งให้เป็นเต็มจอทั้งที่เครื่องไม่ได้คำนวณกรอบไว้ให้"""
    h = bands.effective_height(info.height)
    w = min(info.width, h * plan["target_size"]["width"] / plan["target_size"]["height"])
    return {"center_x": info.width / 2, "w": float(w), "h": float(h),
            "y": bands.offset_y(info.height)}


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
