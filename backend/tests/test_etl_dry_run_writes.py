"""ETL ``dry_run`` must not write; gallery refresh keeps editor-hidden photos (M44)."""

from __future__ import annotations

import pytest

from catalog.etl.manual_pdfs import ensure_dafu_spring_category
from catalog.etl.series_copy_ball_valves import attach_gallery_images
from catalog.models import SKU, Category, Product, ProductImage

pytestmark = pytest.mark.django_db

_URL = "https://static.tildacdn.com/bv/photo-1.jpg"


@pytest.fixture
def sku() -> SKU:
    category = Category.objects.create(name="Краны", slug="krany-dry")
    product = Product.objects.create(category=category, name="BV", slug="bv-dry")
    return SKU.objects.create(product=product, sku_code="BV-DRY", name="BV", slug="bv-dry")


def test_dafu_category_dry_run_does_not_create_category() -> None:
    other = Category.objects.create(name="Прочее", slug="prochee")
    Product.objects.create(category=other, name="DAFU", slug="dafu-24")
    before = Category.objects.count()
    result = ensure_dafu_spring_category(dry_run=True)
    assert Category.objects.count() == before
    assert result["moved"] == 1
    assert Product.objects.get(slug="dafu-24").category_id == other.pk


def test_gallery_dry_run_does_not_touch_existing_row(sku: SKU) -> None:
    row = ProductImage.objects.create(sku=sku, source_url=_URL, sort_order=7, is_published=False, alt="x")
    result = attach_gallery_images(sku, (_URL,), alt_prefix="BV", dry_run=True)
    row.refresh_from_db()
    assert result["existing"] == 1
    assert (row.sort_order, row.is_published) == (7, False)


def test_gallery_refresh_keeps_editor_hidden_photo_hidden(sku: SKU) -> None:
    row = ProductImage.objects.create(
        sku=sku,
        source_url=_URL,
        sort_order=7,
        is_published=False,
        hidden_by_editor=True,
        alt="x",
    )
    attach_gallery_images(sku, (_URL,), alt_prefix="BV")
    row.refresh_from_db()
    assert row.sort_order == 0
    assert row.is_published is False
