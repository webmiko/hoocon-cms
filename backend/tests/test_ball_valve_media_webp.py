"""Tests for media-webp brass 8100 / iron 8100Q product hero attach."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from catalog.etl.ball_valve_media_webp import (
    _nearest_iron_path,
    _parse_iron_stem,
    _parse_pack_stem,
    _parse_q8100_size_stem,
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
        ("IRON DN80", None),
    ],
)
def test_parse_pack_stem(stem: str, expected: tuple[int, int] | None) -> None:
    """Pack names tolerate double spaces; non-brass stems return None."""
    assert _parse_pack_stem(stem) == expected


@pytest.mark.parametrize(
    ("stem", "expected"),
    [
        ("IRON DN80", 80),
        ("iron-dn100", 100),
        ("IRON DN 125", 125),
        ("2-WAY BRASS DN15", None),
    ],
)
def test_parse_iron_stem(stem: str, expected: int | None) -> None:
    """Iron pack stems → DN only."""
    assert _parse_iron_stem(stem) == expected


@pytest.mark.parametrize(
    ("stem", "expected"),
    [
        ("8100Q-S", "s"),
        ("8100Q-L", "l"),
        ("8100q_s", "s"),
        ("IRON DN80", None),
    ],
)
def test_parse_q8100_size_stem(stem: str, expected: str | None) -> None:
    """Size-class pack stems → s/l."""
    assert _parse_q8100_size_stem(stem) == expected


def test_nearest_iron_path_prefers_exact_then_closest() -> None:
    """DN65 without a file reuses the closest available Iron DN."""
    by_dn = {80: Path("IRON DN80.jpg"), 100: Path("IRON DN100.jpg")}
    assert _nearest_iron_path(by_dn, 80) == (80, by_dn[80])
    assert _nearest_iron_path(by_dn, 65) == (80, by_dn[80])
    assert _nearest_iron_path({}, 65) is None


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
        slug="8100-bv215a",
        is_published=True,
    )
    sku_b = SKU.objects.create(
        product=product,
        sku_code="8100-bv215b",
        name="BV215B",
        slug="8100-bv215b",
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
        slug="8100-bv320a",
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
    assert any(k.startswith("2way-brass-dn15:") for k in summary["by_stem"])
    assert any(k.startswith("3way-brass-dn20:") for k in summary["by_stem"])

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


@pytest.mark.django_db
def test_apply_ball_valve_media_webp_8100q_size_class(tmp_path: Path) -> None:
    """8100Q-S → DN65/80; 8100Q-L → DN100–150 (preferred over IRON)."""
    pack = tmp_path / "media-webp"
    pack.mkdir()
    (pack / "8100Q-S.webp").write_bytes(_png(color=(20, 20, 20)))
    (pack / "8100Q-L.webp").write_bytes(_png(color=(30, 30, 30)))
    (pack / "IRON DN80.jpg").write_bytes(_png(color=(50, 50, 50)))

    cat = Category.objects.create(name="Ball", slug="sharovye-krany-q-webp")
    mapping = (
        ("8100Q-BV265", 65, "8100q-s"),
        ("8100Q-BV280", 80, "8100q-s"),
        ("8100Q-BV2100", 100, "8100q-l"),
        ("8100Q-BV2125", 125, "8100q-l"),
        ("8100Q-BV2150", 150, "8100q-l"),
    )
    for code, dn, _stem in mapping:
        product = Product.objects.create(
            name=f"{code.split('-', 1)[1]} | Шаровой кран 2-ходовый DN {dn}",
            slug=f"8100q-bv2{dn}",
            category=cat,
        )
        SKU.objects.create(
            product=product,
            sku_code=code,
            name=code,
            slug=code.casefold(),
            is_published=True,
        )

    summary = apply_ball_valve_media_webp(dry_run=False, photo_root=pack)
    assert summary["created"] == 5
    for code, _dn, stem in mapping:
        sku = SKU.objects.get(sku_code=code)
        img = ProductImage.objects.filter(
            sku=sku,
            source_url__contains=f"media-webp/{stem}-product",
            is_published=True,
        ).first()
        assert img is not None, code
        assert img.sort_order == 0
        key = f"{stem}:8100q-bv2{_dn}"
        assert summary["by_stem"][key]["source"] == ("8100Q-S.webp" if stem == "8100q-s" else "8100Q-L.webp")


@pytest.mark.django_db
def test_apply_ball_valve_media_webp_iron_fallback(tmp_path: Path) -> None:
    """Without 8100Q-S/L, IRON DNxx is used (DN65 → nearest DN80)."""
    pack = tmp_path / "media-webp"
    pack.mkdir()
    (pack / "IRON DN80.jpg").write_bytes(_png(color=(20, 20, 20)))
    (pack / "IRON DN100.jpg").write_bytes(_png(color=(25, 25, 25)))

    cat = Category.objects.create(name="Ball", slug="sharovye-krany-q-iron")
    for code, dn in (("8100Q-BV265", 65), ("8100Q-BV280", 80), ("8100Q-BV2100", 100)):
        product = Product.objects.create(
            name=f"{code.split('-', 1)[1]} | Шаровой кран 2-ходовый DN {dn}",
            slug=f"8100q-bv2{dn}",
            category=cat,
        )
        SKU.objects.create(
            product=product,
            sku_code=code,
            name=code,
            slug=code.casefold(),
            is_published=True,
        )

    summary = apply_ball_valve_media_webp(dry_run=False, photo_root=pack)
    assert summary["created"] == 3
    assert summary["by_stem"]["iron-dn65:8100q-bv265"]["source"] == "IRON DN80.jpg"
    for code, dn in (("8100Q-BV265", 65), ("8100Q-BV280", 80), ("8100Q-BV2100", 100)):
        sku = SKU.objects.get(sku_code=code)
        assert ProductImage.objects.filter(
            sku=sku,
            source_url__contains=f"media-webp/iron-dn{dn}-product",
            is_published=True,
        ).exists()
