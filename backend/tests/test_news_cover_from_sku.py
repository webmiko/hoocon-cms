"""Tests for attaching a catalog SKU photo as news cover."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from django.core.files.base import ContentFile
from django.utils import timezone
from PIL import Image

from catalog.models import SKU, Category, Product, ProductImage
from content.models import News
from content.news_cover_from_sku import attach_sku_cover_to_news


def _tiny_webp() -> bytes:
    buf = BytesIO()
    Image.new("RGB", (8, 8), color=(40, 80, 120)).save(buf, format="WEBP")
    return buf.getvalue()


@pytest.mark.django_db
def test_attach_sku_cover_to_news_copies_primary_image(
    tmp_path: Path,
    settings,
) -> None:
    """Empty news cover receives the primary published ProductImage bytes."""
    settings.MEDIA_ROOT = tmp_path
    category = Category.objects.create(name="Cat", slug="cat-cover")
    product = Product.objects.create(
        name="HVA-5",
        slug="privod-vozdushniy-hva-5nm-cover",
        category=category,
    )
    sku = SKU.objects.create(
        product=product,
        name="HVA230-5",
        slug="privod-hva230-5-cover",
        sku_code="HVA230-5",
        is_published=True,
    )
    ProductImage.objects.create(
        sku=sku,
        image=ContentFile(_tiny_webp(), name="hva230-5-0.webp"),
        alt="HVA230-5",
        sort_order=0,
        is_published=True,
    )
    news = News.objects.create(
        slug="launch-hva-5nm",
        title="В каталоге: HVA-5NM",
        body="<p>5&nbsp;Н·м</p>",
        is_published=True,
        published_at=timezone.now(),
    )

    assert attach_sku_cover_to_news() is True
    news.refresh_from_db()
    assert news.cover
    assert news.cover.size > 0
    assert Path(news.cover.name).suffix == ".webp"

    assert attach_sku_cover_to_news() is False  # already set


@pytest.mark.django_db
def test_attach_sku_cover_skips_when_sku_missing(tmp_path: Path, settings) -> None:
    """Missing SKU returns False without raising."""
    settings.MEDIA_ROOT = tmp_path
    News.objects.create(
        slug="launch-hva-5nm",
        title="В каталоге: HVA-5NM",
        body="<p>body</p>",
        is_published=True,
        published_at=timezone.now(),
    )
    assert attach_sku_cover_to_news() is False


@pytest.mark.django_db
def test_attach_h8205_cover_by_sku_code(tmp_path: Path, settings) -> None:
    """H8205 news can take cover from a named LAV edition SKU."""
    settings.MEDIA_ROOT = tmp_path
    category = Category.objects.create(name="Kits", slug="komplekty-cover")
    product = Product.objects.create(
        name="H8205-LAV232",
        slug="h8205-lav232-cover",
        category=category,
    )
    sku = SKU.objects.create(
        product=product,
        name="H8205-LAV232-24A",
        slug="h8205-lav232-24a-cover",
        sku_code="H8205-LAV232-24A",
        is_published=True,
    )
    ProductImage.objects.create(
        sku=sku,
        image=ContentFile(_tiny_webp(), name="h8205-lav232-photo.webp"),
        alt="H8205-LAV232",
        sort_order=0,
        is_published=True,
    )
    news = News.objects.create(
        slug="launch-h8205-lav-test",
        title="Доступен заказ: H8205-LAV",
        body="<p>LAV</p>",
        is_published=True,
        published_at=timezone.now(),
    )

    assert attach_sku_cover_to_news(
        news_slug="launch-h8205-lav-test",
        sku_code="H8205-LAV232-24A",
    )
    news.refresh_from_db()
    assert news.cover
    assert "h8205" in news.cover.name.lower()
