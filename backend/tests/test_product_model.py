"""Tests for catalog.Product model (TDD: red → green → refactor).

Spec: ПЛАН §6 Iter 1; docs/readiness-backend-ux.md §2.2 —
Product (FK Category, slug unique). Product = линейка/серия (напр. «HVA»),
SKU = конкретная модель (напр. «HVA-5NM»). on_delete=PROTECT — нельзя
удалить категорию с товарами (защита от потери каталога).
"""

from __future__ import annotations

import pytest
from django.db import IntegrityError
from django.db.models import ProtectedError


@pytest.mark.django_db
def test_create_product_with_category() -> None:
    """Can create a Product linked to a Category."""
    from catalog.models import Category, Product

    category = Category.objects.create(name="Воздушные", slug="vozdushnie")
    product = Product.objects.create(
        name="HVA серия",
        slug="hva",
        category=category,
    )
    assert product.pk is not None
    assert product.category_id == category.pk


@pytest.mark.django_db
def test_product_slug_must_be_unique() -> None:
    """Duplicate product slug raises IntegrityError."""
    from catalog.models import Category, Product

    cat = Category.objects.create(name="C", slug="c")
    Product.objects.create(name="A", slug="dup", category=cat)
    with pytest.raises(IntegrityError):
        Product.objects.create(name="B", slug="dup", category=cat)


@pytest.mark.django_db
def test_product_requires_category() -> None:
    """category is NOT NULL — product cannot exist without a category."""
    from catalog.models import Product

    with pytest.raises(IntegrityError):
        Product.objects.create(name="Orphan", slug="orphan")


@pytest.mark.django_db
def test_str_returns_name() -> None:
    """__str__ returns the product name for Admin."""
    from catalog.models import Category, Product

    cat = Category.objects.create(name="C", slug="c")
    product = Product.objects.create(name="HVA серия", slug="hva", category=cat)
    assert str(product) == "HVA серия"


@pytest.mark.django_db
def test_description_is_optional() -> None:
    """Description can be empty."""
    from catalog.models import Category, Product

    cat = Category.objects.create(name="C", slug="c")
    product = Product.objects.create(name="P", slug="p", category=cat)
    assert product.description == ""


@pytest.mark.django_db
def test_category_delete_protected_when_product_exists() -> None:
    """on_delete=PROTECT: cannot delete a category that has products."""
    from catalog.models import Category, Product

    cat = Category.objects.create(name="C", slug="c")
    Product.objects.create(name="P", slug="p", category=cat)
    with pytest.raises(ProtectedError):
        cat.delete()
