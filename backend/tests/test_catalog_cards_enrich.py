"""Tests for specs_text → canonical EAV card enricher."""

from __future__ import annotations

import pytest

from catalog.etl.label_to_slug import label_to_slug
from catalog.etl.specs_to_attrs import parse_specs_bullets


def test_label_to_slug_core_fields() -> None:
    """Common Belimo-RU labels map to canonical slugs."""
    assert label_to_slug("Крутящий момент", value="8 Нм") == "moment"
    assert label_to_slug("Номинальное напряжение", value="24 В") == "voltage"
    assert label_to_slug("Степень защиты", value="IP54") == "ip-rating"
    assert label_to_slug("Класс защиты", value="IP54") == "ip-rating"
    assert label_to_slug("Класс защиты", value="III (SELV)") == "protection-class"
    assert label_to_slug("Мощность", value="5 Нм") == "moment"
    assert label_to_slug("Управление", value="2-/3-позиционное") == "control"


def test_parse_specs_bullets_damu_sample() -> None:
    """DA..MU-style specs bullets become grouped canonical attrs."""
    text = """
ОБЩИЕ ПАРАМЕТРЫ:
– Крутящий момент: 8 Нм
– Время срабатывания (90°): ≤ 55 сек
– Максимальная площадь заслонки: 0,8 м²
– Степень защиты: IP44
– Рабочая температура: -20°C до +50°C
– Номинальное напряжение: AC/DC 24V 50/60Hz
– Потребляемая мощность: 4,5 Вт (работа), 0,5 Вт (ожидание)
– Класс защиты: III (безопасное низкое напряжение)
– Сечение провода: 0,5 мм²
"""
    parsed = {p.slug: p.value for p in parse_specs_bullets(text)}
    assert parsed["moment"] == "8 Нм"
    assert parsed["running-time"]
    assert parsed["damper-area"]
    assert parsed["ip-rating"] == "IP44"
    assert "ambient-temp" in parsed
    assert "voltage" in parsed
    assert "power-consumption" in parsed
    assert "удержание" in parsed["power-consumption"]
    assert parsed["protection-class"].startswith("III")
    assert parsed["wire-cross-section"]


@pytest.mark.django_db
def test_enrich_sku_cards_writes_groups() -> None:
    """Enricher writes canonical attrs and clears specs when enough rows."""
    from catalog.etl.specs_to_attrs import enrich_sku_cards
    from catalog.models import SKU, AttributeValue, Category, Product
    from catalog.serializers import SKUDetailSerializer

    cat = Category.objects.create(name="Test cards", slug="test-cards-cat")
    product = Product.objects.create(
        category=cat,
        name="DA9MU | Test",
        slug="test-da9mu-cards",
        specs_text=(
            "– Крутящий момент: 9 Нм\n"
            "– Площадь заслонки: до 0,9 м²\n"
            "– Угол поворота: макс. 90°\n"
            "– Направление вращения: вручную\n"
            "– Ручное управление: есть\n"
            "– Индикация положения: механическая\n"
            "– Уровень шума: 45 дБ\n"
            "– Степень защиты: IP54\n"
            "– Температура окружающей среды: –20…+50 °C\n"
            "– Температура хранения: –30…+80 °C\n"
            "– Влажность: 95%\n"
            "– Номинальное напряжение: AC/DC 24V\n"
            "– Потребляемая мощность: 4 Вт / 0,5 Вт\n"
            "– Сечение провода: 0,5 мм²\n"
            "– Класс защиты: III\n"
            "– Диаметр вала: 10…16 мм\n"
            "– Масса: 1 кг\n"
        ),
    )
    sku = SKU.objects.create(
        product=product,
        name="DA9MU | Test",
        slug="test-da9mu24-d",
        sku_code="DA9MU24-D",
        is_published=True,
        specs_text=product.specs_text,
        description="Тестовый привод. Используется в ОВК.",
    )
    result = enrich_sku_cards(sku)
    assert not result.skipped
    assert result.attrs_after >= 8
    assert result.cleared_specs
    sku.refresh_from_db()
    assert (sku.specs_text or "") == ""
    assert AttributeValue.objects.filter(sku=sku, attribute__slug="moment").exists()
    ser = SKUDetailSerializer()
    groups = ser.get_attribute_groups(sku)
    titles = {g["title"] for g in groups}
    assert "Электрические параметры" in titles
    assert "Функциональные параметры" in titles
    assert ser.get_specs_text(sku) == ""


@pytest.mark.django_db
def test_da8mqu_skipped_by_enrich() -> None:
    """Canonical DA8MQU product is not rewritten by catalog cards enricher."""
    from catalog.etl.specs_to_attrs import DA8MQU_PRODUCT_SLUG, enrich_sku_cards
    from catalog.models import SKU

    sku = SKU.objects.filter(product__slug=DA8MQU_PRODUCT_SLUG).first()
    if sku is None:
        pytest.skip("DA8MQU not loaded in test DB")
    before = sku.attribute_values.count()
    result = enrich_sku_cards(sku)
    assert result.skipped
    sku.refresh_from_db()
    assert sku.attribute_values.count() == before


