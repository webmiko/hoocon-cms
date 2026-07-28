"""Tests for media-webp HV product hero attach."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from catalog.etl.hv_media_webp import apply_hv_media_webp
from catalog.models import SKU, Category, Product, ProductImage


def _png(size: tuple[int, int] = (900, 1200), color: tuple[int, int, int] = (30, 30, 30)) -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.django_db
def test_apply_hv_media_webp_replaces_hero(tmp_path: Path) -> None:
    """New media-webp hero becomes the published sort=0 shot."""
    pack = tmp_path / "media-webp"
    pack.mkdir()
    (pack / "hva-10q.webp").write_bytes(_png(color=(40, 40, 40)))
    (pack / "hvd-5.webp").write_bytes(_png(color=(45, 45, 45)))
    (pack / "hva-5.webp").write_bytes(_png(color=(50, 50, 50)))

    cat = Category.objects.create(name="Air", slug="air-hv-webp")
    product = Product.objects.create(name="HVA-10Q", slug="hva-10q-webp", category=cat)
    sku = SKU.objects.create(
        product=product,
        sku_code="HVA230-10Q",
        name="HVA230-10Q",
        slug="hva230-10q-webp",
        is_published=True,
    )
    hvd_product = Product.objects.create(name="HVD-5", slug="hvd-5-webp", category=cat)
    hvd_sku = SKU.objects.create(
        product=hvd_product,
        sku_code="HVD24-5",
        name="HVD24-5",
        slug="hvd24-5-webp",
        is_published=True,
    )
    hva_std = Product.objects.create(name="HVA-5", slug="hva-5-std-webp", category=cat)
    hva_sku = SKU.objects.create(
        product=hva_std,
        sku_code="HVA24-5",
        name="HVA24-5",
        slug="hva24-5-webp",
        is_published=True,
    )
    hva_q = SKU.objects.create(
        product=hva_std,
        sku_code="HVA24-5Q",
        name="HVA24-5Q",
        slug="hva24-5q-std-webp",
        is_published=True,
    )
    old = ProductImage.objects.create(
        sku=sku,
        image=SimpleUploadedFile("old.png", _png(color=(220, 80, 80)), content_type="image/png"),
        alt="old promo",
        source_url="https://hoocon.ru/.local-assets/hva-catalog/hva10q-product.webp",
        sort_order=0,
        is_published=True,
    )
    tilda = ProductImage.objects.create(
        sku=sku,
        image=SimpleUploadedFile("tilda.png", _png(color=(200, 100, 50)), content_type="image/png"),
        alt="HVA-10Q | 10 НМ Привод воздушный",
        source_url="https://static.tildacdn.com/stor123/photo.jpg",
        sort_order=1,
        is_published=True,
    )

    summary = apply_hv_media_webp(dry_run=False, photo_root=pack)
    assert summary["created"] + summary["updated"] >= 3
    old.refresh_from_db()
    tilda.refresh_from_db()
    assert old.is_published is False
    assert tilda.is_published is False

    fresh = ProductImage.objects.filter(
        sku=sku,
        source_url__contains="media-webp/hva-10q-product",
        is_published=True,
    ).first()
    assert fresh is not None
    assert fresh.sort_order == 0
    assert "HVA-10Q" in fresh.alt

    hvd_img = ProductImage.objects.filter(
        sku=hvd_sku,
        source_url__contains="media-webp/hvd-5-product",
        is_published=True,
    ).first()
    assert hvd_img is not None
    assert hvd_img.sort_order == 0

    std_img = ProductImage.objects.filter(
        sku=hva_sku,
        source_url__contains="media-webp/hva-5-product",
        is_published=True,
    ).first()
    assert std_img is not None
    # Bare ``hva-5`` must not attach to ``HVA24-5Q`` (no hva-5q in this pack → no hero).
    assert not ProductImage.objects.filter(
        sku=hva_q,
        source_url__contains="media-webp/hva-5-product",
        is_published=True,
    ).exists()
