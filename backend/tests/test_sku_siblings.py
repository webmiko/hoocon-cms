"""Tests for SKU siblings / variant axes helpers."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from catalog.models import SKU, Category, Product
from catalog.siblings import siblings_for_sku, variant_axes_from_siblings


@pytest.mark.django_db
def test_siblings_for_h8101_family_product() -> None:
    cat = Category.objects.create(name="Комплекты", slug="komplekty")
    product = Product.objects.create(name="H8101", slug="h8101", category=cat)
    for code in ("H8101-BV215A-24A", "H8101-BV215A-24AS", "H8101-BV265-24A"):
        SKU.objects.create(
            product=product,
            name=code,
            slug=f"h8101-{code.lower()}",
            sku_code=code,
            is_published=True,
        )
    sku = SKU.objects.get(sku_code="H8101-BV215A-24A")
    rows = siblings_for_sku(sku)
    assert len(rows) == 3
    axes = variant_axes_from_siblings(rows)
    assert "24" in axes["voltage"]
    assert "A" in axes["control"] and "AS" in axes["control"]
    assert "15" in axes["dn"]


@pytest.mark.django_db
def test_sku_detail_exposes_siblings() -> None:
    cat = Category.objects.create(name="Комплекты", slug="komplekty")
    product = Product.objects.create(name="H8103", slug="h8103", category=cat)
    for code in ("H8103-BV265-24A", "H8103-BV265-24AS"):
        SKU.objects.create(
            product=product,
            name=code,
            slug=f"h8103-{code.lower()}",
            sku_code=code,
            is_published=True,
            stock_qty=4 if code.endswith("-24A") else 0,
            stock_qty_ma=2 if code.endswith("-24A") else 0,
        )
    client = APIClient()
    resp = client.get("/api/catalog/skus/h8103-h8103-bv265-24a/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["in_stock_ma"] is True
    assert len(data["siblings"]) == 2
    assert data["variant_axes"]["control"]
    by_code = {row["sku_code"]: row for row in data["siblings"]}
    assert by_code["H8103-BV265-24A"]["in_stock"] is True
    assert by_code["H8103-BV265-24A"]["in_stock_ma"] is True
    assert by_code["H8103-BV265-24AS"]["in_stock_ma"] is False
    assert "stock_qty_ma" not in data
    assert "stock_qty_ma" not in data["siblings"][0]


@pytest.mark.django_db
def test_siblings_for_brass_8100_bv_dn_card() -> None:
    """One Product per DN; siblings expose Kvs editions (8100-bv215a…)."""
    cat = Category.objects.create(name="Шаровые краны", slug="sharovye-krany")
    product = Product.objects.create(
        name="BV215",
        slug="8100-bv215",
        category=cat,
    )
    for code, slug in (
        ("8100-bv215a", "8100-bv215-8100-bv215a"),
        ("8100-bv215b", "8100-bv215-8100-bv215b"),
        ("8100-bv215c", "8100-bv215-8100-bv215c"),
    ):
        SKU.objects.create(
            product=product,
            name=code,
            slug=slug,
            sku_code=code,
            is_published=True,
        )
    sku = SKU.objects.get(sku_code="8100-bv215a")
    rows = siblings_for_sku(sku)
    assert len(rows) == 3
    axes = variant_axes_from_siblings(rows)
    assert axes["dn"] == ["15"]
    assert "1,6" in axes["kvs"] and "2,5" in axes["kvs"]
    assert axes["ways"] == ["2-ходовый"]
    assert not axes["voltage"]
