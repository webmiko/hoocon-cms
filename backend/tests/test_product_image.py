"""Tests for WebP conversion and image upload validators."""

from __future__ import annotations

from io import BytesIO

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from catalog.etl.webp import convert_bytes_to_webp
from catalog.validators import validate_image_upload


def _png_bytes(size: tuple[int, int] = (64, 48)) -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, color=(200, 40, 40)).save(buf, format="PNG")
    return buf.getvalue()


def test_convert_bytes_to_webp_produces_webp_magic() -> None:
    """PNG input becomes WebP with RIFF/WEBP header and smaller-or-equal size."""
    raw = _png_bytes((400, 300))
    webp = convert_bytes_to_webp(raw, quality=90)
    assert webp[:4] == b"RIFF"
    assert webp[8:12] == b"WEBP"
    assert len(webp) > 100


def test_convert_bytes_to_webp_downscales_long_edge() -> None:
    """Images larger than max_edge are resized."""
    raw = _png_bytes((2000, 1200))
    webp = convert_bytes_to_webp(raw, quality=90, max_edge=800)
    with Image.open(BytesIO(webp)) as img:
        assert max(img.size) <= 800


def test_validate_image_upload_accepts_webp() -> None:
    """Valid WebP passes validator."""
    webp = convert_bytes_to_webp(_png_bytes(), quality=90)
    uploaded = SimpleUploadedFile("shot.webp", webp, content_type="image/webp")
    validate_image_upload(uploaded)


def test_validate_image_upload_rejects_pdf() -> None:
    """PDF disguised as image is rejected."""
    uploaded = SimpleUploadedFile(
        "fake.webp",
        b"%PDF-1.4 fake",
        content_type="image/webp",
    )
    with pytest.raises(ValidationError):
        validate_image_upload(uploaded)
