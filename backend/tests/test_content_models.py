"""Tests for content app models: Page / Article / News (TDD).

Spec: ПЛАН §6 Iter 3 — content app: Page / Article / News со slug;
docs/readiness-backend-ux.md §2.2 (content | Page, Article, News | E-E-A-T);
docs/seo-url-migration.md (slug = canonical path, напр. /company, /statyi).
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError

# ── Page ────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_create_page_with_slug() -> None:
    """Can create a Page with a canonical slug."""
    from content.models import Page

    page = Page.objects.create(
        title="О компании",
        slug="o-kompanii",
        body="<p>Hoocon — производитель электроприводов ОВК.</p>",
    )
    assert page.pk is not None
    assert page.slug == "o-kompanii"
    assert page.is_published is True


@pytest.mark.django_db
def test_page_slug_unique() -> None:
    """Duplicate slug raises IntegrityError."""
    from content.models import Page

    Page.objects.create(title="A", slug="dup", body="")
    with pytest.raises(IntegrityError):
        Page.objects.create(title="B", slug="dup", body="")


@pytest.mark.django_db
def test_page_str() -> None:
    """__str__ returns the title."""
    from content.models import Page

    page = Page.objects.create(title="Контакты", slug="kontakty", body="")
    assert str(page) == "Контакты"


@pytest.mark.django_db
def test_page_default_is_published_true() -> None:
    """New Page is published by default (canonical content)."""
    from content.models import Page

    page = Page.objects.create(title="Доставка", slug="dostavka", body="")
    assert page.is_published is True


@pytest.mark.django_db
def test_page_body_optional() -> None:
    """Body can be empty (placeholder page)."""
    from content.models import Page

    page = Page.objects.create(title="Empty", slug="empty", body="")
    assert page.body == ""


# ── Article ──────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_create_article_with_slug() -> None:
    """Can create an Article with title, slug, body."""
    from content.models import Article

    art = Article.objects.create(
        title="Как подобрать привод",
        slug="kak-podobrat-privod",
        body="<p>Гайд по подбору.</p>",
    )
    assert art.pk is not None
    assert art.slug == "kak-podobrat-privod"
    assert art.is_published is True


@pytest.mark.django_db
def test_article_slug_unique() -> None:
    """Duplicate article slug raises IntegrityError."""
    from content.models import Article

    Article.objects.create(title="A", slug="dup-art", body="")
    with pytest.raises(IntegrityError):
        Article.objects.create(title="B", slug="dup-art", body="")


@pytest.mark.django_db
def test_article_str() -> None:
    """__str__ returns the title."""
    from content.models import Article

    art = Article.objects.create(title="Гайд 1", slug="gayd-1", body="")
    assert str(art) == "Гайд 1"


@pytest.mark.django_db
def test_article_published_at_optional() -> None:
    """published_at is optional (drafts have no publish date)."""
    from content.models import Article

    art = Article.objects.create(title="Draft", slug="draft", body="")
    assert art.published_at is None


# ── News ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_create_news_with_slug() -> None:
    """Can create a News item with title, slug, body."""
    from content.models import News

    n = News.objects.create(
        title="Запустили новый привод",
        slug="zapustili-novyy-privod",
        body="<p>Анонс.</p>",
    )
    assert n.pk is not None
    assert n.slug == "zapustili-novyy-privod"
    assert n.is_published is True


@pytest.mark.django_db
def test_news_slug_unique() -> None:
    """Duplicate news slug raises IntegrityError."""
    from content.models import News

    News.objects.create(title="A", slug="dup-news", body="")
    with pytest.raises(IntegrityError):
        News.objects.create(title="B", slug="dup-news", body="")


@pytest.mark.django_db
def test_news_str() -> None:
    """__str__ returns the title."""
    from content.models import News

    n = News.objects.create(title="Анонс 1", slug="anons-1", body="")
    assert str(n) == "Анонс 1"


@pytest.mark.django_db
def test_news_published_at_optional() -> None:
    """published_at is optional (drafts have no publish date)."""
    from content.models import News

    n = News.objects.create(title="Draft", slug="news-draft", body="")
    assert n.published_at is None


# ── Slug uniqueness across models (canonical path collisions) ────────


@pytest.mark.django_db
def test_page_article_news_can_share_slug_namespace() -> None:
    """Each model has its own slug table — same slug across models is OK.

    Note: if the project later decides that all content shares one URL
    namespace (e.g. /p/<slug>), this test must be revisited. For now,
    each model keeps its own unique slug (canonical paths differ:
    /<slug> for Page, /statyi/<slug> for Article, /novosti/<slug> for News).
    """
    from content.models import Article, News, Page

    Page.objects.create(title="P", slug="shared", body="")
    Article.objects.create(title="A", slug="shared", body="")
    News.objects.create(title="N", slug="shared", body="")
    assert Page.objects.filter(slug="shared").count() == 1
    assert Article.objects.filter(slug="shared").count() == 1
    assert News.objects.filter(slug="shared").count() == 1
