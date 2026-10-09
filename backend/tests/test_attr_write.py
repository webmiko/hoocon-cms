"""Tests for shared catalog ETL Attribute writers (audit P3-2)."""

from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from catalog.etl.attr_write import (
    _ATTR_VALUE_MAX_LEN,
    attribute_cache,
    clear_etl_attributes,
    clip_attribute_value,
    ensure_attribute,
    set_sku_attribute,
)
from catalog.models import SKU, Attribute, AttributeValue, Category, Product


@pytest.mark.django_db
def test_ensure_attribute_creates_and_syncs_to_registry() -> None:
    """ensure_attribute upserts by slug; registered slugs keep the canon label."""
    attr = ensure_attribute("moment", "Крутящий момент", "Нм")
    assert attr.slug == "moment"
    assert Attribute.objects.filter(slug="moment").count() == 1

    Attribute.objects.filter(pk=attr.pk).update(name="Момент", unit="Н·м")
    same = ensure_attribute("moment", "Момент", "Н·м")
    assert same.pk == attr.pk
    same.refresh_from_db()
    assert same.name == "Крутящий момент"
    assert same.unit == "Нм"


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


def _sku(code: str) -> SKU:
    cat, _ = Category.objects.get_or_create(slug="c-attr-batch", defaults={"name": "C"})
    product = Product.objects.create(name=code, slug=code.casefold(), category=cat)
    return SKU.objects.create(product=product, name=code, slug=f"{code.casefold()}-s", sku_code=code)


def _value_selects(ctx: CaptureQueriesContext) -> int:
    return sum(
        1
        for q in ctx.captured_queries
        if q["sql"].lstrip().upper().startswith("SELECT") and '"catalog_attributevalue"' in q["sql"]
    )


@pytest.mark.django_db
def test_rewrite_after_clear_reads_values_once() -> None:
    """L23: после clear_etl_attributes запись N атрибутов SKU шла SELECT-ом на каждую строку."""
    sku = _sku("BATCH-1")
    slugs = [f"spec-{n}" for n in range(10)]
    with attribute_cache():
        for slug in slugs:
            ensure_attribute(slug, slug)
        with CaptureQueriesContext(connection) as ctx:
            clear_etl_attributes(sku)
            for slug in slugs:
                set_sku_attribute(sku, slug=slug, value="1", name=slug)
            set_sku_attribute(sku, slug=slugs[0], value="2", name=slugs[0])

    assert _value_selects(ctx) == 1
    values = dict(AttributeValue.objects.filter(sku=sku).values_list("attribute__slug", "value"))
    assert values == {**dict.fromkeys(slugs, "1"), slugs[0]: "2"}


@pytest.mark.django_db
def test_rewrite_after_clear_keeps_manual_rows_and_scopes_to_last_sku() -> None:
    """L23: снимок после очистки хранит правленные вручную строки и касается только последнего SKU."""
    first, second = _sku("BATCH-A"), _sku("BATCH-B")
    for sku in (first, second):
        set_sku_attribute(sku, slug="voltage", value="24 В", name="Напряжение", unit="В")
    AttributeValue.objects.filter(sku=first).update(is_manual=True, value="230 В")

    with attribute_cache():
        clear_etl_attributes(first)
        assert set_sku_attribute(first, slug="voltage", value="24 В", name="Напряжение", unit="В") is False
        clear_etl_attributes(second)
        AttributeValue.objects.filter(sku=first).update(is_manual=False)
        assert set_sku_attribute(first, slug="voltage", value="12 В", name="Напряжение", unit="В") is True
        assert set_sku_attribute(second, slug="voltage", value="12 В", name="Напряжение", unit="В") is True

    assert AttributeValue.objects.get(sku=first).value == "12 В"
    assert AttributeValue.objects.get(sku=second).value == "12 В"
