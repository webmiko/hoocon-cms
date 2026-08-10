"""Tests for ensure_ai_catalog_gaps (2022 AI album missing tiles)."""

from __future__ import annotations

import pytest

from catalog.etl.ensure_ai_catalog_gaps import ensure_ai_catalog_gaps
from catalog.models import SKU, Category, Product


@pytest.mark.django_db
def test_ensure_ai_catalog_gaps_creates_missing_families() -> None:
    """DAMQU / SA7MU / HVD-40 products and editions appear (not DAEU)."""
    Category.objects.create(
        name="MQU",
        slug="elektroprivody-uskorennye-bez-pruzhinnogo-vozvrata",
    )
    Category.objects.create(
        name="SAMU",
        slug="elektroprivody-dlya-klapanov-dymoudaleniya",
    )
    Category.objects.create(
        name="Air",
        slug="elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata",
    )

    summary = ensure_ai_catalog_gaps(dry_run=False)
    assert summary["products_created"] == 6  # 4 MQU + SA7 + HVD40
    assert summary["skus_created"] == 40  # 32 + 4 + 4

    assert Product.objects.filter(slug="privod-vozdushniy-da5mqu-5nm").exists()
    assert Product.objects.filter(slug="privod-vozdushniy-da8mqu-8nm").exists()
    assert Product.objects.filter(slug="privod-vozdushniy-da16mqu-16nm").exists()
    assert Product.objects.filter(slug="privod-vozdushniy-da24mqu-24nm").exists()
    assert not Product.objects.filter(slug="privod-vozdushniy-da10mqu-10nm").exists()
    assert not Product.objects.filter(slug__icontains="daeu").exists()
    assert Product.objects.filter(slug="privod-dimoudaleniya-7nm").exists()
    assert Product.objects.filter(slug="privod-vozdushniy-hvd-40nm").exists()

    assert SKU.objects.filter(sku_code__iexact="DA5MQU24-DS").exists()
    assert SKU.objects.filter(sku_code__iexact="DA8MQU24-A").exists()
    assert SKU.objects.filter(sku_code__iexact="DA24MQU230-A").exists()
    assert not SKU.objects.filter(sku_code__iexact="DA20MQU230-A").exists()
    assert not SKU.objects.filter(sku_code__iregex=r"(?i)^da\d+eu").exists()
    assert SKU.objects.filter(sku_code__iexact="SA7MU24-DST").exists()
    assert SKU.objects.filter(sku_code__iexact="HVD24S-40").exists()

    again = ensure_ai_catalog_gaps(dry_run=False)
    assert again["products_created"] == 0
    assert again["skus_created"] == 0
