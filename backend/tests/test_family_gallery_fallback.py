"""Family gallery fallback when an edition has no own ProductImage rows."""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from catalog.models import SKU, Category, Product, ProductImage
from catalog.serializers import _sku_gallery_images


def _png_bytes() -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (8, 8), color=(40, 120, 200)).save(buf, format="PNG")
    return buf.getvalue()


_PNG = _png_bytes()


@pytest.mark.django_db
def test_sku_gallery_falls_back_to_family_sibling_photo() -> None:
    cat = Category.objects.create(name="Air", slug="air-family-gallery")
    product = Product.objects.create(
        name="HVA-5",
        slug="privod-vozdushniy-hva-5nm-gallery",
        category=cat,
    )
    with_photo = SKU.objects.create(
        product=product,
        sku_code="HVA24-5",
        name="HVA24-5",
        slug="hva24-5-gal",
        is_published=True,
    )
    bare = SKU.objects.create(
        product=product,
        sku_code="HVA230S-5",
        name="HVA230S-5",
        slug="hva230s-5-gal",
        is_published=True,
    )
    ProductImage.objects.create(
        sku=with_photo,
        image=SimpleUploadedFile("hva24-5.png", _PNG, content_type="image/png"),
        alt="HVA-5 | фото привода",
        source_url="https://example.test/hva5-product.webp",
        sort_order=0,
        is_published=True,
    )

    assert _sku_gallery_images(with_photo)
    bare_gallery = _sku_gallery_images(bare)
    assert len(bare_gallery) == 1
    assert bare_gallery[0].source_url.endswith("hva5-product.webp")


@pytest.mark.django_db
def test_sku_gallery_does_not_leak_opposite_control_from_family() -> None:
    cat = Category.objects.create(name="Air", slug="air-family-ctrl")
    product = Product.objects.create(
        name="DA5",
        slug="privod-da5-family-ctrl",
        category=cat,
    )
    modulating = SKU.objects.create(
        product=product,
        sku_code="da5fu24-a",
        name="A",
        slug="da5fu24-a-gal",
        is_published=True,
    )
    on_off = SKU.objects.create(
        product=product,
        sku_code="da5fu24-d",
        name="D",
        slug="da5fu24-d-gal",
        is_published=True,
    )
    ProductImage.objects.create(
        sku=modulating,
        image=SimpleUploadedFile("a.png", _PNG, content_type="image/png"),
        alt="плавное управление",
        source_url="https://example.test/da5-a.webp",
        sort_order=0,
        is_published=True,
    )

    assert _sku_gallery_images(modulating)
    assert _sku_gallery_images(on_off) == []


@pytest.mark.django_db
def test_catalog_list_card_image_uses_family_fallback() -> None:
    cat = Category.objects.create(name="Air", slug="air-family-api")
    product = Product.objects.create(
        name="HVD-5Q",
        slug="privod-vozdushniy-hvd-5q-api",
        category=cat,
    )
    donor = SKU.objects.create(
        product=product,
        sku_code="HVD24-5Q",
        name="HVD24-5Q",
        slug="hvd24-5q-api",
        is_published=True,
    )
    bare = SKU.objects.create(
        product=product,
        sku_code="HVD230-5Q",
        name="HVD230-5Q",
        slug="hvd230-5q-api",
        is_published=True,
    )
    ProductImage.objects.create(
        sku=donor,
        image=SimpleUploadedFile("hvd.png", _PNG, content_type="image/png"),
        alt="HVD-5Q | фото привода",
        source_url="https://example.test/hvd5q.webp",
        sort_order=0,
        is_published=True,
    )

    client = APIClient()
    response = client.get(f"/api/catalog/skus/{bare.slug}/")
    assert response.status_code == 200
    images = response.json().get("images") or []
    assert len(images) >= 1
    assert images[0]["alt"] == "HVD-5Q | фото привода"
