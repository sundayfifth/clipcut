"""clipcut — local web app สำหรับแปลงคลิป 16:9 เป็น 9:16

ตอนนี้ทำได้ถึงขั้น: เลือกไฟล์ -> หา shot -> โชว์ภาพตัวอย่างต่อ shot
ขั้นต่อไป (ยังไม่ทำ): ตรวจจับตัวคน, ตัดสิน crop-vs-pad, render
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.analyze import DEFAULT_SENSITIVITY, SENSITIVITY
from app.jobs import JobStore

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
MEDIA_DIR = BASE_DIR.parent / "media"
INPUT_DIR = MEDIA_DIR / "input"
WORK_DIR = MEDIA_DIR / "work"

# media/ ถูก gitignore ไว้ทั้งก้อน — สร้างให้เองตอน start จะได้ clone มาแล้วรันได้เลย
for _sub in ("input", "work", "output"):
    (MEDIA_DIR / _sub).mkdir(parents=True, exist_ok=True)

VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}

app = FastAPI(title="clipcut", version="0.2.0")
jobs = JobStore(WORK_DIR)


@app.get("/health")
def health() -> dict[str, str]:
    """เช็คว่า server ขึ้นแล้วและเห็นโฟลเดอร์ media"""
    return {
        "status": "ok",
        "version": app.version,
        "media_dir": "found" if MEDIA_DIR.is_dir() else "missing",
    }


@app.get("/api/sources")
def list_sources() -> dict:
    """ไฟล์วีดีโอที่วางไว้ใน media/input/"""
    files = sorted(
        (p for p in INPUT_DIR.iterdir() if p.suffix.lower() in VIDEO_SUFFIXES),
        key=lambda p: p.name.lower(),
    )
    return {
        "sources": [
            {"name": p.name, "size_mb": round(p.stat().st_size / 1_048_576, 1)}
            for p in files
        ]
    }


def _resolve_source(name: str) -> Path:
    """กัน path traversal — รับได้เฉพาะไฟล์ที่อยู่ใน media/input/ ตรงๆ"""
    candidate = (INPUT_DIR / name).resolve()
    if candidate.parent != INPUT_DIR.resolve() or not candidate.is_file():
        raise HTTPException(404, f"ไม่พบไฟล์ '{name}' ใน media/input/")
    return candidate


def _check_sensitivity(value: str) -> str:
    if value not in SENSITIVITY:
        raise HTTPException(
            400, f"ระดับความละเอียด '{value}' ไม่ถูกต้อง (เลือกได้: {', '.join(SENSITIVITY)})"
        )
    return value


@app.get("/api/sensitivity")
def sensitivity_options() -> dict:
    """ระดับความละเอียดที่เลือกได้ พร้อมค่า threshold จริงเพื่อความโปร่งใส"""
    return {
        "default": DEFAULT_SENSITIVITY,
        "levels": [
            {"key": k, "threshold": th, "min_seconds": mn}
            for k, (th, mn) in SENSITIVITY.items()
        ],
    }


@app.post("/api/jobs")
def create_job(name: str, sensitivity: str = DEFAULT_SENSITIVITY) -> dict:
    """เริ่มวิเคราะห์ไฟล์ที่อยู่ใน media/input/"""
    level = _check_sensitivity(sensitivity)
    return jobs.submit(_resolve_source(name), level).as_dict()


@app.post("/api/upload")
async def upload(file: UploadFile, sensitivity: str = DEFAULT_SENSITIVITY) -> dict:
    """อัปโหลดไฟล์เข้า media/input/ แล้วเริ่มวิเคราะห์เลย"""
    filename = Path(file.filename or "").name
    if not filename:
        raise HTTPException(400, "ไม่พบชื่อไฟล์")
    if Path(filename).suffix.lower() not in VIDEO_SUFFIXES:
        raise HTTPException(400, f"ไม่รองรับนามสกุลไฟล์นี้ (รองรับ: {', '.join(sorted(VIDEO_SUFFIXES))})")

    dest = INPUT_DIR / filename
    if dest.exists():
        raise HTTPException(409, f"มีไฟล์ชื่อ '{filename}' อยู่แล้ว — เปลี่ยนชื่อก่อนอัปโหลด")

    with dest.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            out.write(chunk)

    return jobs.submit(dest, _check_sensitivity(sensitivity)).as_dict()


@app.get("/api/jobs")
def list_jobs() -> dict:
    return {"jobs": [j.as_dict() for j in jobs.list()]}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "ไม่พบงานนี้")
    return job.as_dict()


@app.get("/api/jobs/{job_id}/thumbs/{filename}")
def get_thumb(job_id: str, filename: str) -> FileResponse:
    path = (WORK_DIR / job_id / "thumbs" / Path(filename).name).resolve()
    if not path.is_file() or WORK_DIR.resolve() not in path.parents:
        raise HTTPException(404, "ไม่พบภาพตัวอย่าง")
    return FileResponse(path)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