@pytest.mark.django_db
def test_enrich_infers_dn_from_bv_sku_code() -> None:
    """BV article DN uses int() (BV215 → 15), not fragile lstrip('0')."""
    from catalog.etl.specs_to_attrs import enrich_sku_cards
    from catalog.models import SKU, AttributeValue, Category, Product

    cat = Category.objects.create(name="Valves", slug="test-valves-dn")
    product = Product.objects.create(
        category=cat,
        name="BV215 | Шаровой кран",
        slug="test-sharovoy-kran-bv215-dn",
        specs_text="",
    )
    sku = SKU.objects.create(
        product=product,
        name="Шаровой кран BV215A",
        slug="test-bv215a-dn",
        sku_code="8100-BV215A",
        is_published=True,
        specs_text="",
    )
    enrich_sku_cards(sku)
    dn = AttributeValue.objects.filter(sku=sku, attribute__slug="dn").first()
    assert dn is not None
    assert dn.value == "15"


@pytest.mark.django_db
def test_enrich_catalog_cards_and_clear_product_specs() -> None:
    """Batch enrich clears product.specs_text when all SKU specs are empty."""
    from catalog.etl.specs_to_attrs import enrich_catalog_cards, maybe_clear_product_specs
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="Batch", slug="test-batch-cards")
    product = Product.objects.create(
        category=cat,
        name="Batch product",
        slug="test-batch-enrich-product",
        specs_text="legacy product specs",
    )
    sku = SKU.objects.create(
        product=product,
        name="Batch SKU",
        slug="test-batch-sku",
        sku_code="DA7MU24-A",
        is_published=True,
        specs_text=(
            "– Крутящий момент: 7 Нм\n"
            "– Площадь заслонки: до 0,7 м²\n"
            "– Угол поворота: макс. 90°\n"
            "– Направление вращения: вручную\n"
            "– Ручное управление: есть\n"
            "– Индикация положения: механическая\n"
            "– Уровень шума: 45 дБ\n"
            "– Степень защиты: IP54\n"
            "– Температура окружающей среды: –20…+50 °C\n"
            "– Масса: 1 кг\n"
        ),
    )
    summary = enrich_catalog_cards(product_slug=product.slug, dry_run=False)
    assert summary["enriched"] >= 1
    assert summary["skipped"] == 0
    product.refresh_from_db()
    sku.refresh_from_db()
    assert (sku.specs_text or "") == ""
    assert (product.specs_text or "") == ""

    # Already cleared — second call is a no-op.
    assert maybe_clear_product_specs(product) is False


@pytest.mark.django_db
def test_enrich_catalog_cards_dry_run_no_writes() -> None:
    from catalog.etl.specs_to_attrs import enrich_catalog_cards
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="Dry", slug="test-dry-cards")
    product = Product.objects.create(
        category=cat,
        name="Dry",
        slug="test-dry-enrich",
        specs_text="– Крутящий момент: 5 Нм\n– Степень защиты: IP54\n– Масса: 1 кг",
    )
    sku = SKU.objects.create(
        product=product,
        name="Dry SKU",
        slug="test-dry-sku",
        sku_code="DA5MU24-D",
        specs_text=product.specs_text,
    )
    summary = enrich_catalog_cards(product_slug=product.slug, dry_run=True)
    assert summary["total"] == 1
    sku.refresh_from_db()
    assert (sku.specs_text or "").strip()


@pytest.mark.django_db
def test_enrich_sku_cards_loads_category_without_extra_query() -> None:
    """Bare SKU refetch joins category; no lazy Category SELECT afterward."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from catalog.etl.specs_to_attrs import enrich_sku_cards
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="N1", slug="test-n1-cat")
    product = Product.objects.create(
        category=cat,
        name="N1",
        slug="test-n1-product",
        specs_text=(
            "– Крутящий момент: 5 Нм\n"
            "– Номинальное напряжение: AC/DC 24 В\n"
            "– Управление: 2-/3-позиционное\n"
            "– Степень защиты: IP54\n"
            "– Масса: 1 кг\n"
            "– Угол поворота: макс. 90°\n"
            "– Направление вращения: вручную\n"
            "– Ручное управление: есть\n"
        ),
    )
    sku = SKU.objects.create(
        product=product,
        name="N1 SKU",
        slug="test-n1-sku",
        sku_code="DA5MU24-N1",
        specs_text="",
    )
    bare = SKU.objects.get(pk=sku.pk)
    assert "product" not in bare._state.fields_cache

    with CaptureQueriesContext(connection) as ctx:
        result = enrich_sku_cards(bare, dry_run=True)

    assert result.skipped is False
    # Standalone category lookups indicate missing select_related("product__category").
    lazy_category = [
        q["sql"]
        for q in ctx.captured_queries
        if 'FROM "catalog_category"' in q["sql"] and "JOIN" not in q["sql"].upper()
    ]
    assert lazy_category == []
