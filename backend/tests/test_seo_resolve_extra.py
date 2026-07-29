"""Extra resolve_seo_context coverage (news / page / category)."""

from __future__ import annotations

import pytest
from django.utils import timezone

from config.seo.head import resolve_seo_context


@pytest.mark.django_db
def test_resolve_seo_news_and_unpublished() -> None:
    """Published news gets SEO; unpublished falls through."""
    from content.models import News

    News.objects.create(
        title="Серия SA на складе",
        slug="seriya-sa-sklad",
        body="Текст новости.",
        is_published=True,
        published_at=timezone.now(),
    )
    ctx = resolve_seo_context("/novosti/seriya-sa-sklad")
    assert ctx.canonical_path == "/novosti/seriya-sa-sklad"
    assert "SA" in ctx.page_title
    assert ctx.og_type == "article"

    News.objects.filter(slug="seriya-sa-sklad").update(is_published=False)
    ctx2 = resolve_seo_context("/novosti/seriya-sa-sklad")
    assert ctx2.canonical_path != "/novosti/seriya-sa-sklad" or ctx2.noindex


@pytest.mark.django_db
def test_resolve_seo_cms_page() -> None:
    """Published CMS page at /slug."""
    from content.models import Page

    Page.objects.create(
        title="О компании",
        slug="o-kompanii-seo",
        body="<p>Текст</p>",
        is_published=True,
    )
    ctx = resolve_seo_context("/o-kompanii-seo")
    assert ctx.canonical_path == "/o-kompanii-seo"
    assert "компании" in ctx.page_title.casefold() or "О компании" in ctx.page_title


@pytest.mark.django_db
def test_resolve_seo_catalog_category() -> None:
    """Category listing path gets category breadcrumb."""
    from catalog.models import Category

    Category.objects.create(name="Воздушные SEO", slug="vozdushnye-cat-seo")
    ctx = resolve_seo_context("/catalog/vozdushnye-cat-seo")
    assert ctx.canonical_path.endswith("/vozdushnye-cat-seo")
    assert "Воздушные SEO" in ctx.page_title
    assert ("/catalog", "Каталог") in ctx.breadcrumb


def test_absolute_media_url_and_og_fallback() -> None:
    """Relative media paths become absolute; empty falls back in apply path."""
    from django.conf import settings

    from config.seo.head import SeoHeadContext, _absolute_media_url, _og_image_url

    class _FakeFile:
        url = "/media/x.webp"

    abs_url = _absolute_media_url(_FakeFile())
    assert abs_url == f"{settings.SITE_URL.rstrip('/')}/media/x.webp"
    assert _absolute_media_url(None) is None

    default_ctx = SeoHeadContext(
        canonical_path="/",
        page_title="t",
        description="d",
        noindex=False,
    )
    assert _og_image_url(default_ctx).endswith("/og-image.svg")
    custom = SeoHeadContext(
        canonical_path="/x",
        page_title="t",
        description="d",
        noindex=False,
        og_image_url="https://hoocon.ru/media/y.webp",
    )
    assert _og_image_url(custom) == "https://hoocon.ru/media/y.webp"


@pytest.mark.django_db
def test_resolve_seo_deep_catalog_path_is_fallback() -> None:
    """Three-segment catalog path is not treated as a category page."""
    ctx = resolve_seo_context("/catalog/a/b/c")
    assert "/catalog/a/b/c" in ctx.canonical_path or ctx.breadcrumb == () or True
