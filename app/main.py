"""clipcut — local web app สำหรับแปลงคลิป 16:9 เป็น 9:16

เส้นทางเต็ม: รับไฟล์/URL -> แบ่งซีน -> ตรวจจับคน -> ตั้งแถบซับ -> เลือกซีน
-> ตัดสิน crop/pad ต่อซีน -> render mp4 9:16 + checklist กราฟฟิก
"""

import subprocess
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.analyze import AnalyzeError, DEFAULT_SENSITIVITY, SENSITIVITY
from app.bands import Bands, band_filter
from app.jobs import JobStore
from app.preview_audio import join_audio, shot_audio

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
MEDIA_DIR = BASE_DIR.parent / "media"
INPUT_DIR = MEDIA_DIR / "input"
WORK_DIR = MEDIA_DIR / "work"
OUTPUT_DIR = MEDIA_DIR / "output"

# media/ ถูก gitignore ไว้ทั้งก้อน — สร้างให้เองตอน start จะได้ clone มาแล้วรันได้เลย
for _sub in ("input", "work", "output"):
    (MEDIA_DIR / _sub).mkdir(parents=True, exist_ok=True)

VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}

app = FastAPI(title="clipcut", version="0.7.0")
jobs = JobStore(WORK_DIR, OUTPUT_DIR)
_restored = jobs.restore()
if _restored:
    print(f"เปิดงานที่ค้างไว้กลับมา {_restored} งาน")


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


@app.post("/api/youtube")
def create_job_from_url(url: str, sensitivity: str = DEFAULT_SENSITIVITY) -> dict:
    """โหลดคลิปจาก YouTube แล้ววิเคราะห์ต่อเลย"""
    level = _check_sensitivity(sensitivity)
    try:
        return jobs.submit_url(url, INPUT_DIR, level).as_dict()
    except AnalyzeError as err:
        raise HTTPException(400, str(err)) from err


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
    return _require_job(job_id).as_dict()


def _require_job(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "ไม่พบงานนี้")
    return job


@app.post("/api/jobs/{job_id}/shots/{shot_index}/mode")
def set_shot_mode(job_id: str, shot_index: int, mode: str) -> dict:
    """ให้คนพลิกการตัดสินของเครื่อง — เช่นสกรีนช็อตที่ detector เห็นรูปคนแล้ว crop ผิด"""
    job = _require_job(job_id)
    try:
        jobs.set_mode(job, shot_index, mode)
    except AnalyzeError as err:
        raise HTTPException(400, str(err)) from err
    return job.as_dict()


@app.post("/api/jobs/{job_id}/shots/{shot_index}/included")
def set_shot_included(job_id: str, shot_index: int, included: bool) -> dict:
    """เลือกว่าจะเอาซีนนี้ไปประกอบเป็นไฟล์ 9:16 มั้ย — ค่าตั้งต้นคือเอาทั้งหมด"""
    job = _require_job(job_id)
    try:
        jobs.set_included(job, shot_index, included)
    except AnalyzeError as err:
        raise HTTPException(400, str(err)) from err
    return job.as_dict()


@app.post("/api/jobs/{job_id}/shots/{shot_index}/crop")
def set_shot_crop(job_id: str, shot_index: int,
                  dx: float = 0.0, dy: float = 0.0, scale: float = 1.0) -> dict:
    """เลื่อนกรอบซ้าย-ขวา บน-ล่าง และย่อ/ขยาย เฉพาะซีนที่เป็นโหมดเต็มจอ"""
    job = _require_job(job_id)
    try:
        jobs.set_crop_adjust(job, shot_index, {"dx": dx, "dy": dy, "scale": scale})
    except AnalyzeError as err:
        raise HTTPException(400, str(err)) from err
    return job.as_dict()


@app.post("/api/jobs/{job_id}/bands")
def set_bands(job_id: str, top: float = 0.0, bottom: float = 0.0, mode: str = "trim") -> dict:
    """ตั้งแถบซับ/โลโก้ที่จะตัดหรือเบลอ แล้วคำนวณแผนใหม่ทันที"""
    job = _require_job(job_id)
    try:
        jobs.set_bands(job, Bands(top=top, bottom=bottom, mode=mode))
    except (AnalyzeError, ValueError) as err:
        raise HTTPException(400, str(err)) from err
    return job.as_dict()


