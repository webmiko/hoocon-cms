"""Tests for H8205 LAV matrices, variant parse, and enrich smoke."""

from __future__ import annotations

import pytest

from catalog.ball_valve_kit import build_ball_valve_kit_options
from catalog.etl.h8205_lav import (
    all_h8205_series,
    h8205_edition_sku_codes,
    is_h8205_sku_code,
)
from catalog.etl.series_copy_ball_valves import apply_h8205_lav_enrichment
from catalog.etl.sku_variant import parse_sku_variant
from catalog.etl.stock_import import (
    h8205_lav_bare_stock_key,
    normalize_stock_article_key,
)
from catalog.etl.tech_copy import CONTROL_MODBUS, normalize_control_attribute_value
from catalog.facets.aux import AUX_SWITCH_SPDT_2, aux_spdt_count_from_sku
from catalog.models import SKU, AttributeValue, Category, Product
from catalog.series_categories import classify_series_category


@pytest.mark.django_db
def test_h8205_matrix_22_bodies_times_24_editions() -> None:
    """Dimensions table → 22 cards × 24 electrical SKUs = 528 unique codes."""
    series = all_h8205_series()
    assert len(series) == 22
    codes: list[str] = []
    for card in series:
        editions = h8205_edition_sku_codes(card)
        assert len(editions) == 24
        codes.extend(editions)
    assert len(codes) == 528
    assert len(set(codes)) == 528
    assert "H8205-LAV232-24A" in codes
    assert "H8205-LAV280ST-230A" in codes
    assert "H8205-LAV3300T-24M" in codes
    assert series[0].product_slug == "h8205-lav232"


def test_is_h8205_sku_code() -> None:
    assert is_h8205_sku_code("H8205-LAV232-24A")
    assert is_h8205_sku_code("H8205-LAV280ST-230M")
    assert not is_h8205_sku_code("H8101-BV215A-24AS")
    assert not is_h8205_sku_code("8100-bv232a")


def test_parse_sku_variant_h8205() -> None:
    base = parse_sku_variant("H8205-LAV232-24A")
    assert base.voltage == "24"
    assert base.control == "modulating"
    assert base.aux_switch is False
    assert base.fault_alarm is False

    st = parse_sku_variant("H8205-LAV280ST-230A")
    assert st.voltage == "230"
    assert st.control == "modulating"
    assert st.aux_switch is True
    assert st.fault_alarm is True

    modbus = parse_sku_variant("H8205-LAV3100S-24M")
    assert modbus.control == "modbus"
    assert modbus.aux_switch is True
    assert modbus.fault_alarm is False

    on_off = parse_sku_variant("H8205-LAV3300T-24D")
    assert on_off.control == "on_off"
    assert on_off.aux_switch is False
    assert on_off.fault_alarm is True


def test_control_modbus_and_aux_from_h8205() -> None:
    assert normalize_control_attribute_value("x", sku_code="H8205-LAV232-24M") == CONTROL_MODBUS
    assert aux_spdt_count_from_sku("H8205-LAV280ST-230A") == 2
    assert aux_spdt_count_from_sku("H8205-LAV280S-24D") == 2
    assert aux_spdt_count_from_sku("H8205-LAV280T-24A") == 0
    assert aux_spdt_count_from_sku("H8205-LAV280-24A") == 0


def test_classify_h8205_komplekty() -> None:
    assert classify_series_category("h8205-lav232", ["H8205-LAV232-24A"]) == "komplekty"


def test_stock_h8205_not_bv_body() -> None:
    assert normalize_stock_article_key("H8205-LAV232-24A") == "H8205-LAV232-24A"
    assert normalize_stock_article_key("H8205-LAV232-24A") != normalize_stock_article_key(
        "BV232A",
    )
    assert h8205_lav_bare_stock_key("H8205-LAV280ST-230A") == "H8205-LAV280ST"
    assert h8205_lav_bare_stock_key("H8205-LAV280") == "H8205-LAV280"


@pytest.mark.django_db
def test_enrich_h8205_lav232_smoke() -> None:
    """One LAV card seeds 24 SKUs in komplekty with voltage/control/S/T attrs."""
    Category.objects.get_or_create(slug="komplekty", defaults={"name": "Комплекты"})
    lav = next(s for s in all_h8205_series() if s.body == "LAV232")
    stats = apply_h8205_lav_enrichment(lav, attach_pdf=False)
    assert stats["products"] == 1
    assert stats["skus"] == 24

    product = Product.objects.get(slug="h8205-lav232")
    assert product.category.slug == "komplekty"
    assert SKU.objects.filter(product=product, is_published=True).count() == 24

    sku = SKU.objects.get(sku_code="H8205-LAV232ST-230M")
    by_slug = {
        av.attribute.slug: av.value for av in AttributeValue.objects.filter(sku=sku).select_related("attribute")
    }
    assert by_slug["control"] == CONTROL_MODBUS
    assert by_slug["voltage"].startswith("AC 100")
    assert by_slug["aux-switch"] == AUX_SWITCH_SPDT_2
    assert by_slug["fault-alarm"] == "есть"
    assert by_slug["dn"] == "32"
    assert build_ball_valve_kit_options(sku) is None
