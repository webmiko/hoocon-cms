"""Tests for brass 8100 Kvs-disc crop attach."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.core.files.base import ContentFile

from catalog.etl.attr_write import set_sku_attribute
from catalog.etl.ball_valve_kvs_discs import (
    apply_ball_valve_kvs_discs,
    parse_8100_edition,
)
from catalog.models import SKU, Category, Product, ProductImage


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("8100-bv215a", (15, "a")),
        ("8100-BV220E", (20, "e")),
        ("8100-bv315b", (15, "b")),
        ("8100-bv250a", (50, "a")),
        ("8100-bv215", None),
        ("BR-M", None),
    ],
)
def test_parse_8100_edition(code: str, expected: tuple[int, str] | None) -> None:
    assert parse_8100_edition(code) == expected


@pytest.mark.django_db
def test_apply_ball_valve_kvs_discs_attaches_gallery_tile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disc WebP lands as published sort_order=30 without replacing hero."""
    from catalog.etl import ball_valve_kvs_discs as mod

    pack = tmp_path / "discs"
    pack.mkdir()
    # Minimal valid-ish webp bytes: reuse a tiny PNG via convert, or raw webp header.
    # ProductImage accepts webp; write a small PNG renamed — validator may check magic.
    from io import BytesIO

    from PIL import Image

    from catalog.etl.webp import convert_bytes_to_webp

    buf = BytesIO()
    Image.new("RGB", (32, 32), color=(180, 120, 40)).save(buf, format="PNG")
    (pack / "dn15-a.webp").write_bytes(convert_bytes_to_webp(buf.getvalue()))
    monkeypatch.setattr(mod, "_PACK_DIR", pack)

    cat = Category.objects.create(name="Краны", slug="sharovye-kvs-disc")
    product = Product.objects.create(
        category=cat,
        name="BV215",
        slug="8100-bv215",
    )
    sku = SKU.objects.create(
        product=product,
        name="BV215A",
        slug="8100-bv215-8100-bv215a",
        sku_code="8100-bv215a",
        is_published=True,
    )
    set_sku_attribute(sku, slug="kvs", name="Kvs", value="1,6", unit="м³/ч")
    hero = ProductImage(
        sku=sku,
        alt="hero",
        source_url="https://hoocon.ru/.local-assets/media-webp/2way-brass-dn15-product.webp",
        sort_order=0,
        is_published=True,
    )
    hero.image.save("hero.webp", ContentFile((pack / "dn15-a.webp").read_bytes()), save=True)

    summary = apply_ball_valve_kvs_discs(dry_run=False)
    assert summary["created"] == 1
    disc = ProductImage.objects.get(
        sku=sku,
        source_url="https://hoocon.ru/.local-assets/kvs-disc/dn15-a.webp",
    )
    assert disc.is_published
    assert disc.sort_order == 30
    assert "фото расходного диска" in disc.alt.casefold()
    assert "1,6" in disc.alt
    hero.refresh_from_db()
    assert hero.is_published and hero.sort_order == 0
