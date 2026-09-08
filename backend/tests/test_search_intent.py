"""Tests for catalog search intent (kit phrases → komplekty)."""

from __future__ import annotations

import pytest
from django.urls import reverse

from catalog.models import SKU, Category, Product
from catalog.search_intent import (
    KIT_CATEGORY_SLUG,
    normalize_search_query,
    resolve_catalog_search_intent,
)


@pytest.mark.parametrize(
    ("raw", "expected_phrase", "residual"),
    [
        ("кран с приводом", "кран с приводом", ""),
        ("Кран с Приводом", "кран с приводом", ""),
        ("кран + привод", "кран + привод", ""),
        # «+» collapses in normalize; first listed phrase wins («кран + привод»).
        ("кран+привод", "кран + привод", ""),
        ("комплекты", "комплекты", ""),
        ("кран с приводом DN65", "кран с приводом", "dn65"),
        ("шаровой кран с приводом", "шаровой кран с приводом", ""),
    ],
)
def test_resolve_kit_intent_phrases(
    raw: str,
    expected_phrase: str,
    residual: str,
) -> None:
    """Kit phrases map to komplekty; leftover tokens stay as residual."""
    intent = resolve_catalog_search_intent(raw)
    assert intent.category_slug == KIT_CATEGORY_SLUG
    assert intent.matched_phrase == expected_phrase
    assert intent.residual == residual


def test_resolve_intent_ignores_plain_actuator_query() -> None:
    """Ordinary actuator queries must not force komplekty."""
    intent = resolve_catalog_search_intent("привод воздушный 5 нм")
    assert intent.category_slug is None
    assert intent.residual == "привод воздушный 5 нм"


def test_normalize_search_query_yo_and_plus() -> None:
    """Normalization folds ё and treats + as a space."""
    assert normalize_search_query("Кран + привод") == "кран привод"
    assert "ё" not in normalize_search_query("всё")


@pytest.mark.django_db
def test_catalog_q_kran_s_privodom_returns_kits_not_bare_valves(client) -> None:
    """?q=кран с приводом finds komplekty; bare шаровые краны stay out."""
    kits = Category.objects.create(name="Комплекты", slug="komplekty")
    valves = Category.objects.create(name="Шаровые краны", slug="sharovye-krany")
    actuators = Category.objects.create(name="Приводы", slug="vozdushnie-intent")

    kit_product = Product.objects.create(
        name="H8102",
        slug="h8102-intent",
        category=kits,
    )
    valve_product = Product.objects.create(
        name="BV215",
        slug="bv215-intent",
        category=valves,
    )
    actuator_product = Product.objects.create(
        name="DA2",
        slug="da2-intent",
        category=actuators,
    )

    # Kit title has «кран» but not «привод» — FTS alone would miss the phrase.
    SKU.objects.create(
        product=kit_product,
        name="H8102-BV215A-24AS | Электрический шаровой кран 2-ходовый DN 15",
        slug="h8102-bv215a-24as-intent",
        sku_code="H8102-BV215A-24AS",
        is_published=True,
    )
    SKU.objects.create(
        product=valve_product,
        name="BV215 | Шаровой кран 2-ходовый DN 15",
        slug="bv215-bare-intent",
        sku_code="BV215-INTENT",
        is_published=True,
    )
    SKU.objects.create(
        product=actuator_product,
        name="Привод воздушный DA2 2 Нм",
        slug="da2-air-intent",
        sku_code="DA2MU230-AS-INTENT",
        is_published=True,
    )

    response = client.get(reverse("catalog-sku-list"), {"q": "кран с приводом"})
    assert response.status_code == 200
    slugs = {row["slug"] for row in response.data["results"]}
    assert "h8102-bv215a-24as-intent" in slugs
    assert "bv215-bare-intent" not in slugs
    assert "da2-air-intent" not in slugs


@pytest.mark.django_db
def test_catalog_q_komplekty_word_lists_kit_category(client) -> None:
    """?q=комплекты returns published SKUs from the komplekty category."""
    kits = Category.objects.create(name="Комплекты", slug="komplekty")
    product = Product.objects.create(name="Kit", slug="kit-word", category=kits)
    SKU.objects.create(
        product=product,
        name="H8205-LAV2100-230A | Электрический регулирующий клапан",
        slug="h8205-lav-intent",
        sku_code="H8205-LAV2100-230A",
        is_published=True,
    )

    response = client.get(reverse("catalog-sku-list"), {"q": "комплекты"})
    assert response.status_code == 200
    slugs = {row["slug"] for row in response.data["results"]}
    assert slugs == {"h8205-lav-intent"}
