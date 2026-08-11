"""News categories: assignment helpers, API filter/ordering, go-live."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from content.article_go_live import go_live_news_slug, publish_due_articles
from content.models import Article, News, NewsCategory
from content.news_categories import (
    CATEGORY_KOMPANIYA,
    CATEGORY_PRODUKTY,
    CATEGORY_STATI,
    assign_news_categories,
    category_slug_for_news,
    ensure_categories,
)


@pytest.mark.django_db
def test_ensure_and_assign_known_slugs() -> None:
    """Known news slugs map to the planned categories; unknown → kompaniya."""
    News.objects.create(
        title="HVA",
        slug="launch-hva-5nm",
        body="x",
        is_published=True,
    )
    News.objects.create(
        title="Other",
        slug="random-partner-note",
        body="y",
        is_published=True,
    )
    News.objects.create(
        title="Go live",
        slug="article-tipy-upravleniya-privodom",
        body="z",
        is_published=True,
    )

    assert category_slug_for_news("launch-hva-5nm") == CATEGORY_PRODUKTY
    assert category_slug_for_news("article-x") == CATEGORY_STATI
    assert category_slug_for_news("unknown") == CATEGORY_KOMPANIYA

    updated = assign_news_categories()
    assert updated >= 3
    by_slug = {n.slug: n.category.slug for n in News.objects.select_related("category")}
    assert by_slug["launch-hva-5nm"] == CATEGORY_PRODUKTY
    assert by_slug["random-partner-note"] == CATEGORY_KOMPANIYA
    assert by_slug["article-tipy-upravleniya-privodom"] == CATEGORY_STATI


@pytest.mark.django_db
def test_news_list_filter_and_ordering(client) -> None:
    """GET /api/content/news/ supports category + newest/oldest ordering."""
    News.objects.all().delete()
    cats = ensure_categories()
    older = timezone.now() - timedelta(days=10)
    newer = timezone.now() - timedelta(days=1)
    News.objects.create(
        title="Prod old",
        slug="prod-old",
        body="a",
        is_published=True,
        published_at=older,
        category=cats[CATEGORY_PRODUKTY],
    )
    News.objects.create(
        title="Prod new",
        slug="prod-new",
        body="b",
        is_published=True,
        published_at=newer,
        category=cats[CATEGORY_PRODUKTY],
    )
    News.objects.create(
        title="Company",
        slug="company-only",
        body="c",
        is_published=True,
        published_at=newer,
        category=cats[CATEGORY_KOMPANIYA],
    )

    filtered = client.get("/api/content/news/?category=produkty")
    assert filtered.status_code == 200
    slugs = [n["slug"] for n in filtered.json()["results"]]
    assert slugs == ["prod-new", "prod-old"]
    assert filtered.json()["results"][0]["category"] == {
        "slug": "produkty",
        "name": "Продукты",
    }

    oldest = client.get(
        "/api/content/news/?category=produkty&ordering=oldest",
    )
    assert [n["slug"] for n in oldest.json()["results"]] == [
        "prod-old",
        "prod-new",
    ]

    empty = client.get("/api/content/news/?category=stati")
    assert empty.json()["results"] == []


@pytest.mark.django_db
def test_news_categories_list(client) -> None:
    """GET /api/content/news-categories/ returns published rubrics in order."""
    ensure_categories()
    NewsCategory.objects.filter(slug=CATEGORY_KOMPANIYA).update(
        is_published=False,
    )
    response = client.get("/api/content/news-categories/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    slugs = [c["slug"] for c in data]
    assert slugs == ["produkty", "stati", "meropriyatiya"]
    assert "kompaniya" not in slugs


@pytest.mark.django_db
def test_go_live_assigns_stati_category() -> None:
    """Go-live news for article-* gets category stati."""
    slug = "analog-belimo-hoocon"
    when = timezone.now() - timedelta(hours=1)
    Article.objects.update_or_create(
        slug=slug,
        defaults={
            "title": "Belimo",
            "body": "<p>x</p>",
            "excerpt": "e",
            "is_published": True,
            "published_at": when,
        },
    )
    News.objects.filter(slug=go_live_news_slug(slug)).delete()
    with (
        patch(
            "sitesettings.models.SiteSettings.load",
            return_value=MagicMock(social_announce_on_publish=False),
        ),
    ):
        publish_due_articles(announce=True)

    news = News.objects.get(slug=go_live_news_slug(slug))
    assert news.category is not None
    assert news.category.slug == CATEGORY_STATI
