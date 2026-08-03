"""Tests for HVD-…F (smoke, spring return) series copy helpers."""

from __future__ import annotations

import pytest

from catalog.etl.series_copy_hvdf import (
    TORQUE_SPECS,
    apply_hvdf_enrichment,
    ensure_hvdf_catalog,
    hvdf_sku_code,
    is_hvdf_sku,
    parse_hvdf_torque_nm,
    product_slug_for_nm,
)
from catalog.etl.sku_instructions import damper_area_for_nm
from catalog.etl.sku_variant import sku_code_is_thermal
from catalog.facets.aux import aux_spdt_count_from_sku
from catalog.models import SKU, AttributeValue, Category, Product


@pytest.mark.django_db
def test_ensure_hvdf_catalog_creates_eight_skus() -> None:
    """Two products × four editions (24/230 × S/ST)."""
    Category.objects.create(
        name="Дымоудаление",
        slug="elektroprivody-dlya-klapanov-dymoudaleniya",
    )
    stats = ensure_hvdf_catalog(dry_run=False)
    assert stats["products_created"] == 2
    assert stats["skus_created"] == 8
    assert SKU.objects.filter(sku_code="HVD24S-3F").exists()
    assert SKU.objects.filter(sku_code="HVD230ST-5F").exists()
    product = Product.objects.get(slug=product_slug_for_nm(3))
    assert product.skus.count() == 4
    # Idempotent second run.
    again = ensure_hvdf_catalog(dry_run=False)
    assert again["products_created"] == 0
    assert again["skus_created"] == 0


def test_hvdf_code_helpers() -> None:
    """Parsing and edition builders match manual article codes."""
    assert parse_hvdf_torque_nm("HVD24ST-3F") == 3
    assert parse_hvdf_torque_nm("HVD24-5") is None
    assert is_hvdf_sku("HVD230S-5F") is True
    assert hvdf_sku_code(voltage="24", thermal=True, torque_nm=5) == "HVD24ST-5F"
    assert 3 in TORQUE_SPECS and 5 in TORQUE_SPECS
    assert sku_code_is_thermal("HVD24ST-3F") is True
    assert sku_code_is_thermal("HVD24S-3F") is False
    assert aux_spdt_count_from_sku("HVD24ST-3F") == 2
    assert aux_spdt_count_from_sku("HVD230S-5F") == 2


@pytest.mark.parametrize(("nm", "row"), sorted(TORQUE_SPECS.items()))
def test_hvdf_damper_area_matches_nm_formula(nm: int, row: dict[str, str]) -> None:
    """HVD-F: площадь = Нм / 10 (3 Нм → до 0,3 м², not 0,5)."""
    assert row["damper-area"] == damper_area_for_nm(nm)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "sku_code",
    [
        "HVD24S-3F",
        "HVD24ST-3F",
        "HVD230S-3F",
        "HVD230ST-3F",
    ],
)
def test_enriched_hvdf_3nm_damper_area_is_0_3(sku_code: str) -> None:
    """Regression: 3 Нм HVD-F must be до 0,3 м² (was wrongly 0,5 like 5 Нм)."""
    Category.objects.create(
        name="Дымоудаление",
        slug="elektroprivody-dlya-klapanov-dymoudaleniya",
    )
    apply_hvdf_enrichment(dry_run=False)
    sku = SKU.objects.get(sku_code=sku_code)
    area = AttributeValue.objects.get(sku=sku, attribute__slug="damper-area").value
    moment = AttributeValue.objects.get(sku=sku, attribute__slug="moment").value
    assert moment == "3 Нм"
    assert area == damper_area_for_nm(3)
    assert area == "до 0,3 м²"
    assert "до 0,3 м²" in (sku.description or "")
