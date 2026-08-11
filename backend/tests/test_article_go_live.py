"""Tests for scheduled article go-live (news + social announce)."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from content.article_go_live import (
    AUTO_GO_LIVE_NEWS_SLUGS,
    go_live_news_slug,
    publish_due_articles,
)
from content.models import Article, News


def _due_article(slug: str, *, title: str, past: bool = True) -> Article:
    """Upsert a guide article with due or future published_at."""
    when = timezone.now() + (timedelta(hours=-1) if past else timedelta(days=2))
    article, _ = Article.objects.update_or_create(
        slug=slug,
        defaults={
            "title": title,
            "body": "<p>x</p>",
            "excerpt": "Краткий анонс.",
            "is_published": True,
            "published_at": when,
        },
    )
    News.objects.filter(slug=go_live_news_slug(slug)).delete()
    return article


@pytest.mark.django_db
def test_go_live_creates_news_and_announces() -> None:
    """Due AUTO_GO_LIVE article → news + announce_content once."""
    slug = "analog-belimo-hoocon"
    assert slug in AUTO_GO_LIVE_NEWS_SLUGS
    _due_article(slug, title="Замена Belimo на Hoocon")
    fake_post = MagicMock()
    with (
        patch(
            "sitesettings.models.SiteSettings.load",
            return_value=MagicMock(social_announce_on_publish=True),
        ),
        patch(
            "social.services.announce_content",
            return_value=[fake_post],
        ) as announce,
    ):
        results = publish_due_articles(announce=True)

    hit = [r for r in results if r.article_slug == slug]
    assert len(hit) == 1
    assert hit[0].news_created is True
    assert hit[0].announced == 1
    news = News.objects.get(slug=go_live_news_slug(slug))
    assert news.is_published is True
    assert "/statyi/analog-belimo-hoocon" in news.body
    announce.assert_called_once()
    assert announce.call_args.args[0].pk == news.pk


@pytest.mark.django_db
def test_go_live_idempotent_second_run() -> None:
    """Second run does not recreate news."""
    slug = "tipy-upravleniya-privodom"
    _due_article(slug, title="Типы управления")
    with (
        patch(
            "sitesettings.models.SiteSettings.load",
            return_value=MagicMock(social_announce_on_publish=True),
        ),
        patch("social.services.announce_content", return_value=[MagicMock()]),
    ):
        first = publish_due_articles(announce=True)
    with (
        patch(
            "sitesettings.models.SiteSettings.load",
            return_value=MagicMock(social_announce_on_publish=True),
        ),
        patch("social.services.announce_content", return_value=[]) as announce,
    ):
        second = publish_due_articles(announce=True)

    first_hit = [r for r in first if r.article_slug == slug]
    assert first_hit and first_hit[0].news_created is True
    assert all(not r.news_created for r in second if r.article_slug == slug)
    assert News.objects.filter(slug=go_live_news_slug(slug)).count() == 1
    announce.assert_called()


@pytest.mark.django_db
def test_go_live_skips_future_published_at() -> None:
    """Future go-live date is not processed yet."""
    slug = "analog-belimo-hoocon"
    _due_article(slug, title="Analog future", past=False)
    results = publish_due_articles(announce=False)
    assert all(r.article_slug != slug for r in results)
    assert not News.objects.filter(slug=go_live_news_slug(slug)).exists()


@pytest.mark.django_db
def test_go_live_skips_when_announce_flag_off() -> None:
    """News is created even if social flag is off; announce count is 0."""
    slug = "pitanie-24-ili-230-v"
    _due_article(slug, title="Питание")
    with (
        patch(
            "sitesettings.models.SiteSettings.load",
            return_value=MagicMock(social_announce_on_publish=False),
        ),
        patch("social.services.announce_content") as announce,
    ):
        results = publish_due_articles(announce=True)

    hit = [r for r in results if r.article_slug == slug]
    assert len(hit) == 1
    assert hit[0].news_created is True
    assert hit[0].announced == 0
    announce.assert_not_called()
