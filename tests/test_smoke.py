import shutil

import pytest
from fastapi.testclient import TestClient

from app.analyze import detect_shots, probe
from app.main import INPUT_DIR, app

client = TestClient(app)


@pytest.fixture
def sample(tmp_path_factory):
    """คลิปทดสอบ 4 ซีน สร้างด้วย ffmpeg"""
    import subprocess

    path = tmp_path_factory.mktemp("media") / "sample.mp4"
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25:duration=2",
            "-f", "lavfi", "-i", "smptebars=size=640x360:rate=25:duration=2",
            "-f", "lavfi", "-i", "color=c=navy:size=640x360:rate=25:duration=2",
            "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]",
            "-map", "[v]", "-pix_fmt", "yuv420p", "-c:v", "libx264", str(path),
        ],
        check=True, capture_output=True,
    )
    return path


def test_health_reports_ok_and_sees_media_dir():
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["media_dir"] == "found"


def test_index_serves_the_ui():
    res = client.get("/")
    assert res.status_code == 200
    assert "clipcut" in res.text


def test_probe_reads_dimensions_and_duration(sample):
    info = probe(sample)
    assert (info.width, info.height) == (640, 360)
    assert info.duration == pytest.approx(6.0, abs=0.2)


def test_detect_shots_finds_every_cut(sample):
    shots = detect_shots(sample)
    assert len(shots) == 3
    assert shots[0].start == 0.0
    assert shots[-1].end == pytest.approx(6.0, abs=0.2)
    # shot ต้องต่อกันไม่มีช่องว่าง
    for earlier, later in zip(shots, shots[1:]):
        assert earlier.end == later.start


def test_unknown_source_is_rejected():
    assert client.post("/api/jobs", params={"name": "ไม่มีไฟล์นี้.mp4"}).status_code == 404


def test_path_traversal_is_rejected():
    assert client.post("/api/jobs", params={"name": "../../etc/passwd"}).status_code == 404


def test_job_runs_end_to_end_and_produces_thumbnails(sample):
    """ทดสอบทั้งเส้น: submit -> วิเคราะห์ -> ได้ภาพตัวอย่างที่โหลดได้จริง"""
    dest = INPUT_DIR / "pytest-sample.mp4"
    shutil.copy(sample, dest)
    try:
        job = client.post("/api/jobs", params={"name": dest.name}).json()
        for _ in range(200):
            job = client.get(f"/api/jobs/{job['id']}").json()
            if job["status"] in ("done", "error"):
                break
        assert job["status"] == "done", job.get("error")
        assert len(job["shots"]) == 3
        assert all(s["thumbnail"] for s in job["shots"])
        assert client.get(job["shots"][0]["thumbnail"]).status_code == 200
    finally:
        dest.unlink(missing_ok=True)
