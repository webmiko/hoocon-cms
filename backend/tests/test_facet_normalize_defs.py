"""Coverage tests for facet normalize + Attribute↔facet matching."""

from __future__ import annotations

import pytest

from catalog.facets.defs import (
    FACET_BY_KEY,
    attribute_ids_for_facet,
    attribute_matches_facet,
)
from catalog.facets.normalize import (
    _looks_like_area_value,
    normalize_area_attribute_value,
    normalize_facet_value,
    values_match,
)
from catalog.models import Attribute


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", ""),
        ("0,5 м²", "до 0,5 м²"),
        ("< 0,5 м²", "до 0,5 м²"),
        ("до 0,5", "до 0,5 м²"),
        ("3, 2 м²", "до 3,2 м²"),
        ("1 м²", "до 1,0 м²"),
        ("weird m2 note", "до weird м² note"),
    ],
)
def test_normalize_area_attribute_value(raw: str, expected: str) -> None:
    """Damper area chips collapse to ``до N м²``."""
    assert normalize_area_attribute_value(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", False),
        ("0,5 м²", True),
        ("до 1", True),
        ("момент", False),
    ],
)
def test_looks_like_area_value(raw: str, expected: bool) -> None:
    """Area heuristic for EAV matching."""
    assert _looks_like_area_value(raw) is expected


def test_normalize_facet_value_routes_keys() -> None:
    """Area / empty passthrough via normalize_facet_value."""
    assert normalize_facet_value("area", "0,5 м²") == "до 0,5 м²"
    assert normalize_facet_value("moment", "") == ""


def test_values_match_area_and_raw() -> None:
    """Equality after normalization for area and numeric cores."""
    assert values_match("0,5 м²", "до 0,5 м²")
    assert values_match("10 Нм", "10")
    assert not values_match("5", "10")
    assert not values_match("", "x")


@pytest.mark.django_db
def test_attribute_matches_facet_exclusions_and_legacy() -> None:
    """Control/voltage/material exclusions; legacy slug; power-as-moment."""
    control = Attribute.objects.create(
        name="Управляющий сигнал Y",
        slug="control-signal",
        unit="",
    )
    assert not attribute_matches_facet(control, FACET_BY_KEY["control"])

    voltage_range = Attribute.objects.create(
        name="Диапазон напряжения",
        slug="voltage-range",
        unit="",
    )
    assert not attribute_matches_facet(voltage_range, FACET_BY_KEY["voltage"])

    material = Attribute.objects.create(
        name="Материал шара и штока",
        slug="ball-stem-material",
        unit="",
    )
    assert not attribute_matches_facet(material, FACET_BY_KEY["material"])

    kvs = Attribute.objects.create(name="Kvs", slug="kvs-3", unit="")
    assert attribute_matches_facet(kvs, FACET_BY_KEY["kvs"])

    power_nm = Attribute.objects.create(name="Мощность", slug="power-nm", unit="Нм")
    assert attribute_matches_facet(power_nm, FACET_BY_KEY["moment"])

    voltage = Attribute.objects.create(name="Напряжение", slug="voltage", unit="В")
    assert attribute_matches_facet(voltage, FACET_BY_KEY["voltage"])


@pytest.mark.django_db
def test_attribute_ids_for_facet_includes_power_moment() -> None:
    """Moment facet ids include Мощность only when values contain Нм."""
    from catalog.models import SKU, AttributeValue, Category, Product

    Attribute.objects.create(name="Крутящий момент", slug="moment", unit="Нм")
    power = Attribute.objects.create(name="Мощность", slug="power-as-m", unit="")
    power_empty = Attribute.objects.create(name="Мощность", slug="power-w", unit="Вт")
    cat = Category.objects.create(name="C", slug="c-pow")
    product = Product.objects.create(name="P", slug="p-pow", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="S",
        slug="s-pow",
        sku_code="POW1",
    )
    AttributeValue.objects.create(sku=sku, attribute=power, value="5 Нм")
    ids = attribute_ids_for_facet(FACET_BY_KEY["moment"])
    assert power.id in ids
    assert power_empty.id not in ids
    assert len(ids) >= 2
