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
    trim_alpha: bool = False,
    flatten_white: bool = False,
) -> bytes:
    """Decode image bytes and re-encode as WebP.

    Args:
        raw: Original JPEG/PNG/WebP bytes.
        quality: WebP quality 1–100 (default 90).
        max_edge: Max width/height; larger images are downscaled (LANCZOS).
        trim_alpha: Crop transparent padding (diagrams with oversized canvas).
        flatten_white: Composite onto white RGB (paper diagrams / montages).

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

        if trim_alpha and converted.mode == "RGBA":
            converted = trim_rgba_padding(converted)

        if flatten_white:
            converted = flatten_rgba_on_white(converted)

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


def trim_rgba_padding(
    image: Image.Image,
    *,
    alpha_threshold: int = 16,
    pad_px: int = 8,
) -> Image.Image:
    """Crop near-transparent margins from an RGBA diagram.

    Args:
        image: Source RGBA (other modes returned unchanged).
        alpha_threshold: Pixels at or below this alpha are treated as empty.
        pad_px: Keep a small margin around remaining content.

    Returns:
        Cropped image, or the original when there is no usable content.
    """
    if image.mode != "RGBA":
        return image
    alpha = image.getchannel("A")
    mask = alpha.point(lambda value: 255 if value > alpha_threshold else 0)
    bbox = mask.getbbox()
    if bbox is None:
        return image
    left, top, right, bottom = bbox
    width, height = image.size
    left = max(0, left - pad_px)
    top = max(0, top - pad_px)
    right = min(width, right + pad_px)
    bottom = min(height, bottom + pad_px)
    if left == 0 and top == 0 and right == width and bottom == height:
        return image
    return image.crop((left, top, right, bottom))


def flatten_rgba_on_white(image: Image.Image) -> Image.Image:
    """Composite transparent pixels onto an opaque white background."""
    if image.mode != "RGBA":
        return image.convert("RGB") if image.mode != "RGB" else image
    background = Image.new("RGB", image.size, (255, 255, 255))
    background.paste(image, mask=image.getchannel("A"))
    return background


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
