"""Tests for HVD-Q / capacitor QX catalog seed (HVA-P is out of RF scope)."""

from __future__ import annotations

import pytest

from catalog.etl.series_copy_hv_extra import (
    HVD_Q_SPECS,
    QX_SPECS,
    apply_hv_extra_enrichment,
    ensure_hv_qx_catalog,
    ensure_hvd_q_catalog,
)
from catalog.etl.sku_instructions import damper_area_for_nm
from catalog.etl.sku_variant import parse_sku_variant
from catalog.models import SKU, AttributeValue, Category


@pytest.mark.parametrize(
    ("code", "control"),
    [
        ("HVD24-5Q", "on_off"),
        ("HVA24-5P", "modulating"),  # parse only; not seeded for RF
        ("HVD230S-10QX", "on_off"),
        ("HVA24-5QX", "modulating"),
    ],
)
def test_sku_variant_hv_extra_suffixes(code: str, control: str) -> None:
    variant = parse_sku_variant(code)
    assert variant is not None
    assert variant.control == control


@pytest.mark.parametrize(("nm", "row"), sorted(HVD_Q_SPECS.items()))
def test_hvd_q_damper_area_matches_nm_formula(nm: int, row: dict[str, str]) -> None:
    """HVD-Q: площадь заслонки = Нм / 10 (10 Нм → до 1,0 м², not 2,0)."""
    assert row["damper-area"] == damper_area_for_nm(nm)


@pytest.mark.parametrize(("nm", "row"), sorted(QX_SPECS.items()))
def test_qx_damper_area_matches_nm_formula(nm: int, row: dict[str, str]) -> None:
    """HVA/HVD-QX: площадь заслонки = Нм / 10 (10 Нм → до 1,0 м², not 1,8)."""
    assert row["damper-area"] == damper_area_for_nm(nm)


@pytest.mark.django_db
def test_ensure_hvd_q_and_enrich() -> None:
    Category.objects.create(
        name="Воздух",
        slug="elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata",
    )
    Category.objects.create(
        name="Пружина",
        slug="elektroprivody-s-pruzhinnym-vozvratom",
    )
    Category.objects.create(
        name="Конденсатор",
        slug="elektronnye-otkazoustoychivye-vozdushnye-privody",
    )
    q = ensure_hvd_q_catalog(dry_run=False)
    qx = ensure_hv_qx_catalog(dry_run=False)
    assert q["products_created"] == 4
    assert q["skus_created"] == 16
    assert qx["products_created"] == 8
    assert qx["skus_created"] == 32
    assert SKU.objects.filter(sku_code="HVD24-5Q").exists()
    assert not SKU.objects.filter(sku_code__iregex=r"(?i)^hva.*\d+p$").exists()
    assert SKU.objects.filter(sku_code="HVA230-40QX").exists()

    stats = apply_hv_extra_enrichment(dry_run=False)
    assert stats["skus"] >= 16
    assert "ensure_hva_p" not in stats
    sku = SKU.objects.get(sku_code="HVD24-5Q")
    by = {av.attribute.slug: av.value for av in AttributeValue.objects.filter(sku=sku).select_related("attribute")}
    assert by["running-time"] == "< 20 с"
    assert by["weight"] == "< 0,8 кг"
    qx_sku = SKU.objects.get(sku_code="HVD24-5QX")
    qx_by = {
        av.attribute.slug: av.value for av in AttributeValue.objects.filter(sku=qx_sku).select_related("attribute")
    }
    assert qx_by["failsafe-time"] == "< 30 с"
    assert qx_by["charge-time"] == "3 мин 30 с"


@pytest.mark.django_db
@pytest.mark.parametrize(
    "sku_code",
    [
        "HVD24-10Q",
        "HVD24S-10Q",
        "HVD230-10Q",
        "HVD230S-10Q",
        "HVD24-10QX",
        "HVD24S-10QX",
        "HVD230-10QX",
        "HVD230S-10QX",
        "HVA24-10QX",
        "HVA24S-10QX",
        "HVA230-10QX",
        "HVA230S-10QX",
    ],
)
def test_enriched_10nm_q_qx_damper_area_is_one_m2(sku_code: str) -> None:
    """Regression: 10 Нм Q/QX must be до 1,0 м² (was 2,0 / 1,8)."""
    Category.objects.create(
        name="Воздух",
        slug="elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata",
    )
    Category.objects.create(
        name="Конденсатор",
        slug="elektronnye-otkazoustoychivye-vozdushnye-privody",
    )
    ensure_hvd_q_catalog(dry_run=False)
    ensure_hv_qx_catalog(dry_run=False)
    apply_hv_extra_enrichment(dry_run=False)
    sku = SKU.objects.get(sku_code=sku_code)
    area = AttributeValue.objects.get(sku=sku, attribute__slug="damper-area").value
    moment = AttributeValue.objects.get(sku=sku, attribute__slug="moment").value
    assert moment == "10 Нм"
    assert area == damper_area_for_nm(10)
    assert area == "до 1,0 м²"
