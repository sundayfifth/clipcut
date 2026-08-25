"""clipcut — local web app สำหรับแปลงคลิป 16:9 เป็น 9:16

ตอนนี้เป็นโครงขั้นต่ำ: serve หน้า UI + health check
pipeline จริง (ingest -> analyze -> plan -> render -> report) ยังไม่ได้เขียน
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
MEDIA_DIR = BASE_DIR.parent / "media"

# media/ ถูก gitignore ไว้ทั้งก้อน — สร้างให้เองตอน start จะได้ clone มาแล้วรันได้เลย
for _sub in ("input", "work", "output"):
    (MEDIA_DIR / _sub).mkdir(parents=True, exist_ok=True)

app = FastAPI(title="clipcut", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    """เช็คว่า server ขึ้นแล้วและเห็นโฟลเดอร์ media"""
    return {
        "status": "ok",
        "version": app.version,
        "media_dir": "found" if MEDIA_DIR.is_dir() else "missing",
    }


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
