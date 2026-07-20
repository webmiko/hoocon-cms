"""Tests for shared catalog ETL Attribute writers (audit P3-2)."""

from __future__ import annotations

import pytest

from catalog.etl.attr_write import ensure_attribute, set_sku_attribute
from catalog.models import SKU, Attribute, AttributeValue, Category, Product


@pytest.mark.django_db
def test_ensure_attribute_creates_and_syncs_name_unit() -> None:
    """ensure_attribute upserts by slug and syncs drifted name/unit."""
    attr = ensure_attribute("moment", "Крутящий момент", "Нм")
    assert attr.slug == "moment"
    assert Attribute.objects.filter(slug="moment").count() == 1

    same = ensure_attribute("moment", "Момент", "Н·м")
    assert same.pk == attr.pk
    same.refresh_from_db()
    assert same.name == "Момент"
    assert same.unit == "Н·м"


@pytest.mark.django_db
def test_set_sku_attribute_upserts_value() -> None:
    """set_sku_attribute writes AttributeValue and updates on repeat."""
    cat = Category.objects.create(name="C", slug="c-attr")
    product = Product.objects.create(name="P", slug="p-attr", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="S",
        slug="s-attr",
        sku_code="ATTR-1",
    )
    set_sku_attribute(sku, slug="voltage", value="230 В", name="Напряжение", unit="В")
    assert AttributeValue.objects.filter(sku=sku, attribute__slug="voltage").count() == 1
    set_sku_attribute(sku, slug="voltage", value="24 В", name="Напряжение", unit="В")
    av = AttributeValue.objects.get(sku=sku, attribute__slug="voltage")
    assert av.value == "24 В"
