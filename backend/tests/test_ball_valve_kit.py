"""Tests for ball-valve RFQ kit options."""

from __future__ import annotations

import pytest

from catalog.ball_valve_kit import (
    build_ball_valve_kit_options,
    is_ball_valve_sku,
    parse_drive_families,
    resolve_bracket_for_drive,
)
from catalog.etl.attr_write import set_sku_attribute
from catalog.models import SKU, Category, Product


def test_parse_drive_families_from_compatible_actuators_text() -> None:
    text = "DA5FU24, DA6MU24 (−D/−DS/−A/−AS)"
    assert parse_drive_families(text) == ["DA5FU24", "DA6MU24"]


def test_resolve_bracket_for_drive_fu_vs_mu() -> None:
    assert resolve_bracket_for_drive("DA5FU24") == "BR-ML"
    assert resolve_bracket_for_drive("DA6MU24") == "BR-M"


def test_is_ball_valve_sku_via_product_when_category_missing() -> None:
    """Incomplete category chain still matches known BV product slugs."""
    product = Product(name="BV220", slug="sharovoy-kran-bv220", category=None)
    sku = SKU(product=product, name="BV220A", slug="8100-bv220a", sku_code="8100-BV220A")
    assert is_ball_valve_sku(sku) is True


def test_is_ball_valve_sku_false_without_product_or_category() -> None:
    sku = SKU(product=None, name="X", slug="x", sku_code="X")
    assert is_ball_valve_sku(sku) is False


@pytest.mark.django_db
def test_build_ball_valve_kit_options_for_bv_sku() -> None:
    cat = Category.objects.create(name="Шаровые краны", slug="sharovye-krany")
    product = Product.objects.create(
        name="BV220",
        slug="sharovoy-kran-bv220",
        category=cat,
    )
    sku = SKU.objects.create(
        product=product,
        name="BV220A",
        slug="8100-bv220a",
        sku_code="8100-BV220A",
        is_published=True,
    )
    set_sku_attribute(
        sku,
        slug="compatible-actuators",
        value="DA5FU24, DA6MU24 (−D/−DS/−A/−AS)",
        name="Совместимый привод",
        unit="",
    )

    options = build_ball_valve_kit_options(sku)
    assert options is not None
    assert options["drive_families"] == ["DA5FU24", "DA6MU24"]
    assert options["suffixes"] == ["-D", "-DS", "-A", "-AS"]
    assert options["bracket_by_drive"] == {
        "DA5FU24": "BR-ML",
        "DA6MU24": "BR-M",
    }
    assert "BR-ML" in options["bracket_hint"]


@pytest.mark.django_db
def test_build_ball_valve_kit_options_none_for_h81_kit() -> None:
    """Complete H8103 kits do not expose the brass RFQ drive picker."""
    cat = Category.objects.create(name="Шаровые краны", slug="sharovye-krany")
    product = Product.objects.create(
        name="H8103-BV265",
        slug="sharovoy-kran-h8103-bv265",
        category=cat,
    )
    sku = SKU.objects.create(
        product=product,
        name="H8103-BV265",
        slug="sharovoy-kran-h8103-bv265-h8103-bv265-24a",
        sku_code="H8103-BV265-24A",
        is_published=True,
    )
    set_sku_attribute(
        sku,
        slug="compatible-actuators",
        value="DA16MU24 (−D/−DS/−A/−AS)",
        name="Совместимый привод",
        unit="",
    )
    assert build_ball_valve_kit_options(sku) is None


@pytest.mark.django_db
def test_build_ball_valve_kit_options_none_for_actuator() -> None:
    cat = Category.objects.create(name="Воздушные", slug="elektroprivody-vozdushnye")
    product = Product.objects.create(name="DA5", slug="p-da5", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="DA5",
        slug="da5-sku",
        sku_code="DA5MU24",
        is_published=True,
    )
    assert build_ball_valve_kit_options(sku) is None
