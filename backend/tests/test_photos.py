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


# --- Downscaling -----------------------------------------------------------

from io import BytesIO  # noqa: E402

from PIL import Image, ImageCms  # noqa: E402

from app import photos as photos_mod  # noqa: E402


@pytest.fixture
def resize_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cache = tmp_path / "photo-cache"
    monkeypatch.setattr(photos_mod, "_RESIZE_CACHE_DIR", cache)
    return cache


def _jpeg(size: tuple[int, int], **save_kwargs) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, (200, 80, 40)).save(buf, format="JPEG", **save_kwargs)
    return buf.getvalue()


def test_large_photo_downscaled_to_requested_size(photo_dir: Path, resize_cache: Path):
    (photo_dir / "big.jpg").write_bytes(_jpeg((4000, 3000)))

    r = client.get("/api/photos/big.jpg?max=1280")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    with Image.open(BytesIO(r.content)) as img:
        assert max(img.size) == 1280
        assert img.size == (1280, 960)
    assert len(list(resize_cache.glob("*.jpg"))) == 1

    # A different size is a separate cached variant; the default is 1920.
    r = client.get("/api/photos/big.jpg")
    with Image.open(BytesIO(r.content)) as img:
        assert max(img.size) == 1920
    assert len(list(resize_cache.glob("*.jpg"))) == 2


def test_small_photo_served_unchanged(photo_dir: Path, resize_cache: Path):
    original = _jpeg((800, 600))
    (photo_dir / "small.jpg").write_bytes(original)

    r = client.get("/api/photos/small.jpg?max=1280")
    assert r.content == original
    assert not resize_cache.exists()


def test_exif_orientation_applied(photo_dir: Path, resize_cache: Path):
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90° CW on display
    (photo_dir / "rotated.jpg").write_bytes(_jpeg((4000, 3000), exif=exif.tobytes()))

    r = client.get("/api/photos/rotated.jpg?max=1024")
    with Image.open(BytesIO(r.content)) as img:
        assert img.size == (768, 1024)


def test_icc_tagged_photo_converted_to_srgb(photo_dir: Path, resize_cache: Path):
    srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    (photo_dir / "tagged.jpg").write_bytes(_jpeg((3000, 2000), icc_profile=srgb))

    r = client.get("/api/photos/tagged.jpg?max=640")
    with Image.open(BytesIO(r.content)) as img:
        assert img.mode == "RGB"
        assert img.size == (640, 427)
        # Output is plain sRGB: the source profile isn't carried along.
        assert "icc_profile" not in img.info


@pytest.mark.parametrize(
    ("requested", "expected"),
    [(None, 1920), (1, 64), (1000, 1024), (1280, 1280), (99_999, 3840)],
)
def test_requested_dim_clamped_and_rounded(requested, expected):
    assert photos_mod._requested_dim(requested) == expected


def test_cache_not_in_ram_backed_tmp():
    import tempfile

    assert not str(photos_mod._RESIZE_CACHE_DIR).startswith(tempfile.gettempdir())


def test_prune_removes_oldest_beyond_cap(
    resize_cache: Path, monkeypatch: pytest.MonkeyPatch
):
    import os

    resize_cache.mkdir()
    for i in range(5):
        f = resize_cache / f"{i}.jpg"
        f.write_bytes(b"x" * 100)
        os.utime(f, (1_000 + i, 1_000 + i))
    monkeypatch.setattr(photos_mod, "_CACHE_MAX_BYTES", 250)

    photos_mod._prune_cache()

    assert sorted(p.name for p in resize_cache.glob("*.jpg")) == ["3.jpg", "4.jpg"]
