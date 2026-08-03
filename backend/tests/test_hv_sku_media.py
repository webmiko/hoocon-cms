"""Tests for unique per-SKU HV studio photo attach."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from catalog.etl.hv_sku_media import (
    apply_hv_sku_media,
    hv_nm_canvas_factor,
    parse_hv_nm,
    prepare_hv_sku_hero_webp,
)
from catalog.models import SKU, Category, Product, ProductImage


def _cutout_png(
    size: tuple[int, int] = (600, 600),
    *,
    body: tuple[int, int, int, int] = (20, 20, 20, 255),
) -> bytes:
    from io import BytesIO

    from PIL import Image

    img = Image.new("RGBA", size, (0, 0, 0, 0))
    # Opaque body inset so alpha-trim has something to keep.
    inset = Image.new("RGBA", (size[0] // 2, size[1] // 2), body)
    img.paste(inset, (size[0] // 4, size[1] // 4), inset)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_parse_hv_nm_and_canvas_factor() -> None:
    assert parse_hv_nm("HVA24-5") == 5
    assert parse_hv_nm("HVD230S-40Q") == 40
    assert parse_hv_nm("HVA24-5QX") == 5
    assert parse_hv_nm("HVD24S-5F") == 5
    assert parse_hv_nm("HVD24ST-3F") == 3
    assert hv_nm_canvas_factor(5) == pytest.approx(0.78125)
    assert hv_nm_canvas_factor(40) == 1.0
    assert hv_nm_canvas_factor(3, is_fire=True) == pytest.approx(0.9)
    assert hv_nm_canvas_factor(5, is_fire=True) == 1.0


def test_faceplate_style_detection(tmp_path: Path) -> None:
    from PIL import Image

    from catalog.etl.hv_sku_media import _is_faceplate_style, _is_frontal_shot

    square = tmp_path / "square.png"
    tall = tmp_path / "tall.png"
    tiff = tmp_path / "frontal.tif"
    Image.new("RGBA", (1000, 1000), (0, 0, 0, 0)).save(square)
    Image.new("RGBA", (860, 1333), (0, 0, 0, 0)).save(tall)
    Image.new("RGB", (800, 800), (10, 10, 10)).save(tiff)
    assert _is_faceplate_style(square) is False
    assert _is_faceplate_style(tall) is True
    assert _is_frontal_shot(tiff) is True


@pytest.mark.django_db
def test_apply_hv_sku_media_attaches_frontal_when_no_perspective(tmp_path: Path) -> None:
    """Tall frontal PNG/TIFF become unique heroes when no perspective shot exists."""
    from PIL import Image

    nm40 = tmp_path / "40Nm"
    nm40.mkdir()
    Image.new("RGBA", (860, 1505), (20, 20, 20, 255)).save(nm40 / "HVD230-40.png")
    Image.new("RGB", (860, 1505), (25, 25, 25)).save(nm40 / "HVD230-40QX.tif")

    cat = Category.objects.create(name="Air", slug="air-hv-front")
    product = Product.objects.create(name="HVD-40", slug="hvd-40-front", category=cat)
    sku = SKU.objects.create(
        product=product,
        sku_code="HVD230-40",
        name="HVD230-40",
        slug="hvd230-40-front",
        is_published=True,
    )
    sku_qx = SKU.objects.create(
        product=product,
        sku_code="HVD230-40QX",
        name="HVD230-40QX",
        slug="hvd230-40qx-front",
        is_published=True,
    )
    shared = ProductImage.objects.create(
        sku=sku,
        image=SimpleUploadedFile(
            "shared.webp",
            _cutout_png(body=(200, 80, 80, 255)),
            content_type="image/webp",
        ),
        alt="shared",
        source_url="https://hoocon.ru/.local-assets/media-webp/hvd-40-product.webp",
        sort_order=0,
        is_published=True,
    )

    summary = apply_hv_sku_media(dry_run=False, photo_root=tmp_path)
    assert summary["frontal_fallback"] == 2
    assert summary["created"] + summary["updated"] == 2

    shared.refresh_from_db()
    assert shared.is_published is False
    assert ProductImage.objects.filter(
        sku=sku,
        source_url__contains="hv-sku/hvd230-40-product",
        is_published=True,
        sort_order=0,
    ).exists()
    assert ProductImage.objects.filter(
        sku=sku_qx,
        source_url__contains="hv-sku/hvd230-40qx-product",
        is_published=True,
        sort_order=0,
    ).exists()


@pytest.mark.django_db
def test_apply_hv_sku_media_prefers_perspective_over_frontal(tmp_path: Path) -> None:
    """Square perspective wins over a tall frontal for the same SKU code."""
    from PIL import Image

    folder = tmp_path / "pack"
    folder.mkdir()
    Image.new("RGBA", (1000, 1000), (30, 30, 30, 255)).save(folder / "HVD24S-5F.png")
    Image.new("RGBA", (860, 1505), (40, 40, 40, 255)).save(folder / "HVD24S-5F-dup.png")
    # Dup stem won't match SKU regex; add a second frontal-only sibling that must not steal.
    Image.new("RGBA", (860, 1505), (50, 50, 50, 255)).save(folder / "HVD230S-5F.png")

    cat = Category.objects.create(name="Fire", slug="fire-hv-persp")
    product = Product.objects.create(name="HVD-5F", slug="hvd-5f-persp", category=cat)
    sku = SKU.objects.create(
        product=product,
        sku_code="HVD24S-5F",
        name="HVD24S-5F",
        slug="hvd24s-5f-persp",
        is_published=True,
    )

    summary = apply_hv_sku_media(dry_run=False, photo_root=tmp_path)
    assert summary["frontal_fallback"] == 0
    assert summary["created"] + summary["updated"] == 1
    hero = ProductImage.objects.get(sku=sku, source_url__contains="hv-sku/")
    assert hero.is_published is True


@pytest.mark.django_db
def test_apply_hv_sku_media_attaches_unique_hero(tmp_path: Path) -> None:
    """Per-SKU PNG becomes published sort=0 and demotes shared media-webp hero."""
    nm5 = tmp_path / "5Nm"
    nm5.mkdir()
    (nm5 / "HVD24-5.png").write_bytes(_cutout_png(body=(30, 30, 30, 255)))
    (nm5 / "HVA24-5Q.png").write_bytes(_cutout_png(body=(40, 40, 40, 255)))

    cat = Category.objects.create(name="Air", slug="air-hv-sku")
    hvd_product = Product.objects.create(name="HVD-5", slug="hvd-5-sku", category=cat)
    hvd = SKU.objects.create(
        product=hvd_product,
        sku_code="HVD24-5",
        name="HVD24-5",
        slug="hvd24-5-sku",
        is_published=True,
    )
    hva_product = Product.objects.create(name="HVA-5Q", slug="hva-5q-sku", category=cat)
    hva_q = SKU.objects.create(
        product=hva_product,
        sku_code="HVA24-5Q",
        name="HVA24-5Q",
        slug="hva24-5q-sku",
        is_published=True,
    )
    hva_qx = SKU.objects.create(
        product=hva_product,
        sku_code="HVA24-5QX",
        name="HVA24-5QX",
        slug="hva24-5qx-sku",
        is_published=True,
    )
    shared = ProductImage.objects.create(
        sku=hvd,
        image=SimpleUploadedFile(
            "shared.webp",
            _cutout_png(body=(200, 80, 80, 255)),
            content_type="image/webp",
        ),
        alt="shared",
        source_url="https://hoocon.ru/.local-assets/media-webp/hvd-5-product.webp",
        sort_order=0,
        is_published=True,
    )

    summary = apply_hv_sku_media(dry_run=False, photo_root=tmp_path)
    assert summary["created"] + summary["updated"] == 3
    assert summary["qx_fallback"] == 1

    shared.refresh_from_db()
    assert shared.is_published is False

    hero = ProductImage.objects.filter(
        sku=hvd,
        source_url__contains="hv-sku/hvd24-5-product",
        is_published=True,
    ).first()
    assert hero is not None
    assert hero.sort_order == 0
    assert "HVD24-5" in hero.alt

    qx_hero = ProductImage.objects.filter(
        sku=hva_qx,
        source_url__contains="hv-sku/hva24-5qx-product",
        is_published=True,
    ).first()
    assert qx_hero is not None
    assert ProductImage.objects.filter(
        sku=hva_q,
        source_url__contains="hv-sku/hva24-5q-product",
        is_published=True,
    ).exists()


def test_prepare_hv_sku_hero_webp_returns_webp(tmp_path: Path) -> None:
    path = tmp_path / "HVA24-10.png"
    path.write_bytes(_cutout_png(size=(500, 800)))
    webp = prepare_hv_sku_hero_webp(path, sku_code="HVA24-10")
    assert webp[:4] == b"RIFF"
    assert b"WEBP" in webp[:16]
