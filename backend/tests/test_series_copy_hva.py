"""Tests for HVA manual attach + datasheet enrichment."""

from __future__ import annotations

from pathlib import Path

import pytest

from catalog.etl.manual_pdfs import (
    discover_hva_manuals,
    parse_hva_manual_token,
    sku_codes_for_hva_manual,
)
from catalog.etl.series_copy_hva import FAMILY_SPECS, apply_hva_enrichment, parse_hva_std_q
from catalog.models import (
    SKU,
    AttributeValue,
    Category,
    Product,
    ProductFile,
)


def test_hva_family_dimensions_match_catalog_2025() -> None:
    """Catalog pp. 40–54: HVA std/Q envelopes (H×W×D), aligned with HVD air/Q."""
    assert FAMILY_SPECS[(5, "")]["dimensions"] == "144,1 × 71,1 × 62,1 мм"
    assert FAMILY_SPECS[(5, "q")]["dimensions"] == "144,1 × 71,1 × 62,1 мм"
    assert FAMILY_SPECS[(2, "")]["dimensions"] == "144,1 × 71,1 × 62,1 мм"
    assert FAMILY_SPECS[(5, "uq")]["dimensions"] == "167,8 × 86,2 × 68 мм"
    assert FAMILY_SPECS[(8, "q")]["dimensions"] == "167,8 × 86,2 × 68 мм"
    assert FAMILY_SPECS[(10, "")]["dimensions"] == "167,8 × 86,2 × 68 мм"
    assert FAMILY_SPECS[(10, "q")]["dimensions"] == "167,8 × 86,2 × 68 мм"
    assert FAMILY_SPECS[(20, "")]["dimensions"] == "191,8 × 103,4 × 68 мм"
    assert FAMILY_SPECS[(40, "")]["dimensions"] == "198,6 × 110,2 × 68 мм"
    assert FAMILY_SPECS[(40, "q")]["dimensions"] == "198,6 × 110,2 × 68 мм"


@pytest.mark.parametrize(
    ("stem", "expected"),
    [
        ("hva-5", "5"),
        ("hva-5q.pdf", "5q"),
        ("hva-5uq", "5uq"),
        ("hva-10p", None),  # RF-excluded Chinese spring
        ("HVA-5 instruction", "5"),
        ("da5fu-d:ds", None),
    ],
)
def test_parse_hva_manual_token(stem: str, expected: str | None) -> None:
    assert parse_hva_manual_token(stem) == expected


def test_sku_codes_for_hva_manual_exact_body() -> None:
    codes = [
        "HVA24-5",
        "HVA24S-5",
        "HVA24-5Q",
        "HVA230S-5Q",
        "HVA24-5P",
    ]
    assert sku_codes_for_hva_manual("5", codes) == ["HVA24-5", "HVA24S-5"]
    assert sku_codes_for_hva_manual("5q", codes) == ["HVA24-5Q", "HVA230S-5Q"]
    assert sku_codes_for_hva_manual("5p", codes) == ["HVA24-5P"]


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("HVA24-5", (5, "", "24", False)),
        ("HVA230S-5Q", (5, "q", "230", True)),
        ("HVA24S-5UQ", (5, "uq", "24", True)),
        ("HVA24-2", (2, "", "24", False)),
        ("HVA230-8Q", (8, "q", "230", False)),
        ("HVA24-5P", None),
    ],
)
def test_parse_hva_std_q(
    code: str,
    expected: tuple[int, str, str, bool] | None,
) -> None:
    assert parse_hva_std_q(code) == expected


