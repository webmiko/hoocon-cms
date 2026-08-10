"""Root-relative media/static URL helpers for the public API.

SPA (Vite) and nginx both serve the site and proxy ``/media`` to Django.
Absolute URLs like ``http://127.0.0.1:8000/media/...`` break when the page
origin is ``localhost`` or the public host — use path-only URLs instead.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from rest_framework import serializers


def to_media_path(url: str | None) -> str | None:
    """Normalize a FileField/ImageField URL to a root-relative path.

    Args:
        url: Storage URL (relative or absolute).

    Returns:
        Path starting with ``/``, or None when empty.
    """
    if not url:
        return None
    text = str(url).strip()
    if not text:
        return None
    if text.startswith(("http://", "https://")):
        path = urlparse(text).path or "/"
        return path if path.startswith("/") else f"/{path}"
    return text if text.startswith("/") else f"/{text}"


class RelativeImageField(serializers.ImageField):
    """ImageField that never emits an absolute host — only ``/media/...``."""

    def to_representation(self, value: Any) -> str | None:
        """Return root-relative media path (ignore request host)."""
        if not value:
            return None
        try:
            raw = value.url
        except ValueError:
            return None
        return to_media_path(raw)
