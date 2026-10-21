"""Tests for DA..FQU fast spring-return series copy."""

from __future__ import annotations

import pytest

from catalog.etl.series_copy_dafqu import apply_dafqu_enrichment, ensure_dafqu_catalog
from catalog.models import SKU, AttributeValue, Category


@pytest.mark.django_db
def test_ensure_dafqu_catalog_creates_da10fqu_editions() -> None:
    Category.objects.create(
        name="Пружина",
        slug="elektroprivody-s-pruzhinnym-vozvratom",
    )
    stats = ensure_dafqu_catalog(dry_run=False)
    assert stats["products_created"] == 1
    assert stats["skus_created"] == 4
    assert SKU.objects.filter(sku_code="DA10FQU24-DS").exists()


@pytest.mark.django_db
def test_dafqu_enrichment_power_from_en_manual() -> None:
    """DA10FQU EN: 15 W nominal / 3 W holding."""
    Category.objects.create(
        name="Пружина",
        slug="elektroprivody-s-pruzhinnym-vozvratom",
    )
    apply_dafqu_enrichment(dry_run=False)
    sku = SKU.objects.get(sku_code="DA10FQU230-D")
    by_slug = {
        av.attribute.slug: av.value for av in AttributeValue.objects.filter(sku=sku).select_related("attribute")
    }
    assert "15 Вт" in by_slug["power-consumption"]
    assert "3 Вт" in by_slug["power-consumption"]
    # RU da10fqu-d-ds.html: motor 55 dB(A), round shaft from 8 mm, square from 6×6.
    assert by_slug["noise"].startswith("макс. 55 дБ(А)")
    assert by_slug["shaft-diameter"] == "круглый 8…21 мм, квадратный 6×6…15×15 мм"
