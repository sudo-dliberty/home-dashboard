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


def test_spa_cache_headers(tmp_path):
    # The entry HTML must never be stored (Chromium's session restore serves
    # cached pages without revalidating, even under no-cache); hashed assets
    # are immutable.
    from fastapi import FastAPI

    from app.main import SPAStaticFiles

    (tmp_path / "index.html").write_text("<!doctype html>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log(1)")
    spa = FastAPI()
    spa.mount("/", SPAStaticFiles(directory=tmp_path, html=True))
    c = TestClient(spa)

    assert c.get("/").headers["cache-control"] == "no-store"
    assert (
        c.get("/assets/index-abc123.js").headers["cache-control"]
        == "public, max-age=31536000, immutable"
    )
