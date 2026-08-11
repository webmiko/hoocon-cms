"""Canonical news categories for /novosti filter chips.

Separate from ``catalog.Category`` (products only).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from content.models import NewsCategory

# Slug constants used by seed, migration, and article go-live.
CATEGORY_PRODUKTY = "produkty"
CATEGORY_STATI = "stati"
CATEGORY_MEROPRIYATIYA = "meropriyatiya"
CATEGORY_KOMPANIYA = "kompaniya"

DEFAULT_CATEGORIES: tuple[tuple[str, str, int], ...] = (
    (CATEGORY_PRODUKTY, "Продукты", 10),
    (CATEGORY_STATI, "Статьи", 20),
    (CATEGORY_MEROPRIYATIYA, "Мероприятия", 30),
    (CATEGORY_KOMPANIYA, "Компания", 40),
)

# Known news slugs → category slug (fallback = kompaniya).
NEWS_SLUG_TO_CATEGORY: dict[str, str] = {
    "launch-hva-5nm": CATEGORY_PRODUKTY,
    "launch-h8205-lav": CATEGORY_PRODUKTY,
    "launch-br-adapters": CATEGORY_PRODUKTY,
    "articles-podbor-i-sertifikaty": CATEGORY_STATI,
    "aquatherm-2025": CATEGORY_MEROPRIYATIYA,
    "mirklimata-2025": CATEGORY_MEROPRIYATIYA,
    "mir-klimata-2026-hoocon": CATEGORY_MEROPRIYATIYA,
    "hoocon-airvent-2026": CATEGORY_MEROPRIYATIYA,
    "partner-snizhenie-cen-022026": CATEGORY_KOMPANIYA,
}


def category_slug_for_news(news_slug: str) -> str:
    """Return category slug for a news item (go-live ``article-*`` → stati)."""
    if news_slug.startswith("article-"):
        return CATEGORY_STATI
    return NEWS_SLUG_TO_CATEGORY.get(news_slug, CATEGORY_KOMPANIYA)


def ensure_categories() -> dict[str, NewsCategory]:
    """Upsert default categories; return slug → instance map."""
    from content.models import NewsCategory

    out: dict[str, NewsCategory] = {}
    for slug, name, sort_order in DEFAULT_CATEGORIES:
        obj, _ = NewsCategory.objects.update_or_create(
            slug=slug,
            defaults={
                "name": name,
                "sort_order": sort_order,
                "is_published": True,
            },
        )
        out[slug] = obj
    return out


def assign_news_categories(*, only_missing: bool = False) -> int:
    """Assign categories to news rows from the known map / article- prefix.

    Args:
        only_missing: Skip rows that already have a category.

    Returns:
        Number of news rows updated.
    """
    from content.models import News

    cats = ensure_categories()
    updated = 0
    for news in News.objects.all().only("id", "slug", "category_id"):
        if only_missing and news.category_id is not None:
            continue
        target = cats.get(category_slug_for_news(news.slug))
        if target is None:
            continue
        if news.category_id == target.pk:
            continue
        news.category = target
        news.save(update_fields=["category", "updated_at"])
        updated += 1
    return updated
