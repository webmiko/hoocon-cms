"""Tests for shared catalog ETL Attribute writers (audit P3-2)."""

from __future__ import annotations

import pytest

from catalog.etl.attr_write import (
    _ATTR_VALUE_MAX_LEN,
    clip_attribute_value,
    ensure_attribute,
    set_sku_attribute,
)
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


def test_attr_value_max_len_matches_model_field() -> None:
    """ETL truncate limit must equal AttributeValue.value max_length."""
    field_max = AttributeValue._meta.get_field("value").max_length
    assert _ATTR_VALUE_MAX_LEN == field_max == 200


def test_clip_attribute_value_matches_set_sku_attribute_limit() -> None:
    """clip_attribute_value is the shared truncate used by load and writers."""
    long_value = "x" * (_ATTR_VALUE_MAX_LEN + 10)
    assert clip_attribute_value(long_value) == long_value[:_ATTR_VALUE_MAX_LEN]
    assert len(clip_attribute_value("short")) == 5


@pytest.mark.django_db
def test_set_sku_attribute_truncates_to_model_max_length() -> None:
    """Values longer than the CharField max_length save without DB error."""
    cat = Category.objects.create(name="C", slug="c-attr-long")
    product = Product.objects.create(name="P", slug="p-attr-long", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="S",
        slug="s-attr-long",
        sku_code="ATTR-LONG",
    )
    long_value = "x" * (_ATTR_VALUE_MAX_LEN + 50)
    set_sku_attribute(
        sku,
        slug="notes",
        value=long_value,
        name="Примечание",
    )
    av = AttributeValue.objects.get(sku=sku, attribute__slug="notes")
    assert len(av.value) == _ATTR_VALUE_MAX_LEN
    assert av.value == long_value[:_ATTR_VALUE_MAX_LEN]
