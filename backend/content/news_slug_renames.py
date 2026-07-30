"""Canonical news slug renames (Tilda ID prefixes → readable ЧПУ).

Spec: docs/seo-url-migration.md — keep old path as 301, new slug as canonical.
Also relocates ``news_covers/<old-slug>/…`` files to ``news_covers/<new>/…``
so media folder names match the public URL (``/novosti/<slug>``).
"""

from __future__ import annotations

import logging
from pathlib import PurePosixPath

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from content.models import News
from redirects.models import Redirect
from redirects.pathutils import normalize_path

logger = logging.getLogger(__name__)

# old slug (Tilda / scrape) → canonical public slug
NEWS_SLUG_RENAMES: dict[str, str] = {
    "4s6cri8961-aquatherm-2025": "aquatherm-2025",
}


def canonical_news_slug(slug: str) -> str:
    """Map a scraped/Tilda slug to the public ЧПУ when a rename exists."""
    raw = (slug or "").strip()
    return NEWS_SLUG_RENAMES.get(raw, raw)


def relocate_news_cover_to_slug(news: News) -> str | None:
    """Move cover file into ``news_covers/<news.slug>/`` when folder drifts.

    Args:
        news: News with optional ``cover`` FileField.

    Returns:
        New relative media path, or ``None`` when no move was needed / possible.
    """
    if not news.cover or not news.slug:
        return None
    old_name = (news.cover.name or "").replace("\\", "/")
    parts = PurePosixPath(old_name).parts
    if len(parts) < 3 or parts[0] != "news_covers":
        return None
    folder = parts[1]
    if folder == news.slug:
        return None
    basename = parts[-1]
    new_name = f"news_covers/{news.slug}/{basename}"
    if not default_storage.exists(old_name):
        logger.warning(
            "news_cover_missing slug=%s path=%s",
            news.slug,
            old_name,
        )
        return None
    if default_storage.exists(new_name):
        news.cover.name = new_name
        news.save(update_fields=["cover", "updated_at"])
        try:
            default_storage.delete(old_name)
        except OSError:
            logger.warning("news_cover_old_delete_failed path=%s", old_name)
        return new_name

    with default_storage.open(old_name, "rb") as src:
        default_storage.save(new_name, ContentFile(src.read()))
    news.cover.name = new_name
    news.save(update_fields=["cover", "updated_at"])
    try:
        default_storage.delete(old_name)
    except OSError:
        logger.warning("news_cover_old_delete_failed path=%s", old_name)
    logger.info(
        "news_cover_relocated slug=%s from=%s to=%s",
        news.slug,
        old_name,
        new_name,
    )
    return new_name


def relocate_all_news_covers() -> list[tuple[str, str]]:
    """Relocate every news cover whose folder ≠ current slug.

    Returns:
        List of ``(old_path, new_path)`` moves.
    """
    moved: list[tuple[str, str]] = []
    for news in News.objects.exclude(cover="").iterator():
        old = news.cover.name
        new = relocate_news_cover_to_slug(news)
        if new:
            moved.append((old, new))
    return moved


def apply_news_slug_renames() -> list[tuple[str, str]]:
    """Rename news and upsert 301 ``/novosti/{old}`` + ``/news/{old}`` → canonical.

    If both old and new News rows exist, keep the new row and delete the old
    one. If only old exists, rename in place. After slug fixes, relocate cover
    files into ``news_covers/<slug>/``.

    Returns:
        List of ``(old_slug, new_slug)`` pairs that were ensured.
    """
    applied: list[tuple[str, str]] = []
    for old_slug, new_slug in NEWS_SLUG_RENAMES.items():
        old_news = News.objects.filter(slug=old_slug).first()
        new_news = News.objects.filter(slug=new_slug).first()
        if old_news is not None and new_news is not None:
            if old_news.pk != new_news.pk:
                old_news.delete()
        elif old_news is not None:
            old_news.slug = new_slug
            old_news.save(update_fields=["slug", "updated_at"])

        Redirect.objects.update_or_create(
            from_path=normalize_path(f"/novosti/{old_slug}"),
            defaults={
                "to_path": normalize_path(f"/novosti/{new_slug}"),
                "status_code": Redirect.HTTP_MOVED_PERMANENTLY,
                "is_active": True,
            },
        )
        Redirect.objects.update_or_create(
            from_path=normalize_path(f"/news/{old_slug}"),
            defaults={
                "to_path": normalize_path(f"/novosti/{new_slug}"),
                "status_code": Redirect.HTTP_MOVED_PERMANENTLY,
                "is_active": True,
            },
        )
        applied.append((old_slug, new_slug))

    relocate_all_news_covers()
    return applied