@pytest.mark.django_db
def test_discover_hva_manuals_maps_existing_skus(tmp_path: Path) -> None:
    cat = Category.objects.create(name="Воздух", slug="vozdushnie-hva-man")
    product = Product.objects.create(name="HVA-5", slug="hva-5-man", category=cat)
    SKU.objects.create(
        product=product,
        name="HVA24-5",
        slug="hva24-5-man",
        sku_code="HVA24-5",
        is_published=True,
    )
    SKU.objects.create(
        product=product,
        name="HVA24-5Q",
        slug="hva24-5q-man",
        sku_code="HVA24-5Q",
        is_published=True,
    )
    (tmp_path / "hva-5.pdf").write_bytes(b"%PDF-5")
    (tmp_path / "hva-5q.pdf").write_bytes(b"%PDF-5q")
    (tmp_path / "hva-10.pdf").write_bytes(b"%PDF-10")
    matches, warnings = discover_hva_manuals(tmp_path)
    by_kind = {m.kind: m for m in matches}
    assert set(by_kind) == {"5", "5q"}
    assert by_kind["5"].sku_codes == ("HVA24-5",)
    assert by_kind["5q"].sku_codes == ("HVA24-5Q",)
    assert any("hva-10.pdf" in w for w in warnings)


@pytest.mark.django_db
def test_ensure_hva_catalog_creates_missing_families() -> None:
    from catalog.etl.series_copy_hva import ensure_hva_catalog

    Category.objects.create(
        name="Без пружины",
        slug="elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata",
    )
    Category.objects.create(
        name="Ускоренные",
        slug="elektroprivody-uskorennye-bez-pruzhinnogo-vozvrata",
    )
    stats = ensure_hva_catalog(dry_run=False)
    assert stats["products_created"] == 11
    assert stats["skus_created"] == 44
    assert SKU.objects.filter(sku_code="HVA24-10").exists()
    assert SKU.objects.filter(sku_code="HVA230S-40Q").exists()
    assert SKU.objects.filter(sku_code="HVA24-2").exists()
    assert SKU.objects.filter(sku_code="HVA24-8Q").exists()
    assert SKU.objects.filter(sku_code="HVA24-5UQ").exists()
    # Seeded for Admin/PDF attach, hidden on the public site for now.
    assert SKU.objects.filter(sku_code="HVA24-2", is_published=False).exists()
    assert SKU.objects.filter(sku_code="HVA230S-5UQ", is_published=False).exists()
    assert SKU.objects.filter(sku_code="HVA24-8Q", is_published=False).exists()
    assert SKU.objects.filter(sku_code="HVA24-10", is_published=True).exists()


@pytest.mark.django_db
def test_apply_hva_enrichment_fixes_weight_and_wire() -> None:
    Category.objects.create(
        name="Без пружины",
        slug="elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata",
    )
    Category.objects.create(
        name="Ускоренные",
        slug="elektroprivody-uskorennye-bez-pruzhinnogo-vozvrata",
    )
    cat = Category.objects.create(name="Воздух", slug="vozdushnie-hva-enr")
    product = Product.objects.create(name="HVA-5Q", slug="hva-5q-enr", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="HVA24-5Q",
        slug="hva24-5q-enr",
        sku_code="HVA24-5Q",
        is_published=True,
    )
    stats = apply_hva_enrichment(dry_run=False)
    assert stats["updated"] >= 1
    by_slug = {
        av.attribute.slug: av.value for av in AttributeValue.objects.filter(sku=sku).select_related("attribute")
    }
    assert by_slug["weight"] == "< 0,8 кг"
    assert by_slug["wire-cross-section"] == "0,5 мм²"
    assert by_slug["running-time"] == "< 20 с"
    assert by_slug["dimensions"] == "144,1 × 71,1 × 62,1 мм"


@pytest.mark.django_db
def test_attach_hva_creates_product_file(tmp_path: Path) -> None:
    from catalog.etl.manual_pdfs import attach_hva_manuals

    cat = Category.objects.create(name="Воздух", slug="vozdushnie-hva-pf")
    product = Product.objects.create(name="HVA-5", slug="hva-5-pf", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="HVA24-5",
        slug="hva24-5-pf",
        sku_code="HVA24-5",
        is_published=True,
    )
    (tmp_path / "hva-5.pdf").write_bytes(b"%PDF-fake-hva5")
    summary = attach_hva_manuals(tmp_path, dry_run=False)
    assert summary["created"] == 1
    pf = ProductFile.objects.get(sku=sku)
    assert pf.title == "Инструкция HVA-5"
    assert pf.file_type == ProductFile.FileType.DATASHEET
