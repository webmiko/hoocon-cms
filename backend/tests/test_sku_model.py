"""Tests for catalog.SKU model (TDD: red → green → refactor).

Spec: ПЛАН §6 Iter 1; docs/seo-url-migration.md (slug = старый path, дословно);
docs/data-quality-etl.md §4.1 (sku_code уникален, не пуст; цена число ≥0 или null);
docs/market-analysis.md §6.3 (analog_belimo_code — задел для AnalogMap P1).

SKU = конкретная модель (напр. «HVA-5NM»), продаётся как единица каталога.
Цена хранится, но в публичный API не утекает (Slice 9 + SiteSettings).
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError
from django.db.models import ProtectedError


@pytest.mark.django_db
def test_create_sku_with_product_and_slug() -> None:
    """Can create a SKU linked to a Product with a canonical slug."""
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="Воздушные", slug="vozdushnie")
    product = Product.objects.create(name="HVA", slug="hva", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="Привод воздушный HVA 5NM",
        slug="privod-vozdushniy-hva-5nm",
        sku_code="HVA-5NM",
    )
    assert sku.pk is not None
    assert sku.product_id == product.pk
    assert sku.sku_code == "HVA-5NM"


@pytest.mark.django_db
def test_sku_slug_must_be_unique() -> None:
    """Duplicate slug raises IntegrityError (URL path collision)."""
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="C", slug="c")
    product = Product.objects.create(name="P", slug="p", category=cat)
    SKU.objects.create(product=product, name="A", slug="dup", sku_code="A1")
    with pytest.raises(IntegrityError):
        SKU.objects.create(product=product, name="B", slug="dup", sku_code="B1")


@pytest.mark.django_db
def test_sku_code_must_be_unique() -> None:
    """Duplicate sku_code raises IntegrityError (article must be unique)."""
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="C", slug="c")
    product = Product.objects.create(name="P", slug="p", category=cat)
    SKU.objects.create(product=product, name="A", slug="a", sku_code="DUP")
    with pytest.raises(IntegrityError):
        SKU.objects.create(product=product, name="B", slug="b", sku_code="DUP")


@pytest.mark.django_db
def test_sku_requires_product() -> None:
    """product is NOT NULL — SKU cannot exist without a product line."""
    from catalog.models import SKU

    with pytest.raises(IntegrityError):
        SKU.objects.create(name="Orphan", slug="orphan", sku_code="X")


@pytest.mark.django_db
def test_analog_belimo_code_is_optional() -> None:
    """analog_belimo_code is nullable (задел for AnalogMap P1, not all SKUs have it)."""
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="C", slug="c")
    product = Product.objects.create(name="P", slug="p", category=cat)
    sku = SKU.objects.create(product=product, name="S", slug="s", sku_code="S1")
    assert sku.analog_belimo_code is None


@pytest.mark.django_db
def test_analog_belimo_code_can_be_set() -> None:
    """analog_belimo_code can be set (e.g., 'LMV-5NM' for a Hoocon SKU)."""
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="C", slug="c")
    product = Product.objects.create(name="P", slug="p", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="S",
        slug="s",
        sku_code="S1",
        analog_belimo_code="LMV-5NM",
    )
    assert sku.analog_belimo_code == "LMV-5NM"


@pytest.mark.django_db
def test_price_can_be_null() -> None:
    """price is nullable (скрытые цены — по запросу; null = нет цены в БД)."""
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="C", slug="c")
    product = Product.objects.create(name="P", slug="p", category=cat)
    sku = SKU.objects.create(product=product, name="S", slug="s", sku_code="S1")
    assert sku.price is None


@pytest.mark.django_db
def test_price_can_be_set() -> None:
    """price can be set as a decimal (для КП менеджеру)."""
    from decimal import Decimal

    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="C", slug="c")
    product = Product.objects.create(name="P", slug="p", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="S",
        slug="s",
        sku_code="S1",
        price=Decimal("1250.00"),
    )
    assert sku.price == Decimal("1250.00")


@pytest.mark.django_db
def test_default_is_published_is_true() -> None:
    """Default is_published is True (SKU visible in catalog on creation)."""
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="C", slug="c")
    product = Product.objects.create(name="P", slug="p", category=cat)
    sku = SKU.objects.create(product=product, name="S", slug="s", sku_code="S1")
    assert sku.is_published is True


@pytest.mark.django_db
def test_str_returns_name() -> None:
    """__str__ returns the SKU name for Admin."""
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="C", slug="c")
    product = Product.objects.create(name="P", slug="p", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="Привод HVA 5NM",
        slug="hva-5nm",
        sku_code="HVA-5NM",
    )
    assert str(sku) == "Привод HVA 5NM"


@pytest.mark.django_db
def test_product_delete_protected_when_sku_exists() -> None:
    """on_delete=PROTECT: cannot delete a product that has SKUs."""
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="C", slug="c")
    product = Product.objects.create(name="P", slug="p", category=cat)
    SKU.objects.create(product=product, name="S", slug="s", sku_code="S1")
    with pytest.raises(ProtectedError):
        product.delete()
