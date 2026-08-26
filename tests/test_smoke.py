import shutil
from pathlib import Path
import time

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


def _wait(job_id, want, timeout=300):
    deadline = time.monotonic() + timeout
    job = client.get(f"/api/jobs/{job_id}").json()
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in (want, "error"):
            return job
        time.sleep(0.2)
    return job


def test_pipeline_runs_from_analyse_to_rendered_file(sample):
    """ทดสอบทั้งเส้น: วิเคราะห์ -> พลิกการตัดสิน -> render -> ได้ไฟล์ 9:16 จริง"""
    dest = INPUT_DIR / "pytest-sample.mp4"
    shutil.copy(sample, dest)
    try:
        job = client.post("/api/jobs", params={"name": dest.name}).json()
        job = _wait(job["id"], "ready")
        assert job["status"] == "ready", job.get("error")

        assert len(job["shots"]) == 3
        assert all(s["thumbnail"] for s in job["shots"])
        assert client.get(job["shots"][0]["thumbnail"]).status_code == 200

        # ทุกซีนต้องมีการตัดสินพร้อมเหตุผล
        for shot in job["shots"]:
            assert shot["plan"]["mode"] in ("crop", "pad")
            assert shot["plan"]["reason"]
        assert job["summary"]["crop"] + job["summary"]["pad"] == 3

        # คนพลิกการตัดสินได้ และต้องได้กรอบ crop มาด้วยแม้เครื่องไม่ได้คำนวณไว้
        flipped = client.post(
            f"/api/jobs/{job['id']}/shots/0/mode", params={"mode": "crop"}
        ).json()
        first = flipped["shots"][0]["plan"]
        assert first["mode"] == "crop"
        assert first["crop"]["w"] > 0

        assert client.post(
            f"/api/jobs/{job['id']}/shots/0/mode", params={"mode": "หมุน"}
        ).status_code == 400

        # render ออกมาเป็นไฟล์ 9:16 จริง
        client.post(f"/api/jobs/{job['id']}/render")
        job = _wait(job["id"], "done")
        assert job["status"] == "done", job.get("error")

        out = Path(job["output"])
        assert out.is_file()
        info = probe(out)
        assert (info.width, info.height) == (1080, 1920)
        assert client.get(f"/api/jobs/{job['id']}/output").status_code == 200
    finally:
        dest.unlink(missing_ok=True)


def test_render_before_analysis_is_rejected():
    assert client.post("/api/jobs/ไม่มีงานนี้/render").status_code == 404


@pytest.fixture
def subtle(tmp_path_factory):
    """คลิปที่ฉากเปลี่ยนแบบเนียน — สีใกล้กันจนระดับหยาบจับไม่ได้"""
    import subprocess

    path = tmp_path_factory.mktemp("media") / "subtle.mp4"
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=0x203050:size=640x360:rate=25:duration=2",
            "-f", "lavfi", "-i", "color=c=0x243a5e:size=640x360:rate=25:duration=2",
            "-f", "lavfi", "-i", "color=c=0x2a4570:size=640x360:rate=25:duration=2",
            "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]",
            "-map", "[v]", "-pix_fmt", "yuv420p", "-c:v", "libx264", str(path),
        ],
        check=True, capture_output=True,
    )
    return path


def test_every_level_finds_hard_cuts(sample):
    """รอยตัดชัดๆ ต้องเจอครบทุกระดับ"""
    from app.analyze import SENSITIVITY

    for level in SENSITIVITY:
        assert len(detect_shots(sample, level)) == 3, level


def test_finer_levels_catch_subtle_scene_changes(subtle):
    """ฉากที่เปลี่ยนแบบเนียน ระดับหยาบจับไม่ได้ แต่ระดับละเอียดมากต้องจับได้"""
    assert len(detect_shots(subtle, "coarse")) == 1
    assert len(detect_shots(subtle, "finest")) == 3


def test_camera_motion_does_not_create_false_cuts(tmp_path):
    """กล้องขยับตลอดทั้งคลิปต้องไม่ถูกแบ่งเป็นหลายซีน แม้ที่ระดับละเอียดที่สุด"""
    import subprocess

    path = tmp_path / "motion.mp4"
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25:duration=6",
            "-pix_fmt", "yuv420p", "-c:v", "libx264", str(path),
        ],
        check=True, capture_output=True,
    )
    assert len(detect_shots(path, "finest")) == 1


def test_bad_sensitivity_is_rejected(sample):
    from app.analyze import AnalyzeError

    with pytest.raises(AnalyzeError):
        detect_shots(sample, "ระดับที่ไม่มีอยู่")
    # พารามิเตอร์ผิดต้องได้ 400 แม้ไฟล์จะไม่มีอยู่จริง
    res = client.post("/api/jobs", params={"name": "x.mp4", "sensitivity": "nope"})
    assert res.status_code == 400
