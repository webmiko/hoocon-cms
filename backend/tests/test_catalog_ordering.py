"""Tests for numeric catalog list ordering (moment + sku_code digits)."""

from __future__ import annotations

import pytest
from django.db import connection

from catalog.models import SKU, Attribute, AttributeValue, Category, Product
from catalog.ordering import annotate_moment_nm, catalog_list_order_by
from catalog.series_categories import spec_order_case

pytestmark = pytest.mark.django_db


def _sku(code: str, *, category: Category, moment: str | None) -> SKU:
    product, _ = Product.objects.get_or_create(
        slug=f"prod-{code.lower()}",
        defaults={"name": code, "category": category},
    )
    if product.category_id != category.pk:
        product.category = category
        product.save(update_fields=["category"])
    sku = SKU.objects.create(
        product=product,
        sku_code=code,
        name=code,
        slug=code.lower(),
        is_published=True,
    )
    if moment is not None:
        attr, _ = Attribute.objects.get_or_create(
            slug="moment",
            defaults={"name": "Крутящий момент", "unit": "Нм"},
        )
        AttributeValue.objects.create(sku=sku, attribute=attr, value=moment)
    return sku


@pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="REGEXP_REPLACE ordering requires Postgres",
)
def test_catalog_order_moment_numeric_not_lexicographic() -> None:
    """da10… must follow da3… when sorted by Нм, not by sku_code text."""
    cat = Category.objects.create(
        slug="elektroprivody-s-pruzhinnym-vozvratom",
        name="Пружина",
    )
    _sku("da10fu24-d", category=cat, moment="10 Нм")
    _sku("da3fu24-d", category=cat, moment="3 Нм")
    _sku("da5fu24-d", category=cat, moment="5 Нм")

    codes = list(
        annotate_moment_nm(
            SKU.objects.filter(is_published=True).annotate(
                category_spec_order=spec_order_case(
                    slug_field="product__category__slug",
                ),
            ),
        )
        .order_by(*catalog_list_order_by())
        .values_list("sku_code", flat=True),
    )
    assert codes == ["da3fu24-d", "da5fu24-d", "da10fu24-d"]


@pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="REGEXP_REPLACE ordering requires Postgres",
)
def test_catalog_order_sku_code_nm_for_ball_valves() -> None:
    """Without moment, DN digits in sku_code sort numerically (bv32 before bv215)."""
    cat = Category.objects.create(slug="sharovye-krany", name="Краны")
    _sku("8100-bv215a", category=cat, moment=None)
    _sku("8100-bv32a", category=cat, moment=None)

    codes = list(
        annotate_moment_nm(
            SKU.objects.filter(is_published=True).annotate(
                category_spec_order=spec_order_case(
                    slug_field="product__category__slug",
                ),
            ),
        )
        .order_by(*catalog_list_order_by())
        .values_list("sku_code", flat=True),
    )
    assert codes == ["8100-bv32a", "8100-bv215a"]
