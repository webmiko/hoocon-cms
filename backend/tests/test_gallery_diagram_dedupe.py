"""Hide redundant combined / catalog dimension tiles when split diagrams exist."""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from catalog.etl.manual_diagrams import (
    unpublish_combined_when_split_diagrams,
    unpublish_redundant_hva_catalog_dimensions,
)
from catalog.models import SKU, Category, Product, ProductImage


def _tiny_png() -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (8, 8), color=(240, 240, 240)).save(buf, format="PNG")
    return buf.getvalue()


def _img(sku: SKU, *, alt: str, source_url: str, sort_order: int) -> ProductImage:
    return ProductImage.objects.create(
        sku=sku,
        image=SimpleUploadedFile(f"{sort_order}.png", _tiny_png(), content_type="image/png"),
        alt=alt,
        source_url=source_url,
        sort_order=sort_order,
        is_published=True,
    )


@pytest.mark.django_db
def test_unpublish_hva_catalog_dims_when_local_razmer_and_wiring() -> None:
    cat = Category.objects.create(name="Air", slug="air-diag-dedupe")
    product = Product.objects.create(name="HVA-20Q", slug="hva-20q-diag", category=cat)
    sku = SKU.objects.create(
        product=product,
        sku_code="HVA24-20Q",
        name="HVA24-20Q",
        slug="hva24-20q-diag",
        is_published=True,
    )
    _img(
        sku,
        alt="HVA-20Q | Схема подключения",
        source_url="https://hoocon.ru/.local-assets/hva-catalog/hva20q-wiring.webp",
        sort_order=5,
    )
    local = _img(
        sku,
        alt="HVA-20Q | Габаритные размеры привода (мм)",
        source_url="https://hoocon.ru/.local-assets/hva-catalog/hva20q-dimensions.webp",
        sort_order=6,
    )
    catalog = _img(
        sku,
        alt="HVA-20Q | Габаритные размеры привода (мм), чертёж из каталога",
        source_url="https://hoocon.ru/.local-assets/manual-diagrams/hva20q-dimensions.webp",
        sort_order=8,
    )

    assert unpublish_redundant_hva_catalog_dimensions(dry_run=False) == 1
    local.refresh_from_db()
    catalog.refresh_from_db()
    assert local.is_published is True
    assert catalog.is_published is False


@pytest.mark.django_db
def test_keep_catalog_dims_without_local_razmer() -> None:
    cat = Category.objects.create(name="Air2", slug="air-diag-keep")
    product = Product.objects.create(name="HVA-5", slug="hva-5-diag", category=cat)
    sku = SKU.objects.create(
        product=product,
        sku_code="HVA24-5",
        name="HVA24-5",
        slug="hva24-5-diag-keep",
        is_published=True,
    )
    _img(
        sku,
        alt="HVA-5 | Схема подключения",
        source_url="https://hoocon.ru/.local-assets/hva-catalog/hva5-wiring.webp",
        sort_order=5,
    )
    catalog = _img(
        sku,
        alt="HVA-5 | Габаритные размеры привода (мм), чертёж из каталога",
        source_url="https://hoocon.ru/.local-assets/manual-diagrams/hva5-dimensions.webp",
        sort_order=8,
    )

    assert unpublish_redundant_hva_catalog_dimensions(dry_run=False) == 0
    catalog.refresh_from_db()
    assert catalog.is_published is True


@pytest.mark.django_db
def test_unpublish_combined_when_split_exists() -> None:
    cat = Category.objects.create(name="Air3", slug="air-combined-dedupe")
    product = Product.objects.create(name="Act", slug="act-combined", category=cat)
    sku = SKU.objects.create(
        product=product,
        sku_code="HVA24-10Q",
        name="HVA24-10Q",
        slug="hva24-10q-combined",
        is_published=True,
    )
    _img(
        sku,
        alt="HVA-10Q | Схема подключения",
        source_url="https://hoocon.ru/.local-assets/hva-catalog/hva10q-wiring.webp",
        sort_order=5,
    )
    _img(
        sku,
        alt="HVA-10Q | Габаритные размеры привода (мм)",
        source_url="https://hoocon.ru/.local-assets/hva-catalog/hva10q-dimensions.webp",
        sort_order=6,
    )
    combined = _img(
        sku,
        alt="схема размеров и подключения к сети для привода вентиляции Hoocon",
        source_url="https://static.tildacdn.com/combined.jpg",
        sort_order=2,
    )

    assert unpublish_combined_when_split_diagrams(dry_run=False) == 1
    combined.refresh_from_db()
    assert combined.is_published is False
