"""Tests for SA DS↔DST gallery pruning."""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from catalog.etl.sa_gallery import prune_sa_cross_edition_images
from catalog.models import SKU, Category, Product, ProductImage


def _png_bytes(size: tuple[int, int] = (8, 8)) -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", size, color=(200, 40, 40)).save(buf, format="PNG")
    return buf.getvalue()


_PNG = _png_bytes()


@pytest.mark.django_db
def test_prune_sa_unpublishes_opposite_edition_urls() -> None:
    cat = Category.objects.create(name="Fire", slug="fire-sa-gallery")
    product = Product.objects.create(name="SA5", slug="sa5-gallery-test", category=cat)
    ds = SKU.objects.create(
        product=product,
        sku_code="sa5fu24-ds",
        name="DS",
        slug="sa5fu24-ds-gal",
        is_published=True,
    )
    dst = SKU.objects.create(
        product=product,
        sku_code="sa5fu24-dst",
        name="DST",
        slug="sa5fu24-dst-gal",
        is_published=True,
    )
    nont = "https://example.test/sa5-plain.jpg"
    therm = "https://example.test/sa5-thermal.jpg"
    for sku, primary, secondary in (
        (ds, nont, therm),
        (dst, therm, nont),
    ):
        ProductImage.objects.create(
            sku=sku,
            image=SimpleUploadedFile(
                f"{sku.slug}-p.png",
                _PNG,
                content_type="image/png",
            ),
            alt=f"{sku.sku_code} primary",
            source_url=primary,
            sort_order=0,
            is_published=True,
        )
        ProductImage.objects.create(
            sku=sku,
            image=SimpleUploadedFile(
                f"{sku.slug}-s.png",
                _PNG,
                content_type="image/png",
            ),
            alt=f"{sku.sku_code} secondary",
            source_url=secondary,
            sort_order=1,
            is_published=True,
        )

    summary = prune_sa_cross_edition_images()
    assert summary["unpublished"] == 2
    assert ProductImage.objects.filter(sku=ds, source_url=therm, is_published=True).count() == 0
    assert ProductImage.objects.filter(sku=ds, source_url=nont, is_published=True).count() == 1
    assert ProductImage.objects.filter(sku=dst, source_url=nont, is_published=True).count() == 0
    assert ProductImage.objects.filter(sku=dst, source_url=therm, is_published=True).count() == 1
