"""คิวงานวิเคราะห์แบบง่าย รันใน thread แยก

เป็น local single-user tool จึงเก็บ state ไว้ใน memory พอ — ไม่ต้องมี DB
งานวิเคราะห์กินเวลาหลายนาทีต่อคลิป UI จึงต้อง poll ดู progress ได้ (กติกาใน CLAUDE.md)
"""

from __future__ import annotations

import threading
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from app.analyze import AnalyzeError, Shot, detect_shots, extract_thumbnail, probe, shot_to_dict


@dataclass
class Job:
    id: str
    source: Path
    status: str = "pending"  # pending | running | done | error
    step: str = "รอเริ่ม"
    progress: float = 0.0
    error: str | None = None
    info: dict | None = None
    shots: list[Shot] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.source.name,
            "status": self.status,
            "step": self.step,
            "progress": round(self.progress, 3),
            "error": self.error,
            "info": self.info,
            "shots": [shot_to_dict(s) for s in self.shots],
        }


class JobStore:
    def __init__(self, work_dir: Path) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self.work_dir = work_dir

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        with self._lock:
            return list(self._jobs.values())

    def submit(self, source: Path) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], source=source)
        with self._lock:
            self._jobs[job.id] = job
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return job

    def _run(self, job: Job) -> None:
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
            job.progress = 0.05

            job.step = "หารอยตัดระหว่างซีน"
            shots = detect_shots(job.source)
            job.shots = shots
            job.progress = 0.35

            out_dir = self.work_dir / job.id / "thumbs"
            for i, shot in enumerate(shots, start=1):
                job.step = f"ดึงภาพตัวอย่าง {i}/{len(shots)}"
                dest = out_dir / f"shot-{shot.index:04d}.jpg"
                try:
                    extract_thumbnail(job.source, shot.midpoint, dest)
                    shot.thumbnail = f"/api/jobs/{job.id}/thumbs/{dest.name}"
                except AnalyzeError:
                    shot.thumbnail = None  # ภาพเดียวพลาดไม่ควรล้มทั้งงาน
                job.progress = 0.35 + 0.65 * (i / len(shots))

            job.step = f"เสร็จแล้ว — พบ {len(shots)} ซีน"
            job.status = "done"
            job.progress = 1.0

        except AnalyzeError as err:
            job.status, job.error, job.step = "error", str(err), "หยุดเพราะมีปัญหา"
        except Exception as err:  # noqa: BLE001 — กันไม่ให้ thread ตายเงียบ
            traceback.print_exc()
            job.status = "error"
            job.error = f"เกิดข้อผิดพลาดที่ไม่คาดคิด: {type(err).__name__}"
            job.step = "หยุดเพราะมีปัญหา"
