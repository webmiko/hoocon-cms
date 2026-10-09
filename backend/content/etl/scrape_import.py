"""Shared image import for the Tilda article/news scrape commands.

Images are downloaded **before** the DB transaction (slow HTTP must not hold
row locks) and stored inside it once the row exists.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models.fields.files import FieldFile

from content.etl.tilda_articles import ScrapedArticle, collect_image_urls, download_bytes

logger = logging.getLogger(__name__)

FetchedImage = tuple[str, bytes]


def fetch_images(
    item: ScrapedArticle,
    *,
    to_webp: Callable[[bytes, str], bytes],
    warn: Callable[[str], object],
) -> list[FetchedImage]:
    """Download and encode cover + inline images; skip broken ones."""
    fetched: list[FetchedImage] = []
    for remote in collect_image_urls(item.body_html, item.cover_url):
        try:
            fetched.append((remote, to_webp(download_bytes(remote), remote)))
        except Exception as exc:  # noqa: BLE001 — one bad image must not abort
            logger.warning("image failed %s: %s", remote, exc)
            warn(f"    skip image {remote}: {exc}")
    return fetched


def store_images(
    *,
    cover: FieldFile,
    cover_url: str,
    folder: str,
    images: list[FetchedImage],
) -> dict[str, str]:
    """Save fetched images; return the remote→local URL map for the body."""
    mapping: dict[str, str] = {}
    for remote, webp in images:
        basename = safe_basename(remote)
        if remote == cover_url:
            cover.save(basename, ContentFile(webp), save=True)
            if cover:
                mapping[remote] = cover.url
            continue
        stored = default_storage.save(f"{folder}/{basename}", ContentFile(webp))
        mapping[remote] = default_storage.url(stored)
    return mapping


def safe_basename(url: str) -> str:
    """Derive a short WebP filename from a remote URL path."""
    name = Path(urlparse(url).path).name or "image.jpg"
    stem = Path(name).stem[:80] or "image"
    return f"{stem}.webp"
