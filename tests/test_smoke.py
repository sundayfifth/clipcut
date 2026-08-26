import shutil
from pathlib import Path
import time

import pytest
from fastapi.testclient import TestClient

from app.analyze import detect_shots, probe
from app.main import INPUT_DIR, MEDIA_DIR, WORK_DIR, app

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


# ── แถบซับ / โลโก้ ────────────────────────────────────────────

def test_trim_shrinks_the_usable_height_but_blur_does_not():
    from app.bands import Bands

    assert Bands(bottom=0.13, mode="trim").effective_height(720) == 626
    assert Bands(bottom=0.13, mode="blur").effective_height(720) == 720


def test_band_values_are_clamped_and_bad_mode_rejected():
    from app.bands import Bands

    assert Bands(top=-1).top == 0.0
    assert Bands(top=9).top == 0.45  # เกิน 45% แปลว่าตั้งผิด ไม่ใช่แถบซับแล้ว
    with pytest.raises(ValueError):
        Bands(mode="หมุน")


def test_band_filter_is_none_when_nothing_to_do():
    from app.bands import Bands, band_filter

    assert band_filter(Bands(), 1280, 720) is None


def test_trim_makes_the_crop_window_narrower(sample):
    """ตัดแถบล่างแล้วกรอบ 9:16 ต้องแคบลงตามความสูงที่เหลือ"""
    from app.analyze import probe
    from app.bands import Bands
    from app.detect import ShotDetections
    from app.plan import plan_shot

    info = probe(sample)
    shot = detect_shots(sample)[0]
    empty = ShotDetections(shot_index=shot.index, frames_sampled=5, frames_with_person=0, per_frame=[])

    plain = plan_shot(shot, info, empty)
    trimmed = plan_shot(shot, info, empty, Bands(bottom=0.2, mode="trim"))
    # ไม่เจอคน -> pad ทั้งคู่ แต่ความสูงที่ใช้ได้ต้องต่างกัน
    assert plain.mode == trimmed.mode == "pad"
    assert Bands(bottom=0.2, mode="trim").effective_height(info.height) < info.height


# ── เลือกซีน ─────────────────────────────────────────────────

def test_shots_default_to_all_selected_and_can_be_deselected(sample):
    dest = INPUT_DIR / "pytest-select.mp4"
    shutil.copy(sample, dest)
    try:
        job = client.post("/api/jobs", params={"name": dest.name}).json()
        job = _wait(job["id"], "ready")
        assert job["summary"]["included"] == job["summary"]["total"] == 3

        job = client.post(
            f"/api/jobs/{job['id']}/shots/1/included", params={"included": False}
        ).json()
        assert job["summary"]["included"] == 2
        assert job["shots"][1]["plan"]["included"] is False

        # ไม่เลือกเลยแล้ว render ต้องถูกปฏิเสธพร้อมข้อความที่อ่านรู้เรื่อง
        for i in (0, 2):
            job = client.post(
                f"/api/jobs/{job['id']}/shots/{i}/included", params={"included": False}
            ).json()
        assert job["summary"]["included"] == 0
        client.post(f"/api/jobs/{job['id']}/render")
        job = _wait(job["id"], "done", timeout=30)
        assert job["status"] == "error"
        assert "เลือก" in job["error"]
    finally:
        dest.unlink(missing_ok=True)


# ── YouTube ──────────────────────────────────────────────────

def test_only_youtube_urls_are_accepted():
    from app.ingest import is_youtube_url

    assert is_youtube_url("https://www.youtube.com/watch?v=abc")
    assert is_youtube_url("https://youtu.be/abc")
    assert not is_youtube_url("https://vimeo.com/123")
    assert not is_youtube_url("ไม่ใช่ url")
    assert client.post("/api/youtube", params={"url": "https://vimeo.com/1"}).status_code == 400


# ── checklist ────────────────────────────────────────────────

def test_checklist_names_what_the_editor_must_redo():
    from app.report import build_checklist

    plan = {
        "source": "a.mp4",
        "source_size": {"width": 1280, "height": 720},
        "target_size": {"width": 1080, "height": 1920},
        "bands": {"top": 0.0, "bottom": 0.13, "mode": "trim"},
        "summary": {"total": 2, "included": 1, "crop": 1, "pad": 0, "duration": 2.0},
        "shots": [
            {"shot_index": 0, "start": 0.0, "end": 2.0, "mode": "crop", "reason": "x",
             "crop": {"x": 400, "y": 0, "w": 405, "h": 720}, "confidence": 0.9,
             "included": True, "path": {"kind": "poly", "coeffs": [1.0]}},
            {"shot_index": 1, "start": 2.0, "end": 4.0, "mode": "pad", "reason": "y",
             "crop": None, "confidence": 0.0, "included": False, "path": None},
        ],
    }
    text = build_checklist(plan)
    assert "ซับไตเติล" in text            # แถบถูกตัด -> ต้องใส่ซับใหม่
    assert "subtitle-align" in text        # ชี้ไปที่ skill ที่มีอยู่
    assert "ตัดข้างซ้าย 400px" in text     # บอกว่าหายไปเท่าไหร่
    assert "ซีนที่ข้ามไป" in text          # ซีนที่ไม่ได้เลือกต้องถูกระบุ


# ── ปรับกรอบเอง ──────────────────────────────────────────────

def test_adjusted_crop_keeps_9x16_and_stays_inside_the_frame():
    from app.analyze import VideoInfo
    from app.plan import derive_crop

    info = VideoInfo(width=1280, height=720, duration=10, fps=30)
    base = {"center_x": 640.0, "w": 405.0, "h": 720.0, "y": 0}

    for adjust in [None, {"dx": -1}, {"dx": 1}, {"scale": 0.4},
                   {"scale": 0.5, "dx": 0.9, "dy": -1}, {"scale": 0.01, "dx": 5}]:
        c = derive_crop(base, adjust, info)
        assert c["x"] >= 0 and c["x"] + c["w"] <= info.width, (adjust, c)
        assert c["y"] >= 0 and c["y"] + c["h"] <= info.height, (adjust, c)
        assert abs(c["w"] / c["h"] - 9 / 16) < 0.01, (adjust, c)


