"""Tests for HV dimension crops from the RU 2025 catalog."""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from catalog.etl.hv_catalog_dimensions import (
    apply_hv_catalog_dimensions,
    crop_hv_catalog_dimensions,
    default_hv_ru_catalog_pdf,
    envelope_stem_for_sku,
)
from catalog.models import SKU, Category, Product, ProductImage


@pytest.mark.parametrize(
    ("code", "stem"),
    [
        ("HVD24-5", "hv-5"),
        ("HVA230S-5Q", "hv-5"),
        ("HVA24-10", "hv-10"),
        ("HVD24-10Q", "hv-10"),
        ("HVA24-5QX", "hv-10"),
        ("HVD230S-10QX", "hv-10"),
        ("HVA24-20QX", "hv-20"),
        ("HVD24-40", "hv-40"),
        ("HVA24-40Q", "hv-40"),
        ("DA5FU-DS", None),
    ],
)
def test_envelope_stem_for_sku(code: str, stem: str | None) -> None:
    assert envelope_stem_for_sku(code) == stem


def test_crop_hv_catalog_dimensions_trims_half() -> None:
    """Synthetic spread: black drawing on right half is kept after crop."""
    page = Image.new("RGB", (1000, 800), (255, 255, 255))
    # Right-half drawing block in the lower band.
    for x in range(520, 900):
        for y in range(500, 750):
            page.putpixel((x, y), (20, 20, 20))
    crop = crop_hv_catalog_dimensions(page, left_page=False)
    assert crop.size[0] > 50
    assert crop.size[1] > 50
    # Mostly dark content after trim.
    extrema = crop.convert("L").getextrema()
    assert extrema[0] < 40


@pytest.mark.django_db
def test_apply_hv_catalog_dimensions_attaches_and_demotes() -> None:
    """Catalog crop becomes sort=6 and demotes legacy hva-catalog razmer."""
    pdf = default_hv_ru_catalog_pdf()
    if pdf is None or not pdf.is_file():
        pytest.skip("RU 2025 catalog PDF not available")

    cat = Category.objects.create(name="Air", slug="air-hv-dims")
    product = Product.objects.create(name="HVA-10", slug="hva-10-dims", category=cat)
    sku = SKU.objects.create(
        product=product,
        sku_code="HVA24-10",
        name="HVA24-10",
        slug="hva24-10-dims",
        is_published=True,
    )
    sku_qx = SKU.objects.create(
        product=product,
        sku_code="HVA24-5QX",
        name="HVA24-5QX",
        slug="hva24-5qx-dims",
        is_published=True,
    )
    wrong = ProductImage.objects.create(
        sku=sku,
        image=SimpleUploadedFile("wrong.webp", b"RIFF....WEBP", content_type="image/webp"),
        alt="HVA-10 | Габаритные размеры привода (мм)",
        source_url="https://hoocon.ru/.local-assets/hva-catalog/hva10-dimensions.webp",
        sort_order=6,
        is_published=True,
    )

    summary = apply_hv_catalog_dimensions(dry_run=False, catalog_pdf=pdf)
    assert summary["attached"] >= 2
    assert summary["envelopes"]["hv-10"]["catalog_page"] == 41

    wrong.refresh_from_db()
    assert wrong.is_published is False
    assert ProductImage.objects.filter(
        sku=sku,
        source_url__contains="hv-catalog/hv-10-dimensions",
        is_published=True,
        sort_order=6,
    ).exists()
    assert ProductImage.objects.filter(
        sku=sku_qx,
        source_url__contains="hv-catalog/hv-10-dimensions",
        is_published=True,
    ).exists()
