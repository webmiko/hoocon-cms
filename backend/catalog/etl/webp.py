"""Convert raster images to WebP for catalog ProductImage.

Spec: docs/data-quality-etl.md — лёгкое сжатие без заметной потери качества.
quality=90 ≈ visually lossless для фото продукции; method=6 — лучший encode.

SVG и обязательные PNG (favicon / PWA / apple-touch) не конвертируем —
они лежат в ``frontend/public``, не в media ImageField.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from django.core.files.base import ContentFile
from PIL import Image

# Near-lossless for product photos (лёгкое сжатие, без видимой деградации).
DEFAULT_WEBP_QUALITY: int = 90
WEBP_METHOD: int = 6
# Cap long edge so CDN originals (often huge) stay light without crop.
MAX_EDGE_PX: int = 1600


def convert_bytes_to_webp(
    raw: bytes,
    *,
    quality: int = DEFAULT_WEBP_QUALITY,
    max_edge: int = MAX_EDGE_PX,
) -> bytes:
    """Decode image bytes and re-encode as WebP.

    Args:
        raw: Original JPEG/PNG/WebP bytes.
        quality: WebP quality 1–100 (default 90).
        max_edge: Max width/height; larger images are downscaled (LANCZOS).

    Returns:
        WebP bytes.

    Raises:
        OSError / PIL.UnidentifiedImageError: if bytes are not a valid image.
    """
    with Image.open(BytesIO(raw)) as img:
        img.load()
        # Preserve alpha when present; otherwise RGB for smaller files.
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            converted = img.convert("RGBA")
        else:
            converted = img.convert("RGB")

        w, h = converted.size
        longest = max(w, h)
        if longest > max_edge:
            scale = max_edge / float(longest)
            new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
            converted = converted.resize(new_size, Image.Resampling.LANCZOS)

        out = BytesIO()
        converted.save(
            out,
            format="WEBP",
            quality=quality,
            method=WEBP_METHOD,
        )
        return out.getvalue()


def webp_upload_basename(filename: str) -> str:
    """Force ``*.webp`` basename for ImageField ``upload_to`` paths."""
    stem = Path(filename or "image").stem.strip() or "image"
    return f"{stem}.webp"


def ensure_field_file_webp(
    field_file: Any,
    *,
    quality: int = DEFAULT_WEBP_QUALITY,
    max_edge: int = MAX_EDGE_PX,
) -> None:
    """Re-encode an ImageField value to WebP in place when needed.

    No-op when the field is empty or the current name already ends with
    ``.webp``. JPEG/PNG (and other rasters accepted by the validator) are
    converted before the model row is saved.

    Args:
        field_file: Django ``FieldFile`` / ``ImageFieldFile`` on the instance.
        quality: WebP quality 1–100.
        max_edge: Max long edge for downscale.

    Raises:
        OSError / PIL.UnidentifiedImageError: invalid image bytes.
    """
    if field_file is None or not getattr(field_file, "name", ""):
        return
    basename = Path(field_file.name).name
    if basename.lower().endswith(".webp"):
        return
    raw = field_file.read()
    if hasattr(field_file, "seek"):
        field_file.seek(0)
    webp = convert_bytes_to_webp(raw, quality=quality, max_edge=max_edge)
    field_file.save(
        webp_upload_basename(basename),
        ContentFile(webp),
        save=False,
    )
