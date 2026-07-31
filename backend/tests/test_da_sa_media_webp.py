"""Tests for media-webp DA/SA product hero attach."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from catalog.etl.da_sa_media_webp import apply_da_sa_media_webp
from catalog.models import SKU, Category, Product, ProductImage


def _png(size: tuple[int, int] = (900, 1200), color: tuple[int, int, int] = (30, 30, 30)) -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.django_db
def test_apply_da_sa_media_webp_ds_and_dst_fallback(tmp_path: Path) -> None:
    """DST uses -ds body photo (not -dst composite); falls back if only -ds exists."""
    pack = tmp_path / "media-webp"
    pack.mkdir()
    (pack / "sa3fu-ds.webp").write_bytes(_png(color=(40, 40, 40)))
    (pack / "sa3fu-dst.webp").write_bytes(_png(color=(80, 40, 40)))
    (pack / "sa30mu-ds.webp").write_bytes(_png(color=(40, 80, 40)))

    cat = Category.objects.create(name="Fire", slug="fire-dasa-webp")
    p_fu = Product.objects.create(name="SA3FU", slug="sa3fu-webp", category=cat)
    p_mu = Product.objects.create(name="SA30MU", slug="sa30mu-webp", category=cat)

    ds = SKU.objects.create(
        product=p_fu,
        sku_code="sa3fu24-ds",
        name="sa3fu24-ds",
        slug="sa3fu24-ds-webp",
        is_published=True,
    )
    dst = SKU.objects.create(
        product=p_fu,
        sku_code="sa3fu24-dst",
        name="sa3fu24-dst",
        slug="sa3fu24-dst-webp",
        is_published=True,
    )
    mu_dst = SKU.objects.create(
        product=p_mu,
        sku_code="SA30MU24-DST",
        name="SA30MU24-DST",
        slug="sa30mu24-dst-webp",
        is_published=True,
    )
    ProductImage.objects.create(
        sku=ds,
        image=SimpleUploadedFile("old.png", _png(color=(220, 80, 80)), content_type="image/png"),
        alt="old",
        source_url="https://static.tildacdn.com/old.jpg",
        sort_order=0,
        is_published=True,
    )

    summary = apply_da_sa_media_webp(dry_run=False, photo_root=pack)
    assert summary["created"] + summary["updated"] >= 3

    ds_img = ProductImage.objects.filter(
        sku=ds,
        source_url__contains="media-webp/sa3fu-ds-product",
        is_published=True,
    ).first()
    dst_img = ProductImage.objects.filter(
        sku=dst,
        source_url__contains="media-webp/sa3fu-ds-product",
        is_published=True,
    ).first()
    dst_old = ProductImage.objects.filter(
        sku=dst,
        source_url__contains="media-webp/sa3fu-dst-product",
        is_published=True,
    ).first()
    mu_img = ProductImage.objects.filter(
        sku=mu_dst,
        source_url__contains="media-webp/sa30mu-ds-product",
        is_published=True,
    ).first()
    assert ds_img is not None and ds_img.sort_order == 0
    assert dst_img is not None and dst_img.sort_order == 0
    assert dst_old is None
    assert mu_img is not None and mu_img.sort_order == 0
    assert ProductImage.objects.filter(sku=ds, source_url__contains="tildacdn", is_published=True).count() == 0


@pytest.mark.django_db
def test_apply_da_sa_media_webp_colon_editions(tmp_path: Path) -> None:
    """``d:ds`` / ``a:as`` packs map to both edition suffixes; voltage mask respected."""
    pack = tmp_path / "media-webp"
    pack.mkdir()
    (pack / "da5fu-d:ds.webp").write_bytes(_png(color=(50, 50, 50)))
    (pack / "da5fu24-a:as.webp").write_bytes(_png(color=(60, 60, 60)))
    (pack / "da10:15:20fu-a:as.webp").write_bytes(_png(color=(65, 65, 65)))
    (pack / "da10:15:20fu-d:ds.webp").write_bytes(_png(color=(55, 55, 120)))
    (pack / "da8:16:24mu24-d:ds.webp").write_bytes(_png(color=(70, 70, 70)))
    (pack / "da10:20mqu-d:ds.webp").write_bytes(_png(color=(80, 80, 80)))
    (pack / "da10:20mqu-a:as.webp").write_bytes(_png(color=(85, 85, 85)))

    cat = Category.objects.create(name="Air DA", slug="air-dasa-webp")
    product = Product.objects.create(name="DA5FU", slug="da5fu-webp", category=cat)
    codes = ("da5fu24-d", "da5fu24-ds", "da5fu24-a", "da5fu24-as", "da5fu230-d")
    skus = [
        SKU.objects.create(
            product=product,
            sku_code=code,
            name=code,
            slug=f"{code}-webp",
            is_published=True,
        )
        for code in codes
    ]
    p10 = Product.objects.create(name="DA10FU", slug="da10fu-webp", category=cat)
    da10_a = SKU.objects.create(
        product=p10,
        sku_code="da10fu24-a",
        name="da10fu24-a",
        slug="da10fu24-a-webp",
        is_published=True,
    )
    da15_as = SKU.objects.create(
        product=p10,
        sku_code="da15fu24-as",
        name="da15fu24-as",
        slug="da15fu24-as-webp",
        is_published=True,
    )
    p32 = Product.objects.create(name="DA32MU", slug="da32mu-webp", category=cat)
    da32 = SKU.objects.create(
        product=p32,
        sku_code="DA32MU24-DS",
        name="DA32MU24-DS",
        slug="da32mu24-ds-webp",
        is_published=True,
    )
    p8 = Product.objects.create(name="DA8MQU", slug="da8mqu-webp", category=cat)
    da8 = SKU.objects.create(
        product=p8,
        sku_code="DA8MQU24-DS",
        name="DA8MQU24-DS",
        slug="da8mqu24-ds-webp",
        is_published=True,
    )

    summary = apply_da_sa_media_webp(dry_run=False, photo_root=pack)
    assert summary["created"] == 9

    for sku in skus[:2] + skus[4:]:
        assert ProductImage.objects.filter(
            sku=sku,
            source_url__contains="media-webp/da5fu-d:ds-product",
            is_published=True,
        ).exists()
    for sku in skus[2:4]:
        assert ProductImage.objects.filter(
            sku=sku,
            source_url__contains="media-webp/da5fu24-a:as-product",
            is_published=True,
        ).exists()
    for sku in (da10_a, da15_as):
        assert ProductImage.objects.filter(
            sku=sku,
            source_url__contains="media-webp/da10:15:20fu-d:ds-product",
            is_published=True,
        ).exists()
    assert ProductImage.objects.filter(
        sku=da32,
        source_url__contains="media-webp/da8:16:24mu24-d:ds-product",
        is_published=True,
    ).exists()
    assert ProductImage.objects.filter(
        sku=da8,
        source_url__contains="media-webp/da10:20mqu-d:ds-product",
        is_published=True,
    ).exists()


@pytest.mark.django_db
def test_da20fu24_a_as_uses_d_ds_body_photo(tmp_path: Path) -> None:
    """DA20FU24-A/AS must attach the shared ``…-d:ds`` hero, not ``…-a:as``."""
    pack = tmp_path / "media-webp"
    pack.mkdir()
    (pack / "da10:15:20fu-a:as.webp").write_bytes(_png(color=(200, 40, 40)))
    (pack / "da10:15:20fu-d:ds.webp").write_bytes(_png(color=(40, 40, 200)))

    cat = Category.objects.create(name="Spring", slug="spring-da20-photo")
    product = Product.objects.create(name="DA20FU", slug="da20fu-photo", category=cat)
    a = SKU.objects.create(
        product=product,
        sku_code="da20fu24-a",
        name="da20fu24-a",
        slug="da20fu24-a-photo",
        is_published=True,
    )
    as_sku = SKU.objects.create(
        product=product,
        sku_code="da20fu24-as",
        name="da20fu24-as",
        slug="da20fu24-as-photo",
        is_published=True,
    )
    ds = SKU.objects.create(
        product=product,
        sku_code="da20fu24-ds",
        name="da20fu24-ds",
        slug="da20fu24-ds-photo",
        is_published=True,
    )

    summary = apply_da_sa_media_webp(dry_run=False, photo_root=pack)
    assert summary["created"] == 3
    for sku in (a, as_sku, ds):
        assert ProductImage.objects.filter(
            sku=sku,
            source_url__contains="media-webp/da10:15:20fu-d:ds-product",
            is_published=True,
        ).exists()
    assert (
        ProductImage.objects.filter(
            sku__in=[a, as_sku],
            source_url__contains="media-webp/da10:15:20fu-a:as-product",
            is_published=True,
        ).count()
        == 0
    )
