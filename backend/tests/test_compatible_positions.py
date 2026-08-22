"""Tests for adapter ↔ brass 8100 compatible_positions cross-links."""

from __future__ import annotations

import pytest
from django.urls import reverse

from catalog.compatible_positions import (
    bracket_uses_adapter,
    compatible_positions_for_sku,
    exact_adapter_sku_code,
)
from catalog.etl.attr_write import set_sku_attribute
from catalog.models import SKU, Category, Product


def test_bracket_uses_adapter_substring_safe() -> None:
    assert bracket_uses_adapter("BR-ML", "BR-ML") is True
    assert bracket_uses_adapter("BR-ML", "BR-M") is False
    assert bracket_uses_adapter("BR-M", "BR-M") is True
    assert bracket_uses_adapter("BR-M / BR-ML (для DA5FU)", "BR-M") is True
    assert bracket_uses_adapter("BR-M / BR-ML (для DA5FU)", "BR-ML") is True


def test_exact_adapter_sku_code_for_catalog_q() -> None:
    assert exact_adapter_sku_code("BR-M") == "BR-M"
    assert exact_adapter_sku_code("br-m") == "BR-M"
    assert exact_adapter_sku_code("BR-ML") == "BR-ML"
    assert exact_adapter_sku_code("BR-M ") == "BR-M"
    assert exact_adapter_sku_code("HVA-5") is None
    assert exact_adapter_sku_code("") is None


def _make_category(slug: str, name: str) -> Category:
    return Category.objects.create(name=name, slug=slug)


def _make_sku(
    *,
    category: Category,
    product_slug: str,
    sku_slug: str,
    sku_code: str,
    name: str | None = None,
) -> SKU:
    product = Product.objects.create(
        name=name or sku_code,
        slug=product_slug,
        category=category,
    )
    return SKU.objects.create(
        product=product,
        name=name or sku_code,
        slug=sku_slug,
        sku_code=sku_code,
        is_published=True,
    )


@pytest.mark.django_db
def test_compatible_positions_adapter_br_m_drives_and_valves() -> None:
    adapters = _make_category("adaptery", "Адаптеры")
    drives = _make_category("elektroprivody", "Электроприводы")
    valves = _make_category("sharovye-krany", "Шаровые краны")

    br_m = _make_sku(
        category=adapters,
        product_slug="adapter-br-m",
        sku_slug="adapter-br-m",
        sku_code="BR-M",
    )
    _make_sku(
        category=adapters,
        product_slug="adapter-br-ml",
        sku_slug="adapter-br-ml",
        sku_code="BR-ML",
    )
    _make_sku(
        category=drives,
        product_slug="da4mu",
        sku_slug="da4mu24-d",
        sku_code="DA4MU24-D",
    )
    _make_sku(
        category=drives,
        product_slug="da5fu",
        sku_slug="da5fu24-d",
        sku_code="DA5FU24-D",
    )
    _make_sku(
        category=drives,
        product_slug="da4mu-230",
        sku_slug="da4mu230-d",
        sku_code="DA4MU230-D",
    )

    valve_both = _make_sku(
        category=valves,
        product_slug="8100-bv220",
        sku_slug="8100-bv220a",
        sku_code="8100-BV220A",
    )
    set_sku_attribute(
        valve_both,
        slug="bracket",
        name="Кронштейн",
        value="BR-M / BR-ML (для DA5FU)",
    )
    valve_m_only = _make_sku(
        category=valves,
        product_slug="8100-bv250",
        sku_slug="8100-bv250a",
        sku_code="8100-BV250A",
    )
    set_sku_attribute(
        valve_m_only,
        slug="bracket",
        name="Кронштейн",
        value="BR-M",
    )

    rows = compatible_positions_for_sku(br_m)
    roles = {r["role"] for r in rows}
    assert roles == {"drive", "valve"}
    drive_codes = {r["sku_code"] for r in rows if r["role"] == "drive"}
    assert any(code.startswith("DA4MU") for code in drive_codes)
    assert not any("FU" in code for code in drive_codes)

    valve_codes = {r["sku_code"] for r in rows if r["role"] == "valve"}
    assert valve_codes == {"8100-BV220A", "8100-BV250A"}


