"""Tests for SA..FQU fast fire/smoke series copy."""

from __future__ import annotations

import pytest

from catalog.etl.series_copy_safqu import (
    TORQUE_SPECS,
    apply_safqu_enrichment,
    ensure_safqu_catalog,
    parse_safqu_torque_nm,
    safqu_sku_code,
)
from catalog.models import SKU, AttributeValue, Category, Product


@pytest.mark.django_db
def test_ensure_safqu_catalog_creates_eight_skus_per_nm() -> None:
    """SA3FQU and SA10FQU: four editions each (24/230 × DS/DST)."""
    Category.objects.create(
        name="Противопожарные",
        slug="elektroprivody-protivopozharnye-i-dymovye",
    )
    stats = ensure_safqu_catalog(dry_run=False)
    assert stats["products_created"] == 2
    assert stats["skus_created"] == 8
    assert SKU.objects.filter(sku_code="SA3FQU24-DS").exists()
    assert SKU.objects.filter(sku_code="SA10FQU230-DST").exists()


def test_safqu_torque_from_manual_tables() -> None:
    """FQU stroke ~35 s and SA10 holding 3 Вт — from EN sa3/sa10fqu PDFs."""
    assert parse_safqu_torque_nm("SA3FQU24-DST") == 3
    assert safqu_sku_code(voltage="230", thermal=False, torque_nm=10) == "SA10FQU230-DS"
    row3 = TORQUE_SPECS[3]
    row10 = TORQUE_SPECS[10]
    assert "35" in row3["running-time"]
    assert "15 Вт" in row10["power"]
    # RU sa3fqu / sa10fqu: motor 55 dB(A), spring return 62 dB(A).
    assert row3["noise"].startswith("макс. 55 дБ(А)")
    assert "62 дБ(А)" in row3["noise"]
    assert row10["noise"].startswith("макс. 55 дБ(А)")
    assert "62 дБ(А)" in row10["noise"]


@pytest.mark.django_db
def test_safqu_enrichment_writes_running_time() -> None:
    Category.objects.create(
        name="Противопожарные",
        slug="elektroprivody-protivopozharnye-i-dymovye",
    )
    apply_safqu_enrichment(dry_run=False)
    sku = SKU.objects.get(sku_code="SA3FQU24-DS")
    rt = AttributeValue.objects.get(sku=sku, attribute__slug="running-time").value
    noise = AttributeValue.objects.get(sku=sku, attribute__slug="noise").value
    humidity = AttributeValue.objects.get(sku=sku, attribute__slug="humidity").value
    assert "35" in rt
    assert noise.startswith("макс. 55 дБ(А)")
    assert humidity.startswith("5…95 %")
    product = Product.objects.get(slug="privod-protivopozharniy-safqu-3nm")
    assert product.skus.count() == 4
