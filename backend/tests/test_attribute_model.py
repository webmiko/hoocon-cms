"""Tests for catalog.Attribute + AttributeValue (TDD: red → green → refactor).

Spec: docs/data-quality-etl.md §4.1 — ТТХ (момент, напряжение, пружина…) в
словаре Attribute, не свободная строка. EAV: Attribute = словарь, AttributeValue
= значение для SKU. Фильтры каталога (Slice 9) — exact match по value.
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError
from django.db.models import ProtectedError

# ── Attribute ─────────────────────────────────────────────────────


@pytest.mark.django_db
def test_create_attribute_with_name_slug_unit() -> None:
    """Can create an Attribute (dictionary entry) with name, slug, unit."""
    from catalog.models import Attribute

    attr = Attribute.objects.create(name="Момент", slug="moment", unit="Н·м")
    assert attr.pk is not None
    assert attr.name == "Момент"
    assert attr.slug == "moment"
    assert attr.unit == "Н·м"


@pytest.mark.django_db
def test_attribute_slug_must_be_unique() -> None:
    """Duplicate attribute slug raises IntegrityError."""
    from catalog.models import Attribute

    Attribute.objects.create(name="A", slug="dup", unit="")
    with pytest.raises(IntegrityError):
        Attribute.objects.create(name="B", slug="dup", unit="")


@pytest.mark.django_db
def test_attribute_unit_is_optional() -> None:
    """Unit can be blank (for dimensionless attributes like «пружина: да/нет»)."""
    from catalog.models import Attribute

    attr = Attribute.objects.create(name="Тип пружины", slug="spring_type", unit="")
    assert attr.unit == ""


@pytest.mark.django_db
def test_attribute_str_returns_name() -> None:
    """__str__ returns the attribute name for Admin."""
    from catalog.models import Attribute

    attr = Attribute.objects.create(name="Напряжение", slug="voltage", unit="В")
    assert str(attr) == "Напряжение"


# ── AttributeValue ──────────────────────────────────────────────


@pytest.mark.django_db
def test_create_attribute_value_for_sku() -> None:
    """Can attach an AttributeValue to a SKU."""
    from catalog.models import SKU, Attribute, AttributeValue, Category, Product

    cat = Category.objects.create(name="C", slug="c")
    product = Product.objects.create(name="P", slug="p", category=cat)
    sku = SKU.objects.create(product=product, name="S", slug="s", sku_code="S1")
    attr = Attribute.objects.create(name="Момент", slug="moment", unit="Н·м")
    value = AttributeValue.objects.create(sku=sku, attribute=attr, value="5")
    assert value.pk is not None
    assert value.value == "5"
    assert value.attribute_id == attr.pk
    assert value.sku_id == sku.pk


@pytest.mark.django_db
def test_attribute_value_unique_per_sku() -> None:
    """One value per (sku, attribute) — duplicate raises IntegrityError."""
    from catalog.models import SKU, Attribute, AttributeValue, Category, Product

    cat = Category.objects.create(name="C", slug="c")
    product = Product.objects.create(name="P", slug="p", category=cat)
    sku = SKU.objects.create(product=product, name="S", slug="s", sku_code="S1")
    attr = Attribute.objects.create(name="Момент", slug="moment", unit="Н·м")
    AttributeValue.objects.create(sku=sku, attribute=attr, value="5")
    with pytest.raises(IntegrityError):
        AttributeValue.objects.create(sku=sku, attribute=attr, value="10")


@pytest.mark.django_db
def test_sku_delete_cascades_attribute_values() -> None:
    """on_delete=CASCADE: deleting a SKU deletes its AttributeValues."""
    from catalog.models import SKU, Attribute, AttributeValue, Category, Product

    cat = Category.objects.create(name="C", slug="c")
    product = Product.objects.create(name="P", slug="p", category=cat)
    sku = SKU.objects.create(product=product, name="S", slug="s", sku_code="S1")
    attr = Attribute.objects.create(name="Момент", slug="moment", unit="Н·м")
    AttributeValue.objects.create(sku=sku, attribute=attr, value="5")
    assert AttributeValue.objects.count() == 1
    # Delete SKU via raw SQL-friendly path: bypass PROTECT by deleting SKU directly
    # (SKU has no PROTECT from AttributeValue; AttributeValue cascades).
    sku.delete()
    assert AttributeValue.objects.count() == 0


@pytest.mark.django_db
def test_attribute_delete_protected_when_used() -> None:
    """on_delete=PROTECT: cannot delete an Attribute that has values."""
    from catalog.models import SKU, Attribute, AttributeValue, Category, Product

    cat = Category.objects.create(name="C", slug="c")
    product = Product.objects.create(name="P", slug="p", category=cat)
    sku = SKU.objects.create(product=product, name="S", slug="s", sku_code="S1")
    attr = Attribute.objects.create(name="Момент", slug="moment", unit="Н·м")
    AttributeValue.objects.create(sku=sku, attribute=attr, value="5")
    with pytest.raises(ProtectedError):
        attr.delete()


@pytest.mark.django_db
def test_attribute_value_str_shows_sku_attribute_value() -> None:
    """__str__ shows 'sku_code / attribute_name = value' for Admin readability."""
    from catalog.models import SKU, Attribute, AttributeValue, Category, Product

    cat = Category.objects.create(name="C", slug="c")
    product = Product.objects.create(name="P", slug="p", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="S",
        slug="s",
        sku_code="HVA-5NM",
    )
    attr = Attribute.objects.create(name="Момент", slug="moment", unit="Н·м")
    value = AttributeValue.objects.create(sku=sku, attribute=attr, value="5")
    text = str(value)
    assert "HVA-5NM" in text
    assert "Момент" in text
    assert "5" in text
