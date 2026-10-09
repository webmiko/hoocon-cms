"""Private chat attachments: URLs and the content-type policy.

The MIME a browser or messenger reports is untrusted. Only raster images
verified by magic bytes are previewed inline; everything else is served
as a download, so an uploaded SVG/HTML never runs in the site origin.
"""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from supportchat.models import Message

INLINE_IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})
DOWNLOAD_TYPES = frozenset(
    {
        "application/pdf",
        "application/zip",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
        "text/plain",
    },
)
FALLBACK_TYPE = "application/octet-stream"
ATTACHMENT_CSP = "sandbox; default-src 'none'; img-src 'self'; style-src 'unsafe-inline'"


def sniff_image_type(head: bytes) -> str | None:
    """Raster image MIME from the first bytes, or None."""
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


def _read_head(upload: Any, size: int = 16) -> bytes:
    try:
        pos = upload.tell()
        upload.seek(0)
        head = upload.read(size)
        upload.seek(pos)
    except (AttributeError, OSError, ValueError):
        return b""
    return head if isinstance(head, bytes) else bytes(head or b"")


def normalize_mime(raw: str) -> str:
    return (raw or "").split(";")[0].strip().lower()


def safe_attachment_mime(upload: Any, claimed: str) -> str:
    """MIME to store for an upload: sniffed image, known document, or octet-stream."""
    image = sniff_image_type(_read_head(upload))
    if image:
        return image
    mime = normalize_mime(claimed)
    return mime if mime in DOWNLOAD_TYPES else FALLBACK_TYPE


def claims_image_without_raster_bytes(upload: Any, claimed: str) -> bool:
    """True for «image/*» uploads that are not JPEG/PNG/WebP/GIF (SVG, HTML…)."""
    return normalize_mime(claimed).startswith("image/") and sniff_image_type(_read_head(upload)) is None


def is_inline_image(mime: str) -> bool:
    return normalize_mime(mime) in INLINE_IMAGE_TYPES


def served_content_type(mime: str) -> str:
    normalized = normalize_mime(mime)
    if normalized in INLINE_IMAGE_TYPES or normalized in DOWNLOAD_TYPES:
        return normalized
    return FALLBACK_TYPE


def message_attachment_url(message: Message) -> str:
    """Relative API path that checks widget session or staff perm.

    Args:
        message: persisted Message with an attachment.

    Returns:
        URL path, or empty string when there is no file.
    """
    if not message.pk or not message.attachment:
        return ""
    return reverse("support-message-attachment", args=[message.pk])
