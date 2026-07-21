"""Tests for ball-valve RFQ kit options."""

from __future__ import annotations

import pytest

from catalog.ball_valve_kit import (
    build_ball_valve_kit_options,
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
