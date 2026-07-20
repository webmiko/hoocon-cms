"""Tests for root-relative media URL helpers."""

from __future__ import annotations

from catalog.media_urls import to_media_path


def test_to_media_path_strips_host() -> None:
    """Absolute media URLs collapse to ``/media/...`` paths."""
    assert to_media_path("http://127.0.0.1:8000/media/product_images/a.webp") == ("/media/product_images/a.webp")
    assert to_media_path("https://hoocon.ru/media/x.webp") == "/media/x.webp"


def test_to_media_path_keeps_relative() -> None:
    """Relative and root-relative forms stay path-only."""
    assert to_media_path("/media/a.webp") == "/media/a.webp"
    assert to_media_path("media/a.webp") == "/media/a.webp"
    assert to_media_path("") is None
    assert to_media_path(None) is None
