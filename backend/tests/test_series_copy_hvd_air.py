"""Tests for bare HVD air enricher and DAEU aux count."""

from __future__ import annotations

import pytest

from catalog.etl.series_copy_hvd_air import TORQUE_SPECS, apply_hvd_air_enrichment
from catalog.facets.aux import aux_spdt_count_from_sku
from catalog.facets.highlights import highlights_for_sku
from catalog.models import SKU, AttributeValue, Category, Product
from catalog.sku_access import sku_attribute_values, sku_category_slug_or_empty


def test_hvd_air_dimensions_match_catalog_2025() -> None:
    """Catalog pp. 39/41/43/45: H×W×D envelopes for HVD air (no spring)."""
    assert TORQUE_SPECS[5]["dimensions"] == "144,1 × 71,1 × 62,1 мм"
    assert TORQUE_SPECS[10]["dimensions"] == "167,8 × 86,2 × 68 мм"
    assert TORQUE_SPECS[20]["dimensions"] == "191,8 × 103,4 × 68 мм"
    assert TORQUE_SPECS[40]["dimensions"] == "198,6 × 110,2 × 68 мм"


def test_aux_spdt_count_daeu_ds_is_two() -> None:
    """DA..EU24-DS album wiring: two auxiliary switches."""
    assert aux_spdt_count_from_sku("DA8EU24-DS") == 2
    assert aux_spdt_count_from_sku("DA16EU24-D") == 0


@pytest.mark.django_db
def test_apply_hvd_air_enrichment_hvd40_highlights() -> None:
    """HVD-40 gets primary card highlights: moment/voltage/control/area/aux."""
    cat = Category.objects.create(
        name="Air",
        slug="elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata",
    )
    product = Product.objects.create(
        category=cat,
        name="old",
        slug="privod-vozdushniy-hvd-40nm",
    )
    plain = SKU.objects.create(
        product=product,
        name="old",
        slug="hvd24-40-test",
        sku_code="HVD24-40",
        is_published=True,
    )
    aux = SKU.objects.create(
        product=product,
        name="old",
        slug="hvd24s-40-test",
        sku_code="HVD24S-40",
        is_published=True,
    )

    stats = apply_hvd_air_enrichment()
    assert stats["skus"] >= 2
    assert stats["attributes"] > 0
    assert AttributeValue.objects.filter(sku=plain, attribute__slug="moment").exists()

    hs_plain = highlights_for_sku(
        sku_attribute_values(plain),
        sku_code=plain.sku_code,
        category_slug=sku_category_slug_or_empty(plain) or None,
    )
    keys = [h["key"] for h in hs_plain]
    assert keys[:4] == ["moment", "voltage", "control", "area"]
    assert hs_plain[0]["value"] == "40 Нм"

    hs_aux = highlights_for_sku(
        sku_attribute_values(aux),
        sku_code=aux.sku_code,
        category_slug=sku_category_slug_or_empty(aux) or None,
    )
    assert any(h["key"] == "aux_switch" and h["value"] == "SPDT-2" for h in hs_aux)
