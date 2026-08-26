"""รับคลิปเข้าระบบ — จากไฟล์ในเครื่อง หรือจาก URL YouTube"""

from __future__ import annotations

import re
from pathlib import Path

from app.analyze import AnalyzeError

YOUTUBE_HOSTS = ("youtube.com", "youtu.be", "m.youtube.com", "www.youtube.com")
_SAFE = re.compile(r'[/\\:*?"<>|\x00-\x1f]')


def is_youtube_url(value: str) -> bool:
    value = value.strip().lower()
    if not value.startswith(("http://", "https://")):
        return False
    host = value.split("/")[2].split(":")[0]
    return host in YOUTUBE_HOSTS


def safe_name(name: str) -> str:
    """ชื่อไฟล์ที่ไม่ทำให้ path พัง — คงภาษาไทยไว้"""
    cleaned = _SAFE.sub("_", name).strip(" .")
    return cleaned[:120] or "video"


def download_youtube(url: str, dest_dir: Path, on_progress=None) -> Path:
    """โหลดคลิปจาก YouTube ลง dest_dir แล้วคืน path ของไฟล์

    เลือก mp4 ที่ไม่เกิน 1080p — ต้นทางใหญ่กว่านั้นไม่ได้ช่วยอะไรกับ output 9:16
    """
    try:
        from yt_dlp import YoutubeDL
    except ImportError as err:  # pragma: no cover
        raise AnalyzeError("ยังไม่ได้ติดตั้ง yt-dlp") from err

    dest_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[str] = []

    def hook(status: dict) -> None:
        if status.get("status") == "downloading" and on_progress:
            total = status.get("total_bytes") or status.get("total_bytes_estimate")
            if total:
                on_progress(min(0.99, status.get("downloaded_bytes", 0) / total))
        elif status.get("status") == "finished":
            downloaded.append(status["filename"])

    options = {
        "format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "outtmpl": str(dest_dir / "%(title).100B.%(ext)s"),
        "restrictfilenames": False,
        "windowsfilenames": True,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook],
    }

    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            path = Path(ydl.prepare_filename(info))
    except Exception as err:
        raise AnalyzeError(
            f"โหลดคลิปจาก YouTube ไม่สำเร็จ — ตรวจว่า URL ถูกต้องและคลิปไม่ได้ตั้งเป็นส่วนตัว "
            f"({type(err).__name__})"
        ) from err

    if not path.exists():
        # merge แล้วนามสกุลอาจเปลี่ยน หา candidate จาก hook แทน
        for candidate in (Path(p) for p in reversed(downloaded)):
            if candidate.exists():
                return candidate
        merged = path.with_suffix(".mp4")
        if merged.exists():
            return merged
        raise AnalyzeError("โหลดเสร็จแต่หาไฟล์ผลลัพธ์ไม่เจอ")
    return path
