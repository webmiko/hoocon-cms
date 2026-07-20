"""Tests for specs_text → AttributeValue card enrichment."""

from __future__ import annotations

import pytest

from catalog.etl.specs_to_attrs import (
    enrich_sku_cards,
    parse_specs_bullets,
)
from catalog.models import SKU, Attribute, AttributeValue, Category, Product


def test_parse_specs_bullets_extracts_canonical_rows() -> None:
    """Bullet Label: value lines map to canonical ParsedAttr."""
    text = """
Общие характеристики:
– Крутящий момент: 8 Нм
– Номинальное напряжение: AC/DC 24V, 50/60 Hz
– Степень защиты корпуса: IP54
– Мощность: 10 Нм
DA8MQU:
– skip model header
"""
    rows = parse_specs_bullets(text)
    by_slug = {r.slug: r.value for r in rows}
    # Later «Мощность: 10 Нм» overrides earlier moment.
    assert by_slug["moment"] == "10 Нм"
    assert "24" in by_slug["voltage"]
    assert by_slug["ip-rating"] == "IP54"


def test_parse_specs_bullets_empty_and_noise() -> None:
    assert parse_specs_bullets("") == []
    assert parse_specs_bullets("   ") == []
    assert parse_specs_bullets("– Без двоеточия\n– Значение: –") == []


@pytest.mark.django_db
def test_enrich_sku_cards_from_specs_and_variant() -> None:
    """Specs bullets + SKU code fill voltage/control cards and may clear specs."""
    cat = Category.objects.create(name="Act", slug="act-specs-test")
    product = Product.objects.create(
        category=cat,
        name="DA test",
        slug="privod-test-specs-generic",
        specs_text="",
    )
    specs = """
– Крутящий момент: 8 Нм
– Площадь заслонки: до 0,8 м²
– Угол поворота: макс. 90°
– Степень защиты корпуса: IP54
– Температура окружающей среды: –20…+50
– Масса: 1,2 кг
– Сечение провода: 0,5 мм²
– Габаритные размеры: 180 × 100 × 68
– Ручное управление: кнопка
"""
    sku = SKU.objects.create(
        product=product,
        name="DA8MQU24-A",
        slug="da8mqu24-a-specs",
        sku_code="da8mqu24-a",
        specs_text=specs,
        is_published=True,
    )
    legacy = Attribute.objects.create(name="Крутящий момент", slug="attr-legacy-m")
    AttributeValue.objects.create(sku=sku, attribute=legacy, value="5 Нм")

    result = enrich_sku_cards(sku, dry_run=False)
    assert not result.skipped
    assert result.attrs_after >= 8
    by_slug = {
        av.attribute.slug: av.value
        for av in AttributeValue.objects.filter(sku=sku).select_related(
            "attribute",
        )
    }
    assert "moment" in by_slug
    assert "24" in by_slug.get("voltage", "")
    assert "пропорциональн" in by_slug.get("control", "").casefold()


@pytest.mark.django_db
def test_enrich_sku_cards_skips_canonical_series() -> None:
    """DA8MQU product is owned by series_copy_damqu — skip card enrich."""
    cat = Category.objects.create(name="Act", slug="act-canon-skip")
    product = Product.objects.create(
        category=cat,
        name="DA8MQU",
        slug="privod-vozdushniy-da8mqu-8nm",
    )
    sku = SKU.objects.create(
        product=product,
        name="x",
        slug="da8mqu-skip",
        sku_code="da8mqu24-a",
        is_published=True,
    )
    result = enrich_sku_cards(sku)
    assert result.skipped
    assert result.reason == "canonical_series_copy"


@pytest.mark.django_db
def test_enrich_sku_cards_valve_infers_dn_ways() -> None:
    """BV SKU without specs still gets DN/ways from article code."""
    cat = Category.objects.create(name="Valves", slug="valves-specs-test")
    product = Product.objects.create(
        category=cat,
        name="BV215 | Шаровой кран 2-ходовый DN 15",
        slug="sharovoy-kran-generic-bv-test",
    )
    sku = SKU.objects.create(
        product=product,
        name=product.name,
        slug="8100-bv215a-specs",
        sku_code="8100-bv215a",
        specs_text="– Kvs: 1,6\n– Резьба: G ½",
        is_published=True,
    )
    result = enrich_sku_cards(sku)
    assert not result.skipped
    by_slug = {
        av.attribute.slug: av.value
        for av in AttributeValue.objects.filter(sku=sku).select_related(
            "attribute",
        )
    }
    assert by_slug.get("dn") == "15"
    assert "2-ходов" in by_slug.get("ways", "")
    assert "kvs" in by_slug
