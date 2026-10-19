import io
import uuid

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_SIDE = 1024
VISION_SIDE = 640

# Phones send HEIC; Pillow reads it only with pillow-heif, which is optional.
try:  # pragma: no cover - depends on optional package
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    pass


def normalize(raw: bytes, max_mb: int) -> tuple[bytes, bytes]:
    """Validate an upload; return (stored WEBP, small JPEG for the vision model).

    Re-encoding strips EXIF (GPS location from phone cameras) and fixes rotation.
    """
    if len(raw) > max_mb * 1024 * 1024:
        raise HTTPException(413, detail={"code": "image_too_large"})
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except (UnidentifiedImageError, OSError):
        raise HTTPException(415, detail={"code": "unsupported_image"})

    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "A" in img.getbands() else "RGB")

    stored = img.copy()
    stored.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    stored.save(out, "WEBP", quality=82, method=4)

    small = img.convert("RGB")
    small.thumbnail((VISION_SIDE, VISION_SIDE))
    vis = io.BytesIO()
    small.save(vis, "JPEG", quality=80)
    return out.getvalue(), vis.getvalue()


def new_key(user_id: uuid.UUID, ext: str = "webp") -> str:
    return f"u/{user_id.hex}/{uuid.uuid4().hex}.{ext}"

