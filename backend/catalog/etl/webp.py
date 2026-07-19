"""Convert raster images to WebP for catalog ProductImage.

Spec: docs/data-quality-etl.md — лёгкое сжатие без заметной потери качества.
quality=90 ≈ visually lossless для фото продукции; method=6 — лучший encode.
"""

from __future__ import annotations

from io import BytesIO

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
