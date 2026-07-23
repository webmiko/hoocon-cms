"""Unit tests for nested catalog URL helpers."""

from __future__ import annotations

from catalog.urls_paths import (
    catalog_category_path,
    catalog_path_for_sku,
    catalog_sku_path,
)


def test_catalog_category_path() -> None:
    assert catalog_category_path("sharovye-krany") == "/catalog/sharovye-krany"
    assert catalog_category_path("") == "/catalog"
    assert catalog_category_path("/x/") == "/catalog/x"


def test_catalog_sku_path() -> None:
    assert (
        catalog_sku_path("sharovye-krany", "sharovoy-kran-bv215-8100-bv215a")
        == "/catalog/sharovye-krany/sharovoy-kran-bv215-8100-bv215a"
    )
    assert catalog_sku_path("", "sku") == "/catalog"
    assert catalog_sku_path("cat", "") == "/catalog"


def test_catalog_path_for_sku_uses_related_category() -> None:
    class Cat:
        slug = "sharovye-krany"

    class Prod:
        category = Cat()

    class Sku:
        slug = "sharovoy-kran-bv215-8100-bv215a"
        product = Prod()

    assert catalog_path_for_sku(Sku()) == "/catalog/sharovye-krany/sharovoy-kran-bv215-8100-bv215a"
