"""Tests for HVD-Q / HVA-P / capacitor QX catalog seed."""

from __future__ import annotations

import pytest

from catalog.etl.series_copy_hv_extra import (
    apply_hv_extra_enrichment,
    ensure_hv_qx_catalog,
    ensure_hva_p_catalog,
    ensure_hvd_q_catalog,
)
from catalog.etl.sku_variant import parse_sku_variant
from catalog.models import SKU, AttributeValue, Category


@pytest.mark.parametrize(
    ("code", "control"),
    [
        ("HVD24-5Q", "on_off"),
        ("HVA24-5P", "modulating"),
        ("HVD230S-10QX", "on_off"),
        ("HVA24-5QX", "modulating"),
    ],
)
def test_sku_variant_hv_extra_suffixes(code: str, control: str) -> None:
    variant = parse_sku_variant(code)
    assert variant is not None
    assert variant.control == control


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
    p = ensure_hva_p_catalog(dry_run=False)
    qx = ensure_hv_qx_catalog(dry_run=False)
    assert q["products_created"] == 4
    assert q["skus_created"] == 16
    assert p["products_created"] == 3
    assert p["skus_created"] == 6
    assert qx["products_created"] == 8
    assert qx["skus_created"] == 32
    assert SKU.objects.filter(sku_code="HVD24-5Q").exists()
    assert SKU.objects.filter(sku_code="HVA24S-10P").exists()
    assert SKU.objects.filter(sku_code="HVA230-40QX").exists()

    stats = apply_hv_extra_enrichment(dry_run=False)
    assert stats["skus"] >= 16
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