def test_zoom_is_clamped_so_output_never_upscales_too_far():
    from app.plan import MIN_SCALE, clamp_adjust

    assert clamp_adjust({"scale": 0.01})["scale"] == MIN_SCALE
    assert clamp_adjust({"scale": 99})["scale"] == 1.0
    assert clamp_adjust({"dx": -9})["dx"] == -1.0


def test_crop_can_be_nudged_and_survives_a_band_change(sample):
    dest = INPUT_DIR / "pytest-tune.mp4"
    shutil.copy(sample, dest)
    try:
        job = client.post("/api/jobs", params={"name": dest.name}).json()
        job = _wait(job["id"], "ready")
        jid = job["id"]

        # หาซีนที่เป็นโหมด crop มาปรับ (ถ้าไม่มีก็พลิกให้เป็น crop ก่อน)
        idx = next((s["index"] for s in job["shots"] if s["plan"]["mode"] == "crop"), None)
        if idx is None:
            idx = 0
            client.post(f"/api/jobs/{jid}/shots/0/mode", params={"mode": "crop"})

        before = client.get(f"/api/jobs/{jid}").json()["shots"][idx]["plan"]["crop"]["x"]
        job = client.post(
            f"/api/jobs/{jid}/shots/{idx}/crop", params={"dx": 0.3, "scale": 0.6}
        ).json()
        plan = job["shots"][idx]["plan"]
        assert plan["adjust"] == {"dx": 0.3, "dy": 0.0, "scale": 0.6}
        assert plan["crop"]["x"] != before          # กรอบขยับจริง
        assert plan["crop"]["w"] < plan["crop_base"]["w"]  # ซูมเข้าจริง

        # ขยับแถบซับแล้วคำนวณใหม่ ค่าที่ปรับเองต้องไม่หาย
        job = client.post(f"/api/jobs/{jid}/bands", params={"bottom": 0.1}).json()
        assert job["shots"][idx]["plan"]["adjust"]["scale"] == 0.6

        # ซีนที่เป็นโหมดย่อทั้งภาพ ปรับกรอบไม่ได้
        pad = next((s["index"] for s in job["shots"] if s["plan"]["mode"] == "pad"), None)
        if pad is not None:
            assert client.post(
                f"/api/jobs/{jid}/shots/{pad}/crop", params={"dx": 0.2}
            ).status_code == 400
    finally:
        dest.unlink(missing_ok=True)


# ── เก็บงานลงดิสก์ / undo ────────────────────────────────────

def test_every_edit_survives_a_restart(sample, tmp_path):
    """แก้ครบทุกอย่าง แล้วโหลด store ใหม่ ต้องได้สถานะเดิมกลับมาทั้งหมด

    เขียนไว้เพราะเคยลืมใส่ save() ใน 2 เมธอด แล้วงานที่ตรวจไว้หายตอนรีสตาร์ท
    """
    from app.jobs import JobStore

    dest = INPUT_DIR / "pytest-persist.mp4"
    shutil.copy(sample, dest)
    try:
        job = client.post("/api/jobs", params={"name": dest.name}).json()
        jid = job["id"]
        job = _wait(jid, "ready")
        assert job["status"] == "ready", job.get("error")

        client.post(f"/api/jobs/{jid}/shots/0/mode", params={"mode": "crop"})
        client.post(f"/api/jobs/{jid}/shots/0/crop", params={"dx": -0.3, "scale": 0.75})
        client.post(f"/api/jobs/{jid}/shots/1/included", params={"included": False})
        before = client.post(f"/api/jobs/{jid}/bands", params={"bottom": 0.12}).json()

        # จำลองการปิดแล้วเปิด server ใหม่
        fresh = JobStore(WORK_DIR, MEDIA_DIR / "output")
        assert fresh.restore() >= 1
        after = fresh.get(jid)
        assert after is not None, "กู้งานกลับมาไม่ได้"

        assert after.plan["bands"] == before["bands"]
        assert after.plan["summary"] == before["summary"]
        for i in (0, 1):
            assert after.plan["shots"][i] == before["shots"][i]["plan"], f"ซีน {i} ไม่ตรง"
        assert after.detections, "ผลตรวจจับคนต้องถูกเก็บด้วย ไม่งั้นขยับแถบแล้วคำนวณใหม่ไม่ได้"
    finally:
        dest.unlink(missing_ok=True)


def test_undo_walks_back_one_edit_at_a_time(sample):
    dest = INPUT_DIR / "pytest-undo.mp4"
    shutil.copy(sample, dest)
    try:
        job = client.post("/api/jobs", params={"name": dest.name}).json()
        jid = job["id"]
        job = _wait(jid, "ready")
        assert not job["can_undo"]

        client.post(f"/api/jobs/{jid}/shots/0/included", params={"included": False})
        job = client.post(f"/api/jobs/{jid}/shots/1/included", params={"included": False}).json()
        assert job["summary"]["included"] == 1
        assert job["can_undo"]

        job = client.post(f"/api/jobs/{jid}/undo").json()
        assert job["summary"]["included"] == 2
        job = client.post(f"/api/jobs/{jid}/undo").json()
        assert job["summary"]["included"] == 3
        assert not job["can_undo"]
        assert client.post(f"/api/jobs/{jid}/undo").status_code == 400
    finally:
        dest.unlink(missing_ok=True)
