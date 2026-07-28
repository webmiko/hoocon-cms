"""Tests for ProductImage WebP audit and inferior-hero pruning."""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from catalog.etl.product_image_audit import (
    apply_product_image_cleanup,
    audit_product_images,
    prune_inferior_hero_duplicates,
)
from catalog.models import SKU, Category, Product, ProductImage


def _png(size: tuple[int, int], color: tuple[int, int, int] = (20, 80, 140)) -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="PNG")
    return buf.getvalue()


def _png_cutout(size: tuple[int, int], fill: tuple[int, int, int] = (30, 30, 30)) -> bytes:
    """Opaque product blob on a transparent top edge (HVD-style cutout)."""
    from io import BytesIO

    from PIL import Image, ImageDraw

    buf = BytesIO()
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    w, h = size
    draw.rectangle((w // 4, h // 3, 3 * w // 4, 7 * h // 8), fill=(*fill, 255))
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.django_db
def test_prune_keeps_local_asset_hero_over_tilda() -> None:
    cat = Category.objects.create(name="Air", slug="air-img-audit")
    product = Product.objects.create(name="HVA-5", slug="hva-5-img-audit", category=cat)
    sku = SKU.objects.create(
        product=product,
        sku_code="HVA24-5",
        name="HVA24-5",
        slug="hva24-5-img-audit",
        is_published=True,
    )
    weak = ProductImage.objects.create(
        sku=sku,
        image=SimpleUploadedFile("tilda.png", _png((811, 1080)), content_type="image/png"),
        alt="HVA-5 | 5 Нм Привод",
        source_url="https://static.tildacdn.com/stor123/51599499.jpg",
        sort_order=0,
        is_published=True,
    )
    strong = ProductImage.objects.create(
        sku=sku,
        image=SimpleUploadedFile(
            "local.png",
            _png_cutout((1200, 1500)),
            content_type="image/png",
        ),
        alt="HVA-5 | фото привода",
        source_url="https://hoocon.ru/.local-assets/hva-catalog/hva5-product.webp",
        sort_order=0,
        is_published=True,
    )

    summary = prune_inferior_hero_duplicates(dry_run=False)
    assert summary["unpublished"] == 1
    weak.refresh_from_db()
    strong.refresh_from_db()
    assert weak.is_published is False
    assert strong.is_published is True


@pytest.mark.django_db
def test_prune_prefers_neutral_studio_over_chroma_promo() -> None:
    """Red promo local-asset must not displace a smaller grey studio hero."""
    cat = Category.objects.create(name="Air", slug="air-img-chroma")
    product = Product.objects.create(name="HVA-5Q", slug="hva-5q-img-chroma", category=cat)
    sku = SKU.objects.create(
        product=product,
        sku_code="HVA230-5Q",
        name="HVA230-5Q",
        slug="hva230-5q-img-chroma",
        is_published=True,
    )
    studio = ProductImage.objects.create(
        sku=sku,
        image=SimpleUploadedFile(
            "studio.png",
            _png((811, 1080), color=(203, 207, 210)),
            content_type="image/png",
        ),
        alt="HVA-5Q | 5 Нм Привод",
        source_url="https://static.tildacdn.com/stor999/studio.jpg",
        sort_order=0,
        is_published=False,
    )
    promo = ProductImage.objects.create(
        sku=sku,
        image=SimpleUploadedFile(
            "promo.png",
            _png((1200, 1500), color=(220, 88, 90)),
            content_type="image/png",
        ),
        alt="HVA-5Q | фото привода",
        source_url="https://hoocon.ru/.local-assets/hva-catalog/hva5q-product.webp",
        sort_order=0,
        is_published=True,
    )

    summary = prune_inferior_hero_duplicates(dry_run=False)
    assert summary["republished"] == 1
    assert summary["unpublished"] == 1
    studio.refresh_from_db()
    promo.refresh_from_db()
    assert studio.is_published is True
    assert promo.is_published is False


@pytest.mark.django_db
def test_prune_keeps_secondary_gallery_angle() -> None:
    cat = Category.objects.create(name="Valves", slug="valves-img-audit")
    product = Product.objects.create(name="BV", slug="bv-img-audit", category=cat)
    sku = SKU.objects.create(
        product=product,
        sku_code="8100-bv2100",
        name="BV2100",
        slug="bv2100-img-audit",
        is_published=True,
    )
    first = ProductImage.objects.create(
        sku=sku,
        image=SimpleUploadedFile("a.png", _png((1042, 1599)), content_type="image/png"),
        alt="BV2100 | Шаровой кран — фото 1",
        source_url="https://hoocon.ru/.local-catalog/img_a.jpeg",
        sort_order=0,
        is_published=True,
    )
    second = ProductImage.objects.create(
        sku=sku,
        image=SimpleUploadedFile("b.png", _png((633, 958)), content_type="image/png"),
        alt="BV2100 | Шаровой кран — фото 2",
        source_url="https://hoocon.ru/.local-catalog/img_b.jpeg",
        sort_order=1,
        is_published=True,
    )
    summary = prune_inferior_hero_duplicates(dry_run=False)
    assert summary["unpublished"] == 0
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.is_published is True
    assert second.is_published is True


@pytest.mark.django_db
def test_audit_reports_weak_and_multi_hero() -> None:
    cat = Category.objects.create(name="Air", slug="air-img-audit-2")
    product = Product.objects.create(name="HVD-5Q", slug="hvd-5q-img-audit", category=cat)
    sku = SKU.objects.create(
        product=product,
        sku_code="HVD24-5Q",
        name="HVD24-5Q",
        slug="hvd24-5q-img-audit",
        is_published=True,
    )
    ProductImage.objects.create(
        sku=sku,
        image=SimpleUploadedFile("a.png", _png((400, 400)), content_type="image/png"),
        alt="HVD-5Q | фото привода",
        source_url="https://example.test/a.webp",
        sort_order=0,
        is_published=True,
    )
    ProductImage.objects.create(
        sku=sku,
        image=SimpleUploadedFile("b.png", _png((900, 900)), content_type="image/png"),
        alt="HVD-5Q | фото привода",
        source_url="https://hoocon.ru/.local-assets/hvd-catalog/hvd5q-product.webp",
        sort_order=0,
        is_published=True,
    )
    report = audit_product_images()
    assert report["weak_heroes"] >= 1
    assert report["multi_hero_skus"] >= 1
    cleaned = apply_product_image_cleanup(dry_run=False)
    assert cleaned["pruned"]["unpublished"] >= 1
    after = cleaned["after"]
    assert after["multi_hero_skus"] == 0
