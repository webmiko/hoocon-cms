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
def test_catalog_order_series_before_moment() -> None:
    """Within a category, DAMU stays contiguous before HVA at overlapping Нм."""
    cat = Category.objects.create(
        slug="elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata",
        name="Без пружины",
    )
    _sku("HVA230S-5", category=cat, moment="5 Нм")
    _sku("DA6MU230-AS", category=cat, moment="6 Нм")
    _sku("DA2MU230-AS", category=cat, moment="2 Нм")
    _sku("HVD230S-5", category=cat, moment="5 Нм")

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
    assert codes == [
        "DA2MU230-AS",
        "DA6MU230-AS",
        "HVA230S-5",
        "HVD230S-5",
    ]


@pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="REGEXP_REPLACE ordering requires Postgres",
)
def test_catalog_order_voltage_24_before_230() -> None:
    """Same series/Nm: 24 V editions before 230 V (not lexicographic sku_code)."""
    cat = Category.objects.create(
        slug="elektroprivody-s-pruzhinnym-vozvratom",
        name="Пружина",
    )
    _sku("da5fu230-d", category=cat, moment="5 Нм")
    _sku("da5fu24-d", category=cat, moment="5 Нм")
    _sku("da5fu24-as", category=cat, moment="5 Нм")

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
    assert codes == ["da5fu24-as", "da5fu24-d", "da5fu230-d"]


@pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="REGEXP_REPLACE ordering requires Postgres",
)
def test_catalog_order_sku_code_nm_for_ball_valves() -> None:
    """Family then DN numeric: BV215→15 before BV232→32; 8100 before 8100Q."""
    cat = Category.objects.create(slug="sharovye-krany", name="Краны")
    _sku("8100q-bv2100", category=cat, moment=None)
    _sku("8100-bv232a", category=cat, moment=None)
    _sku("8100q-bv265", category=cat, moment=None)
    _sku("8100-bv215a", category=cat, moment=None)
    _sku("8100-bv315a", category=cat, moment=None)

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
    assert codes == [
        "8100-bv215a",
        "8100-bv315a",
        "8100-bv232a",
        "8100q-bv265",
        "8100q-bv2100",
    ]


@pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="REGEXP_REPLACE ordering requires Postgres",
)
def test_catalog_order_h8205_by_dn_not_voltage_trail() -> None:
    """H8205 LAV cards sort by body DN (32 before 100), not by -24/-230 trail."""
    cat = Category.objects.create(slug="komplekty", name="Комплекты")
    _sku("H8205-LAV2100-24A", category=cat, moment=None)
    _sku("H8205-LAV232-24A", category=cat, moment=None)
    _sku("H8205-LAV332-24A", category=cat, moment=None)
    _sku("H8205-LAV3100-230A", category=cat, moment=None)

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
    assert codes == [
        "H8205-LAV232-24A",
        "H8205-LAV332-24A",
        "H8205-LAV2100-24A",
        "H8205-LAV3100-230A",
    ]


@pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="REGEXP_REPLACE ordering requires Postgres",
)
def test_catalog_order_h8205_two_way_before_three_at_same_dn() -> None:
    """At equal DN, 2-way H8205 precedes 3-way even if voltages differ."""
    cat = Category.objects.create(slug="komplekty", name="Комплекты")
    _sku("H8205-LAV3300-24A", category=cat, moment=None)
    _sku("H8205-LAV2300-230A", category=cat, moment=None)

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
    assert codes == ["H8205-LAV2300-230A", "H8205-LAV3300-24A"]
