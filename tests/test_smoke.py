from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_reports_ok_and_sees_media_dir():
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["media_dir"] == "found"


def test_index_serves_the_ui():
    res = client.get("/")
    assert res.status_code == 200
    assert "clipcut" in res.text