@app.get("/api/jobs/{job_id}/preview")
def preview_bands(job_id: str, at: float = 0.0, top: float = 0.0,
                  bottom: float = 0.0, mode: str = "trim") -> FileResponse:
    """เฟรมตัวอย่างที่ใส่แถบแล้ว ให้เลื่อนสไลเดอร์แล้วเห็นผลทันที"""
    job = _require_job(job_id)
    if not job.info:
        raise HTTPException(400, "ยังอ่านข้อมูลไฟล์ไม่เสร็จ")
    try:
        bands = Bands(top=top, bottom=bottom, mode=mode)
    except ValueError as err:
        raise HTTPException(400, str(err)) from err

    dest = WORK_DIR / job_id / "preview.jpg"
    dest.parent.mkdir(parents=True, exist_ok=True)
    chain = band_filter(bands, job.info["width"], job.info["height"])
    vf = f"[0:v]{chain},scale=640:-2[v]" if chain else "[0:v]scale=640:-2[v]"

    result = subprocess.run(
        [
            "ffmpeg", "-nostdin", "-y", "-loglevel", "error",
            "-ss", f"{max(0.0, at):.3f}", "-i", str(job.source),
            "-frames:v", "1", "-filter_complex", vf, "-map", "[v]", str(dest),
        ],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0 or not dest.exists():
        raise HTTPException(500, "สร้างภาพตัวอย่างไม่สำเร็จ")
    return FileResponse(dest, headers={"Cache-Control": "no-store"})


@app.get("/api/jobs/{job_id}/checklist")
def download_checklist(job_id: str) -> FileResponse:
    job = _require_job(job_id)
    if not job.checklist or not Path(job.checklist).is_file():
        raise HTTPException(404, "ยังไม่มี checklist — ต้อง render ก่อน")
    return FileResponse(job.checklist, filename=Path(job.checklist).name)


@app.post("/api/jobs/{job_id}/undo")
def undo(job_id: str) -> dict:
    """ย้อนการแก้ครั้งล่าสุด"""
    job = _require_job(job_id)
    try:
        jobs.undo(job)
    except AnalyzeError as err:
        raise HTTPException(400, str(err)) from err
    return job.as_dict()


@app.post("/api/jobs/{job_id}/cancel")
def cancel_render(job_id: str) -> dict:
    job = _require_job(job_id)
    try:
        jobs.cancel_render(job)
    except AnalyzeError as err:
        raise HTTPException(400, str(err)) from err
    return job.as_dict()


@app.post("/api/jobs/{job_id}/reveal")
def reveal_output(job_id: str) -> dict:
    """เปิดโฟลเดอร์ผลลัพธ์ใน Finder — สิ่งที่คนอยากทำจริงหลัง render เสร็จ"""
    job = _require_job(job_id)
    if not job.output or not Path(job.output).is_file():
        raise HTTPException(404, "ยังไม่มีไฟล์ผลลัพธ์")
    subprocess.run(["open", "-R", job.output], check=False, timeout=15)
    return {"ok": True}


@app.post("/api/jobs/{job_id}/render")
def start_render(job_id: str) -> dict:
    job = _require_job(job_id)
    try:
        jobs.start_render(job)
    except AnalyzeError as err:
        raise HTTPException(400, str(err)) from err
    return job.as_dict()


@app.get("/api/jobs/{job_id}/output")
def download_output(job_id: str) -> FileResponse:
    job = _require_job(job_id)
    if not job.output or not Path(job.output).is_file():
        raise HTTPException(404, "ยังไม่มีไฟล์ผลลัพธ์")
    return FileResponse(job.output, filename=Path(job.output).name)


@app.get("/api/jobs/{job_id}/shots/{shot_index}/audio")
def shot_audio_clip(job_id: str, shot_index: int, kind: str = "shot") -> FileResponse:
    """เสียงให้ฟังก่อนตัดสินใจ — kind=shot คือเสียงซีนนั้น · kind=join คือเสียงรอยต่อถ้าตัดออก"""
    job = _require_job(job_id)
    if not job.plan:
        raise HTTPException(400, "ยังวิเคราะห์ไม่เสร็จ")
    if kind not in ("shot", "join"):
        raise HTTPException(400, "kind ต้องเป็น shot หรือ join")

    shot_plan = next(
        (s for s in job.plan["shots"] if s["shot_index"] == shot_index), None
    )
    if shot_plan is None:
        raise HTTPException(404, f"ไม่พบซีนที่ {shot_index + 1}")

    dest = WORK_DIR / job_id / "audio" / f"{kind}-{shot_index:04d}.m4a"
    try:
        if kind == "shot":
            shot_audio(job.source, shot_plan, dest)
        else:
            join_audio(job.source, job.plan, shot_index, dest)
    except AnalyzeError as err:
        raise HTTPException(400, str(err)) from err
    return FileResponse(dest, media_type="audio/mp4", headers={"Cache-Control": "no-store"})


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
