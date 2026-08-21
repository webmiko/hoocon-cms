"""Tests for series-8100 brass PDF attach (documents only)."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from catalog.etl.ball_valve_8100_catalog_media import (
    _BRASS_DIMS,
    apply_8100_catalog_media,
    attach_8100_series_pdf,
    brass_body_code_from_sku,
    find_8100_series_pdf,
    sync_brass_dims_from_pdf,
    unpublish_legacy_8100_diagram_tiles,
)
from catalog.models import SKU, AttributeValue, Category, Product, ProductFile, ProductImage


def _png(size: tuple[int, int] = (400, 300), color: tuple[int, int, int] = (240, 240, 240)) -> bytes:
    from io import BytesIO

    buf = BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.parametrize(
    ("code", "body"),
    [
        ("8100-bv215a", "BV215"),
        ("8100-BV350B", "BV350"),
        ("H8101-BV215A-24A", None),
    ],
)
def test_brass_body_code_from_sku(code: str, body: str | None) -> None:
    assert brass_body_code_from_sku(code) == body


def test_brass_dims_table_covers_all_dn_cards() -> None:
    """PDF table constant covers every published brass DN body."""
    expected = {
        "BV215",
        "BV220",
        "BV225",
        "BV232",
        "BV240",
        "BV250",
        "BV315",
        "BV320",
        "BV325",
        "BV332",
        "BV340",
        "BV350",
    }
    assert set(_BRASS_DIMS) == expected
    assert _BRASS_DIMS["BV215"].h == "142"
    assert _BRASS_DIMS["BV315"].d == "30"


@pytest.mark.django_db
def test_attach_pdf_only_no_gallery_crops(tmp_path: Path) -> None:
    """PDF datasheet lands on brass SKUs; no 8100-series gallery tiles."""
    pdf = tmp_path / "шаровые краны серии 8100.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    cat = Category.objects.create(name="Ball", slug="sharovye-8100-pdf")
    product = Product.objects.create(
        name="BV215 | Шаровой кран 2-ходовый DN 15",
        slug="8100-bv215",
        category=cat,
    )
    sku = SKU.objects.create(
        product=product,
        sku_code="8100-bv215a",
        name="BV215A",
        slug="8100-bv215-8100-bv215a",
        is_published=True,
    )
    hero = ProductImage.objects.create(
        sku=sku,
        image=SimpleUploadedFile("hero.webp", _png(color=(40, 40, 40)), content_type="image/webp"),
        alt="hero",
        source_url="https://hoocon.ru/.local-assets/media-webp/2way-brass-dn15-product.webp",
        sort_order=0,
        is_published=True,
    )

    summary = apply_8100_catalog_media(dry_run=False, pdf_path=pdf)

    assert summary["pdf_created"] == 1
    pf = ProductFile.objects.get(sku=sku, title__contains="8100")
    assert pf.title == "Инструкция серии 8100 (шаровые краны)"
    assert ProductImage.objects.filter(source_url__contains="8100-series").count() == 0
    hero.refresh_from_db()
    assert hero.is_published is True
    assert hero.sort_order == 0


@pytest.mark.django_db
def test_unpublish_legacy_diagram_tiles() -> None:
    """Re-apply hides previously attached page-crop tiles."""
    cat = Category.objects.create(name="Ball", slug="sharovye-8100-legacy")
    product = Product.objects.create(name="BV220", slug="8100-bv220-legacy", category=cat)
    sku = SKU.objects.create(
        product=product,
        sku_code="8100-bv220a",
        name="BV220A",
        slug="8100-bv220-legacy-a",
        is_published=True,
    )
    tile = ProductImage.objects.create(
        sku=sku,
        image=SimpleUploadedFile("dims.webp", _png(), content_type="image/webp"),
        alt="legacy dims",
        source_url="https://hoocon.ru/.local-assets/8100-series/brass-dimensions.webp",
        sort_order=8,
        is_published=True,
    )
    assert unpublish_legacy_8100_diagram_tiles(dry_run=False) == 1
    tile.refresh_from_db()
    assert tile.is_published is False


@pytest.mark.django_db
def test_sync_brass_dims_fills_empty_only() -> None:
    """Empty size attrs are filled; existing matching values stay put."""
    cat = Category.objects.create(name="Ball", slug="sharovye-8100-attrs")
    product = Product.objects.create(name="BV220", slug="8100-bv220", category=cat)
    sku = SKU.objects.create(
        product=product,
        sku_code="8100-bv220a",
        name="BV220A",
        slug="8100-bv220-8100-bv220a",
        is_published=True,
    )
    from catalog.etl.attr_write import set_sku_attribute

    set_sku_attribute(
        sku,
        slug="height-actuator",
        value="146",
        name="Высота до верхнего края привода",
        unit="мм",
    )

    stats = sync_brass_dims_from_pdf(sku, dry_run=False)
    assert stats["filled"] >= 1
    assert AttributeValue.objects.filter(
        sku=sku,
        attribute__slug="valve-length",
        value="68",
    ).exists()
    assert AttributeValue.objects.filter(
        sku=sku,
        attribute__slug="height-actuator",
        value="146",
    ).exists()


@pytest.mark.django_db
def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    pdf = tmp_path / "seria.pdf"
    pdf.write_bytes(b"%PDF-1.4 x")
    cat = Category.objects.create(name="Ball", slug="sharovye-8100-dry")
    product = Product.objects.create(name="BV225", slug="8100-bv225", category=cat)
    SKU.objects.create(
        product=product,
        sku_code="8100-bv225a",
        name="BV225A",
        slug="8100-bv225-8100-bv225a",
        is_published=True,
    )
    summary = apply_8100_catalog_media(dry_run=True, pdf_path=pdf)
    assert summary["pdf_created"] == 1
    assert ProductFile.objects.count() == 0


def test_find_8100_series_pdf_override(tmp_path: Path) -> None:
    missing = tmp_path / "nope.pdf"
    assert find_8100_series_pdf(pdf_path=missing) is None
    present = tmp_path / "ok.pdf"
    present.write_bytes(b"%PDF")
    assert find_8100_series_pdf(pdf_path=present) == present


@pytest.mark.django_db
def test_attach_pdf_skip_when_too_large(tmp_path: Path) -> None:
    """Oversize PDF is skipped (mirrors catalog attach guard)."""
    from unittest.mock import patch

    pdf = tmp_path / "big.pdf"
    pdf.write_bytes(b"%PDF" + b"0" * 100)
    cat = Category.objects.create(name="Ball", slug="sharovye-8100-big")
    product = Product.objects.create(name="BV232", slug="8100-bv232", category=cat)
    sku = SKU.objects.create(
        product=product,
        sku_code="8100-bv232a",
        name="BV232A",
        slug="8100-bv232-8100-bv232a",
        is_published=True,
    )
    with patch(
        "catalog.etl.ball_valve_8100_catalog_media.MAX_PRODUCT_FILE_SIZE_BYTES",
        10,
    ):
        assert attach_8100_series_pdf(sku, pdf_path=pdf) == "too_large"
    assert ProductFile.objects.filter(sku=sku).count() == 0


@pytest.mark.django_db
def test_attach_renames_legacy_passport_series_title(tmp_path: Path) -> None:
    """Old «Паспорт серии…» rows become «Инструкция серии…» on re-attach."""
    from django.core.files.base import ContentFile

    from catalog.etl.ball_valve_8100_catalog_media import PDF_TITLE, PDF_TITLE_LEGACY

    pdf = tmp_path / "series.pdf"
    pdf.write_bytes(b"%PDF-renamed")
    cat = Category.objects.create(name="Ball", slug="sharovye-8100-rename")
    product = Product.objects.create(name="BV215", slug="8100-bv215-rename", category=cat)
    sku = SKU.objects.create(
        product=product,
        sku_code="8100-bv215a",
        name="BV215A",
        slug="8100-bv215-rename-a",
        is_published=True,
    )
    legacy = ProductFile(
        sku=sku,
        title=PDF_TITLE_LEGACY,
        file_type=ProductFile.FileType.DATASHEET,
        is_published=True,
        sort_order=40,
    )
    legacy.file.save("old.pdf", ContentFile(b"%PDF-old"), save=True)

    assert attach_8100_series_pdf(sku, pdf_path=pdf) == "update"
    assert ProductFile.objects.filter(sku=sku).count() == 1
    row = ProductFile.objects.get(sku=sku)
    assert row.title == PDF_TITLE
    assert not ProductFile.objects.filter(sku=sku, title=PDF_TITLE_LEGACY).exists()
