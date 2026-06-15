"""Photos router — list and serve images from PHOTO_DIR.

Implements:
    GET /api/photos             — JSON listing of usable image filenames.
    GET /api/photos/{filename}  — streams the file with proper media type and
                                  Cache-Control. Hardened against path
                                  traversal.

HEIC (`.heic`/`.heif`) support is opt-in: set ``settings.photo_heic = True`` and
``pip install pillow-heif`` separately. ``pillow-heif`` is intentionally NOT in
requirements.txt — it's optional and the user installs it manually.

Images are downscaled (and cached on disk) before serving: PHOTO_DIR often
holds full-resolution phone-camera originals, and serving those straight to
the kiosk browser overwhelms the Pi's GPU texture/decode pipeline (seen in
practice as the whole display going blank once the slideshow hits a large
photo). The resize is best-effort — if Pillow can't open a file for any
reason, the original is streamed unchanged.
"""
from __future__ import annotations

import hashlib
import mimetypes
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from . import config_store
from .config import settings

router = APIRouter(prefix="/api", tags=["photos"])

# Always-on supported extensions (case-insensitive).
_BASE_EXTS: frozenset[str] = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif"})
_HEIC_EXTS: frozenset[str] = frozenset({".heic", ".heif"})

_CACHE_HEADER = "public, max-age=3600"

# Long edge a resized photo is capped to. The photos panel is at most ~2/3 of
# a 1080p kiosk display, so this comfortably covers it with headroom while
# staying well under typical embedded-GPU max texture sizes (e.g. the Pi 3's
# VideoCore IV).
_MAX_DIM = 1920
_RESIZE_CACHE_DIR = Path(tempfile.gettempdir()) / "home-dashboard-photo-cache"


def _photo_dir() -> Path:
    """Resolve the photo directory from the live runtime config."""
    return Path(config_store.get_runtime_config()["photos"]["directory"])


def _heic_available() -> bool:
    """True iff HEIC is opt-in *and* pillow-heif is importable."""
    if not settings.photo_heic:
        return False
    try:
        import pillow_heif  # noqa: F401
    except ImportError:
        return False
    return True


def _supported_extensions() -> frozenset[str]:
    if _heic_available():
        return _BASE_EXTS | _HEIC_EXTS
    return _BASE_EXTS


def _is_safe_filename(filename: str) -> bool:
    """Reject any filename that could escape PHOTO_DIR."""
    if not filename:
        return False
    if "\x00" in filename:
        return False
    if "/" in filename or "\\" in filename:
        return False
    if ".." in filename:
        return False
    # Defense-in-depth: pathlib must agree the name has no directory parts.
    if Path(filename).name != filename:
        return False
    return True


@router.get("/photos")
async def list_photos() -> dict:
    photo_dir: Path = _photo_dir()
    if not photo_dir.exists() or not photo_dir.is_dir():
        return {"photos": [], "error": "photo_dir_missing"}

    exts = _supported_extensions()
    names: list[str] = []
    for entry in photo_dir.iterdir():
        if not entry.is_file():
            continue
        if entry.name.startswith("."):
            continue
        if entry.suffix.lower() not in exts:
            continue
        names.append(entry.name)

    names.sort(key=str.lower)
    return {"photos": names}


def _resize_cache_key(target: Path) -> Path:
    stat = target.stat()
    key = f"{target}|{stat.st_mtime_ns}|{stat.st_size}|{_MAX_DIM}"
    digest = hashlib.sha1(key.encode()).hexdigest()
    return _RESIZE_CACHE_DIR / f"{digest}.jpg"


def _serve_path(target: Path, ext: str) -> tuple[Path, str]:
    """Pick what to actually stream for `target`: a cached downscaled JPEG
    when the original is larger than _MAX_DIM, otherwise the original file
    unchanged. Resizing is best-effort — GIFs are left alone (to preserve
    animation) and any Pillow failure falls back to the original untouched,
    so a corrupt/unusual file still serves rather than 500ing."""
    media_type, _ = mimetypes.guess_type(str(target))
    if media_type is None:
        media_type = "image/heic" if ext in _HEIC_EXTS else "application/octet-stream"
    original = (target, media_type)

    if ext == ".gif":
        return original

    try:
        from PIL import Image, ImageOps
    except ImportError:
        return original

    try:
        cache_path = _resize_cache_key(target)
    except OSError:
        return original
    if cache_path.is_file():
        return cache_path, "image/jpeg"

    try:
        with Image.open(target) as img:
            if max(img.size) <= _MAX_DIM:
                return original
            img = ImageOps.exif_transpose(img)
            img.thumbnail((_MAX_DIM, _MAX_DIM))
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            _RESIZE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            tmp_path = cache_path.with_suffix(".tmp")
            img.save(tmp_path, format="JPEG", quality=85)
            tmp_path.replace(cache_path)
    except Exception:
        return original

    return cache_path, "image/jpeg"


@router.get("/photos/{filename}")
async def get_photo(filename: str):
    if not _is_safe_filename(filename):
        return JSONResponse(
            status_code=400, content={"error": "invalid_filename"}
        )

    ext = Path(filename).suffix.lower()
    if ext not in _supported_extensions():
        return JSONResponse(
            status_code=415, content={"error": "unsupported_type"}
        )

    photo_dir: Path = _photo_dir()
    if not photo_dir.exists() or not photo_dir.is_dir():
        return JSONResponse(status_code=404, content={"error": "not_found"})

    base = photo_dir.resolve()
    target = (photo_dir / filename).resolve()

    # Defense-in-depth: ensure resolved path is inside PHOTO_DIR.
    try:
        target.relative_to(base)
    except ValueError:
        return JSONResponse(
            status_code=400, content={"error": "invalid_filename"}
        )

    if not target.is_file():
        return JSONResponse(status_code=404, content={"error": "not_found"})

    serve_path, media_type = _serve_path(target, ext)

    return FileResponse(
        path=str(serve_path),
        media_type=media_type,
        headers={"Cache-Control": _CACHE_HEADER},
    )
