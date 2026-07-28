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
        seeded["sku10"].sku_code.upper(),
        seeded["sku5"].sku_code.upper(),
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
def test_compare_fills_weight_when_highlight_truncated(client) -> None:
    """Modulating editions can drop weight from list highlights; compare still shows EAV."""
    from catalog.models import (
        SKU,
        Attribute,
        AttributeValue,
        Category,
        Product,
    )

    cat = Category.objects.create(name="Воздушные", slug="vozdushnie-weight-cmp")
    product = Product.objects.create(name="DAMU", slug="damu-weight-cmp", category=cat)
    sku_mod = SKU.objects.create(
        product=product,
        name="DA24",
        slug="da24-weight-cmp",
        sku_code="DA24MU230-AS",
        is_published=True,
    )
    sku_onoff = SKU.objects.create(
        product=product,
        name="DA3FU",
        slug="da3fu-weight-cmp",
        sku_code="da3fu230-ds",
        is_published=True,
    )
    attrs = {
        "control": Attribute.objects.create(name="Управление", slug="control"),
        "moment": Attribute.objects.create(name="Крутящий момент", slug="moment"),
        "voltage": Attribute.objects.create(name="Напряжение", slug="voltage"),
        "area": Attribute.objects.create(name="Площадь заслонки", slug="damper-area"),
        "aux": Attribute.objects.create(name="Вспомогательный переключатель", slug="aux-switch"),
        "runtime": Attribute.objects.create(name="Время поворота", slug="running-time"),
        "signal": Attribute.objects.create(name="Упр. сигнал Y", slug="control-signal"),
        "feedback": Attribute.objects.create(name="Обратная связь U", slug="feedback-signal"),
        "weight": Attribute.objects.create(name="Масса", slug="weight"),
    }
    # Modulating SKU: enough primary rows that weight falls off list highlight limit.
    AttributeValue.objects.create(sku=sku_mod, attribute=attrs["control"], value="Пропорциональное")
    AttributeValue.objects.create(sku=sku_mod, attribute=attrs["moment"], value="24 Нм")
    AttributeValue.objects.create(sku=sku_mod, attribute=attrs["voltage"], value="AC 230 В")
    AttributeValue.objects.create(sku=sku_mod, attribute=attrs["area"], value="до 2,4 м²")
    AttributeValue.objects.create(sku=sku_mod, attribute=attrs["aux"], value="SPDT-2")
    AttributeValue.objects.create(sku=sku_mod, attribute=attrs["runtime"], value="< 160 с")
    AttributeValue.objects.create(
        sku=sku_mod,
        attribute=attrs["signal"],
        value="0(2)...10 В= / 0(4)...20 мА (спецзаказ)",
    )
    AttributeValue.objects.create(
        sku=sku_mod,
        attribute=attrs["feedback"],
        value="0(2)...10 В= / 0(4)...20 мА (спецзаказ)",
    )
    AttributeValue.objects.create(sku=sku_mod, attribute=attrs["weight"], value="≈ 1,3 кг")
    AttributeValue.objects.create(sku=sku_onoff, attribute=attrs["control"], value="Открыто/закрыто")
    AttributeValue.objects.create(sku=sku_onoff, attribute=attrs["moment"], value="3 Нм")
    AttributeValue.objects.create(sku=sku_onoff, attribute=attrs["voltage"], value="AC 230 В")
    AttributeValue.objects.create(sku=sku_onoff, attribute=attrs["area"], value="до 0,3 м²")
    AttributeValue.objects.create(sku=sku_onoff, attribute=attrs["aux"], value="SPDT-1")
    AttributeValue.objects.create(sku=sku_onoff, attribute=attrs["runtime"], value="≤ 20 с")
    AttributeValue.objects.create(sku=sku_onoff, attribute=attrs["weight"], value="< 1,3 кг")

    response = client.get(
        reverse("catalog-compare-list"),
        {"skus": f"{sku_mod.slug},{sku_onoff.slug}"},
    )
    assert response.status_code == 200
    assert [s["sku_code"] for s in response.data["skus"]] == [
        "DA24MU230-AS",
        "DA3FU230-DS",
    ]
    by_key = {row["key"]: row for row in response.data["rows"]}
    assert "weight" in by_key
    assert by_key["weight"]["values"] == ["≈ 1,3 кг", "< 1,3 кг"]


@pytest.mark.django_db
def test_compare_skips_legacy_signal_alias_rows(client) -> None:
    """Legacy control-signal-y must not duplicate core Упр. сигнал Y with a dash gap."""
    from catalog.models import (
        SKU,
        Attribute,
        AttributeValue,
        Category,
        Product,
    )

    cat = Category.objects.create(name="Воздушные", slug="vozdushnie-signal-cmp")
    product = Product.objects.create(name="DAMU", slug="damu-signal-cmp", category=cat)
    sku_a = SKU.objects.create(
        product=product,
        name="DA2",
        slug="da2-signal-cmp",
        sku_code="DA2MU230-AS",
        is_published=True,
    )
    sku_b = SKU.objects.create(
        product=product,
        name="DA4",
        slug="da4-signal-cmp",
        sku_code="DA4MU230-AS",
        is_published=True,
    )
    control = Attribute.objects.create(name="Управление", slug="control")
    signal_canon = Attribute.objects.create(
        name="Управляющий сигнал Y",
        slug="control-signal",
    )
    signal_alias = Attribute.objects.create(
        name="Управляющий сигнал Y",
        slug="control-signal-y",
    )
    canon = "0(2)...10 В= / 0(4)...20 мА (спецзаказ)"
    for sku in (sku_a, sku_b):
        AttributeValue.objects.create(sku=sku, attribute=control, value="Пропорциональное")
        AttributeValue.objects.create(sku=sku, attribute=signal_canon, value=canon)
    # Alias only on first SKU — mimics uneven ETL; must not create a dashed diff row.
    AttributeValue.objects.create(sku=sku_a, attribute=signal_alias, value=canon)

    response = client.get(
        reverse("catalog-compare-list"),
        {"skus": f"{sku_a.slug},{sku_b.slug}"},
    )
    assert response.status_code == 200
    rows = response.data["rows"]
    assert not any(row["key"] == "control-signal-y" for row in rows)
    signal_rows = [row for row in rows if row["key"] == "control_signal"]
    assert len(signal_rows) == 1
    assert signal_rows[0]["values"] == [canon, canon]
    assert signal_rows[0]["diff"] is False
