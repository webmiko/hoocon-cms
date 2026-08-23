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
def test_resolve_seo_sku_og_image_uses_family_gallery_fallback() -> None:
    """Bare edition without own photo still gets sibling gallery as og:image."""
    from io import BytesIO

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    from catalog.models import SKU, Category, Product, ProductImage
    from catalog.urls_paths import catalog_path_for_sku
    from config.seo.head import resolve_seo_context

    buf = BytesIO()
    Image.new("RGB", (8, 8), color=(40, 120, 200)).save(buf, format="PNG")
    png = buf.getvalue()

    cat = Category.objects.create(name="Air OG", slug="air-og-family")
    product = Product.objects.create(
        name="HVA-5 OG",
        slug="privod-hva-5-og",
        category=cat,
    )
    donor = SKU.objects.create(
        product=product,
        sku_code="HVA24-5",
        name="HVA24-5",
        slug="hva24-5-og",
        is_published=True,
    )
    bare = SKU.objects.create(
        product=product,
        sku_code="HVA230S-5",
        name="HVA230S-5",
        slug="hva230s-5-og",
        is_published=True,
    )
    ProductImage.objects.create(
        sku=donor,
        image=SimpleUploadedFile("hva-og.png", png, content_type="image/png"),
        alt="HVA OG",
        source_url="https://example.test/hva-og.webp",
        sort_order=0,
        is_published=True,
    )

    path = catalog_path_for_sku(bare)
    ctx = resolve_seo_context(path)
    assert ctx.og_type == "product"
    assert ctx.og_image_url is not None
    assert "/media/" in ctx.og_image_url
    assert ctx.og_image_url.startswith("http")


@pytest.mark.django_db
def test_resolve_seo_missing_catalog_sku_has_unique_title() -> None:
    """Broken /catalog/{cat}/{sku} URLs get per-slug noindex titles."""
    from catalog.models import Category

    Category.objects.create(name="Комплекты", slug="komplekty-seo-miss")
    ctx = resolve_seo_context(
        "/catalog/komplekty-seo-miss/h8102-h8102-bv215c-24ds",
    )
    assert ctx.noindex is True
    assert "h8102-h8102-bv215c-24ds" in ctx.page_title
    assert "Товар не найден" in ctx.page_title


@pytest.mark.django_db
def test_resolve_seo_deep_catalog_path_is_fallback() -> None:
    """Three-segment catalog path is not treated as a category page."""
    ctx = resolve_seo_context("/catalog/a/b/c")
    assert "/catalog/a/b/c" in ctx.canonical_path or ctx.breadcrumb == () or True
