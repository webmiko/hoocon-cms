"""Tests for media-webp brass 8100 product hero attach."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from catalog.etl.ball_valve_media_webp import (
    _parse_pack_stem,
    apply_ball_valve_media_webp,
)
from catalog.models import SKU, Category, Product, ProductImage


def _png(size: tuple[int, int] = (900, 1200), color: tuple[int, int, int] = (30, 30, 30)) -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.parametrize(
    ("stem", "expected"),
    [
        ("2-WAY BRASS DN15", (2, 15)),
        ("2-WAY  BRASS DN20", (2, 20)),
        ("3-WAY BRASS DN50", (3, 50)),
        ("hva-5", None),
    ],
)
def test_parse_pack_stem(stem: str, expected: tuple[int, int] | None) -> None:
    """Pack names tolerate double spaces; non-brass stems return None."""
    assert _parse_pack_stem(stem) == expected


@pytest.mark.django_db
def test_apply_ball_valve_media_webp_replaces_hero(tmp_path: Path) -> None:
    """New media-webp hero becomes the published sort=0 shot on all DN SKUs."""
    pack = tmp_path / "media-webp"
    pack.mkdir()
    (pack / "2-WAY BRASS DN15.webp").write_bytes(_png(color=(40, 40, 40)))
    (pack / "3-WAY  BRASS DN20.webp").write_bytes(_png(color=(45, 45, 45)))

    cat = Category.objects.create(name="Ball", slug="sharovye-krany-bv-webp")
    product = Product.objects.create(
        name="BV215 | Шаровой кран 2-ходовый DN 15",
        slug="8100-bv215",
        category=cat,
    )
    sku_a = SKU.objects.create(
        product=product,
        sku_code="8100-bv215a",
        name="BV215A",
        slug="8100-bv215-8100-bv215a",
        is_published=True,
    )
    sku_b = SKU.objects.create(
        product=product,
        sku_code="8100-bv215b",
        name="BV215B",
        slug="8100-bv215-8100-bv215b",
        is_published=True,
    )
    three_way = Product.objects.create(
        name="BV320 | Шаровой кран 3-ходовый DN 20",
        slug="8100-bv320",
        category=cat,
    )
    sku_320 = SKU.objects.create(
        product=three_way,
        sku_code="8100-bv320a",
        name="BV320A",
        slug="8100-bv320-8100-bv320a",
        is_published=True,
    )
    old = ProductImage.objects.create(
        sku=sku_a,
        image=SimpleUploadedFile("old.png", _png(color=(220, 80, 80)), content_type="image/png"),
        alt="old tilda",
        source_url="https://static.tildacdn.com/stor123/photo.jpg",
        sort_order=0,
        is_published=True,
    )

    summary = apply_ball_valve_media_webp(dry_run=False, photo_root=pack)
    assert summary["created"] >= 3
    assert "2way-brass-dn15" in summary["by_stem"]
    assert "3way-brass-dn20" in summary["by_stem"]

    old.refresh_from_db()
    assert old.is_published is False

    for sku in (sku_a, sku_b):
        fresh = ProductImage.objects.filter(
            sku=sku,
            source_url__contains="media-webp/2way-brass-dn15-product",
            is_published=True,
        ).first()
        assert fresh is not None
        assert fresh.sort_order == 0
        assert "BV215" in fresh.alt

    three_img = ProductImage.objects.filter(
        sku=sku_320,
        source_url__contains="media-webp/3way-brass-dn20-product",
        is_published=True,
    ).first()
    assert three_img is not None
    assert three_img.sort_order == 0
