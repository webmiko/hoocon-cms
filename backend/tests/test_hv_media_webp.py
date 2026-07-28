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

    cat = Category.objects.create(name="Air", slug="air-hv-webp")
    product = Product.objects.create(name="HVA-10Q", slug="hva-10q-webp", category=cat)
    sku = SKU.objects.create(
        product=product,
        sku_code="HVA230-10Q",
        name="HVA230-10Q",
        slug="hva230-10q-webp",
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

    summary = apply_hv_media_webp(dry_run=False, photo_root=pack)
    assert summary["created"] + summary["updated"] >= 1
    old.refresh_from_db()
    assert old.is_published is False

    fresh = ProductImage.objects.filter(
        sku=sku,
        source_url__contains="media-webp/hva-10q-product",
        is_published=True,
    ).first()
    assert fresh is not None
    assert fresh.sort_order == 0