@pytest.mark.django_db
def test_compatible_positions_adapter_br_ml_only_fu_and_ml_valves() -> None:
    adapters = _make_category("adaptery", "Адаптеры")
    drives = _make_category("elektroprivody", "Электроприводы")
    valves = _make_category("sharovye-krany", "Шаровые краны")

    br_ml = _make_sku(
        category=adapters,
        product_slug="adapter-br-ml",
        sku_slug="adapter-br-ml",
        sku_code="BR-ML",
    )
    _make_sku(
        category=drives,
        product_slug="da3fu",
        sku_slug="da3fu24-ds",
        sku_code="DA3FU24-DS",
    )
    _make_sku(
        category=drives,
        product_slug="da5fu",
        sku_slug="da5fu24-d",
        sku_code="DA5FU24-D",
    )
    _make_sku(
        category=drives,
        product_slug="da6mu",
        sku_slug="da6mu24-d",
        sku_code="DA6MU24-D",
    )
    valve_both = _make_sku(
        category=valves,
        product_slug="8100-bv220",
        sku_slug="8100-bv220a",
        sku_code="8100-BV220A",
    )
    set_sku_attribute(
        valve_both,
        slug="bracket",
        name="Кронштейн",
        value="BR-M / BR-ML (для DA5FU)",
    )
    valve_m_only = _make_sku(
        category=valves,
        product_slug="8100-bv250",
        sku_slug="8100-bv250a",
        sku_code="8100-BV250A",
    )
    set_sku_attribute(
        valve_m_only,
        slug="bracket",
        name="Кронштейн",
        value="BR-M",
    )

    rows = compatible_positions_for_sku(br_ml)
    drive_codes = {r["sku_code"] for r in rows if r["role"] == "drive"}
    valve_codes = {r["sku_code"] for r in rows if r["role"] == "valve"}
    assert drive_codes == {"DA5FU24-D"}
    assert valve_codes == {"8100-BV220A"}


@pytest.mark.django_db
def test_compatible_positions_valve_lists_brackets() -> None:
    adapters = _make_category("adaptery", "Адаптеры")
    valves = _make_category("sharovye-krany", "Шаровые краны")
    _make_sku(
        category=adapters,
        product_slug="adapter-br-m",
        sku_slug="adapter-br-m",
        sku_code="BR-M",
    )
    _make_sku(
        category=adapters,
        product_slug="adapter-br-ml",
        sku_slug="adapter-br-ml",
        sku_code="BR-ML",
    )
    valve = _make_sku(
        category=valves,
        product_slug="8100-bv220",
        sku_slug="8100-bv220a",
        sku_code="8100-BV220A",
    )
    set_sku_attribute(
        valve,
        slug="bracket",
        name="Кронштейн",
        value="BR-M / BR-ML (для DA5FU)",
    )

    rows = compatible_positions_for_sku(valve)
    assert [r["role"] for r in rows] == ["bracket", "bracket"]
    assert [r["sku_code"] for r in rows] == ["BR-M", "BR-ML"]


@pytest.mark.django_db
def test_compatible_positions_empty_for_plain_drive() -> None:
    drives = _make_category("elektroprivody", "Электроприводы")
    sku = _make_sku(
        category=drives,
        product_slug="da6mu",
        sku_slug="da6mu24-d",
        sku_code="DA6MU24-D",
    )
    assert compatible_positions_for_sku(sku) == []


@pytest.mark.django_db
def test_sku_detail_api_exposes_compatible_positions(client) -> None:
    adapters = _make_category("adaptery", "Адаптеры")
    valves = _make_category("sharovye-krany", "Шаровые краны")
    br_m = _make_sku(
        category=adapters,
        product_slug="adapter-br-m",
        sku_slug="adapter-br-m",
        sku_code="BR-M",
    )
    valve = _make_sku(
        category=valves,
        product_slug="8100-bv250",
        sku_slug="8100-bv250a",
        sku_code="8100-BV250A",
    )
    set_sku_attribute(
        valve,
        slug="bracket",
        name="Кронштейн",
        value="BR-M",
    )

    response = client.get(reverse("catalog-sku-detail", kwargs={"slug": br_m.slug}))
    assert response.status_code == 200
    rows = response.data["compatible_positions"]
    assert any(r["role"] == "valve" and r["sku_code"] == "8100-BV250A" for r in rows)
    assert all({"role", "name", "slug", "sku_code", "category_slug", "image"} <= r.keys() for r in rows)
