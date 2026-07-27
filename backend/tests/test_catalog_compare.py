"""Tests for GET /api/catalog/compare/."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.urls import reverse

from catalog.compare import (
    COMPARE_EMPTY_CELL,
    COMPARE_MAX_SKUS,
    build_compare_rows,
    normalize_compare_cell,
    parse_compare_slugs,
)


def _seed_pair():
    from catalog.models import (
        SKU,
        Attribute,
        AttributeValue,
        Category,
        Product,
    )

    cat = Category.objects.create(name="Воздушные", slug="vozdushnie-cmp")
    product = Product.objects.create(name="DAFU", slug="dafu-cmp", category=cat)
    sku5 = SKU.objects.create(
        product=product,
        name="DA5FU",
        slug="privod-cmp-5nm",
        sku_code="da5fu24-d",
        analog_belimo_code="TF24",
        price=Decimal("100.00"),
        is_published=True,
    )
    sku10 = SKU.objects.create(
        product=product,
        name="DA10FU",
        slug="privod-cmp-10nm",
        sku_code="da10fu24-d",
        analog_belimo_code="",
        is_published=True,
    )
    moment = Attribute.objects.create(
        name="Крутящий момент",
        slug="attr-moment-cmp",
    )
    voltage = Attribute.objects.create(
        name="Напряжение (В)",
        slug="attr-voltage-cmp",
    )
    AttributeValue.objects.create(sku=sku5, attribute=moment, value="5 Нм")
    AttributeValue.objects.create(sku=sku5, attribute=voltage, value="24 В")
    AttributeValue.objects.create(sku=sku10, attribute=moment, value="10 Нм")
    AttributeValue.objects.create(sku=sku10, attribute=voltage, value="24 В")
    return {"sku5": sku5, "sku10": sku10}


def test_parse_compare_slugs_dedupes_and_strips() -> None:
    """Comma list keeps order and drops empties/dupes."""
    assert parse_compare_slugs(" a,b, a ,c,,") == ["a", "b", "c"]
    assert parse_compare_slugs("") == []


def test_normalize_compare_cell() -> None:
    """Diff equality ignores case and spacing."""
    assert normalize_compare_cell("  24  В= ") == normalize_compare_cell("24 в=")


def test_format_compare_cells() -> None:
    """Empty cells become dash; units append when missing from value."""
    from catalog.compare import format_attribute_cell, format_highlight_cell

    assert format_highlight_cell({"value": "", "unit": "Нм"}) == COMPARE_EMPTY_CELL
    assert format_highlight_cell({"value": "5", "unit": "Нм"}) == "5 Нм"
    assert format_highlight_cell({"value": "5 Нм", "unit": "Нм"}) == "5 Нм"
    assert format_attribute_cell({"value": "", "unit": ""}) == COMPARE_EMPTY_CELL
    assert format_attribute_cell({"value": "IP54", "unit": ""}) == "IP54"
    assert format_attribute_cell({"value": "54", "unit": "дБ"}) == "54 дБ"


def test_build_compare_rows_marks_diff() -> None:
    """Moment differs; voltage same; empty analog is dash."""
    payloads = [
        {
            "sku_code": "A",
            "analog_belimo_code": "TF24",
            "highlights": [
                {"key": "moment", "name": "Крутящий момент", "value": "5 Нм", "unit": ""},
                {"key": "voltage", "name": "Напряжение", "value": "24 В", "unit": ""},
            ],
        },
        {
            "sku_code": "B",
            "analog_belimo_code": "",
            "highlights": [
                {"key": "moment", "name": "Крутящий момент", "value": "10 Нм", "unit": ""},
                {"key": "voltage", "name": "Напряжение", "value": "24 В", "unit": ""},
            ],
        },
    ]
    rows = {r["key"]: r for r in build_compare_rows(payloads)}
    assert rows["moment"]["diff"] is True
    assert rows["voltage"]["diff"] is False
    assert rows["analog_belimo_code"]["values"] == ["TF24", COMPARE_EMPTY_CELL]
    assert rows["analog_belimo_code"]["diff"] is True


@pytest.mark.django_db
def test_compare_endpoint_happy_path(client) -> None:
    """GET compare returns SKUs in request order and diff rows."""
    seeded = _seed_pair()
    url = reverse("catalog-compare-list")
    response = client.get(
        url,
        {"skus": f"{seeded['sku10'].slug},{seeded['sku5'].slug}"},
    )
    assert response.status_code == 200
    slugs = [row["slug"] for row in response.data["skus"]]
    assert slugs == [seeded["sku10"].slug, seeded["sku5"].slug]
    by_key = {row["key"]: row for row in response.data["rows"]}
    assert by_key["moment"]["diff"] is True
    assert by_key["voltage"]["diff"] is False
    assert by_key["sku_code"]["values"] == [
        seeded["sku10"].sku_code,
        seeded["sku5"].sku_code,
    ]


@pytest.mark.django_db
def test_compare_endpoint_rejects_over_limit(client) -> None:
    """More than COMPARE_MAX_SKUS → 400."""
    _seed_pair()
    slugs = ",".join(f"x{i}" for i in range(COMPARE_MAX_SKUS + 1))
    response = client.get(reverse("catalog-compare-list"), {"skus": slugs})
    assert response.status_code == 400
    assert "detail" in response.data


@pytest.mark.django_db
def test_compare_endpoint_unknown_slug(client) -> None:
    """Unknown slug → 400 with missing list."""
    seeded = _seed_pair()
    response = client.get(
        reverse("catalog-compare-list"),
        {"skus": f"{seeded['sku5'].slug},missing-sku"},
    )
    assert response.status_code == 400
    assert "missing-sku" in str(response.data)


@pytest.mark.django_db
def test_compare_endpoint_empty_skus(client) -> None:
    """Empty / missing skus → empty matrix (200)."""
    response = client.get(reverse("catalog-compare-list"))
    assert response.status_code == 200
    assert response.data["skus"] == []
    assert response.data["rows"] == []


@pytest.mark.django_db
def test_compare_endpoint_includes_attribute_rows(client) -> None:
    """Full ТТХ rows carry group metadata alongside highlight rows."""
    seeded = _seed_pair()
    response = client.get(
        reverse("catalog-compare-list"),
        {"skus": f"{seeded['sku5'].slug},{seeded['sku10'].slug}"},
    )
    assert response.status_code == 200
    rows = response.data["rows"]
    assert any(row.get("core") is True for row in rows)
    assert all("group" in row for row in rows)
    assert all("values" in row and "diff" in row for row in rows)
