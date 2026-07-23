"""Tests for A/AS ↔ D/DS control gallery pruning."""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from catalog.etl.control_gallery import prune_cross_control_images
from catalog.models import SKU, Category, Product, ProductImage


def _png_bytes(size: tuple[int, int] = (8, 8)) -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", size, color=(200, 40, 40)).save(buf, format="PNG")
    return buf.getvalue()


_PNG = _png_bytes()


@pytest.mark.django_db
def test_prune_control_unpublishes_opposite_edition_urls() -> None:
    """A card drops on/off marketing shot; D card drops modulating shot."""
    cat = Category.objects.create(name="Air", slug="air-control-gallery")
    product = Product.objects.create(name="DA2", slug="da2-gallery-test", category=cat)
    sku_a = SKU.objects.create(
        product=product,
        sku_code="DA2MU230-A",
        name="A",
        slug="da2mu230-a-gal",
        is_published=True,
    )
    sku_d = SKU.objects.create(
        product=product,
        sku_code="DA2MU230-D",
        name="D",
        slug="da2mu230-d-gal",
        is_published=True,
    )
    modulating = "https://example.test/da2-modulating.jpg"
    on_off = "https://example.test/da2-on-off.jpg"
    for sku, primary, secondary in (
        (sku_a, modulating, on_off),
        (sku_d, on_off, modulating),
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

    summary = prune_cross_control_images()
    assert summary["unpublished"] == 2
    assert (
        ProductImage.objects.filter(
            sku=sku_a,
            source_url=on_off,
            is_published=True,
        ).count()
        == 0
    )
    assert (
        ProductImage.objects.filter(
            sku=sku_a,
            source_url=modulating,
            is_published=True,
        ).count()
        == 1
    )
    assert (
        ProductImage.objects.filter(
            sku=sku_d,
            source_url=modulating,
            is_published=True,
        ).count()
        == 0
    )
    assert (
        ProductImage.objects.filter(
            sku=sku_d,
            source_url=on_off,
            is_published=True,
        ).count()
        == 1
    )
