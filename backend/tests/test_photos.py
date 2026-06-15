"""Tests for /api/photos listing + /api/photos/{filename} serving."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)

# Minimal but valid PNG magic header. Enough to verify byte-for-byte streaming.
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@pytest.fixture
def photo_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point settings.photo_dir at a writable tmp dir for the duration of test."""
    monkeypatch.setattr(settings, "photo_dir",tmp_path)
    # photos.py reads settings via `from .config import settings`, which shares
    # the same module-level instance — patching the attribute is enough.
    return tmp_path


def test_list_empty_dir(photo_dir: Path):
    r = client.get("/api/photos")
    assert r.status_code == 200
    assert r.json() == {"photos": []}


def test_list_filters_and_sorts(photo_dir: Path):
    (photo_dir / "a.jpg").write_bytes(b"x")
    (photo_dir / "B.PNG").write_bytes(b"x")
    (photo_dir / "note.txt").write_bytes(b"x")
    (photo_dir / ".hidden.jpg").write_bytes(b"x")
    (photo_dir / "pic.webp").write_bytes(b"x")

    r = client.get("/api/photos")
    assert r.status_code == 200
    body = r.json()
    # txt and hidden excluded; sorted case-insensitively.
    assert body == {"photos": ["a.jpg", "B.PNG", "pic.webp"]}


def test_list_missing_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    missing = tmp_path / "does-not-exist"
    monkeypatch.setattr(settings, "photo_dir",missing)

    r = client.get("/api/photos")
    assert r.status_code == 200
    body = r.json()
    assert body == {"photos": [], "error": "photo_dir_missing"}


def test_serve_returns_file(photo_dir: Path):
    (photo_dir / "tiny.png").write_bytes(PNG_MAGIC)

    r = client.get("/api/photos/tiny.png")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/png")
    assert r.content == PNG_MAGIC


def test_serve_rejects_traversal(photo_dir: Path):
    # Both forms must fail to escape PHOTO_DIR. Starlette decodes %2F before
    # routing, so encoded slashes hit a 404 from the router; literal slashes
    # likewise can't reach our handler. The critical guarantee is that no
    # traversal succeeds — neither returns 200.
    r1 = client.get("/api/photos/..%2Fetc%2Fpasswd")
    assert r1.status_code in (400, 404)
    assert r1.status_code != 200

    r2 = client.get("/api/photos/../etc/passwd")
    assert r2.status_code in (400, 404)
    assert r2.status_code != 200

    # Names that *do* reach our handler must be rejected at the handler with
    # 400 invalid_filename: "..", backslash, and NUL byte. Use percent-encoded
    # dots so the client doesn't collapse the segment before sending.
    r3 = client.get("/api/photos/%2E%2E")  # ".."
    assert r3.status_code == 400
    assert r3.json() == {"error": "invalid_filename"}

    r4 = client.get("/api/photos/foo%5Cbar.jpg")  # foo\bar.jpg
    assert r4.status_code == 400
    assert r4.json() == {"error": "invalid_filename"}

    r5 = client.get("/api/photos/bad%00name.jpg")  # embedded NUL
    assert r5.status_code == 400
    assert r5.json() == {"error": "invalid_filename"}


def test_serve_rejects_unsupported(photo_dir: Path):
    (photo_dir / "bad.exe").write_bytes(b"MZ")

    r = client.get("/api/photos/bad.exe")
    assert r.status_code == 415
    assert r.json() == {"error": "unsupported_type"}


def test_serve_404_when_missing(photo_dir: Path):
    r = client.get("/api/photos/nope.jpg")
    assert r.status_code == 404
    assert r.json() == {"error": "not_found"}


def test_serve_sets_cache_header(photo_dir: Path):
    (photo_dir / "tiny.png").write_bytes(PNG_MAGIC)

    r = client.get("/api/photos/tiny.png")
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "public, max-age=3600"
