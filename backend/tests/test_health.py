from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["station_stop_id"] == "R06"
    assert isinstance(body["uptime_s"], (int, float))


def test_unimplemented_routers_wired():
    # Skeleton placeholders exist; Phases 2-4 will replace them.
    for path in ("/api/trains", "/api/weather", "/api/photos"):
        r = client.get(path)
        assert r.status_code == 200
        assert "error" in r.json() or "phase" in r.json() or isinstance(r.json(), dict)
