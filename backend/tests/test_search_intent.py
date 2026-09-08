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


def test_resolve_intent_empty_and_punctuation_only() -> None:
    """Blank / punctuation-only queries stay without category intent."""
    empty = resolve_catalog_search_intent("")
    assert empty.category_slug is None
    assert empty.residual == ""
    spaced = resolve_catalog_search_intent("   ")
    assert spaced.category_slug is None
    assert spaced.residual == ""
    punct = resolve_catalog_search_intent("+++")
    assert punct.category_slug is None
    assert punct.residual == ""


def test_resolve_intent_skips_phrases_that_normalize_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty normalized phrase entries are skipped; later phrases still match."""
    monkeypatch.setattr(
        "catalog.search_intent._KIT_PHRASES",
        ("+++", "комплекты"),
    )
    intent = resolve_catalog_search_intent("комплекты")
    assert intent.category_slug == KIT_CATEGORY_SLUG
    assert intent.matched_phrase == "комплекты"


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


@pytest.mark.django_db
def test_catalog_q_kit_phrase_with_residual_narrows_by_fts(client) -> None:
    """?q=кран с приводом DN65 keeps kits and applies residual FTS."""
    kits = Category.objects.create(name="Комплекты", slug="komplekty")
    product = Product.objects.create(name="Kits", slug="kits-residual", category=kits)
    SKU.objects.create(
        product=product,
        name="H8102 | Электрический шаровой кран DN65",
        slug="kit-dn65-intent",
        sku_code="H8102-DN65-INTENT",
        is_published=True,
    )
    SKU.objects.create(
        product=product,
        name="H8101 | Электрический шаровой кран DN15",
        slug="kit-dn15-intent",
        sku_code="H8101-DN15-INTENT",
        is_published=True,
    )

    response = client.get(
        reverse("catalog-sku-list"),
        {"q": "кран с приводом DN65"},
    )
    assert response.status_code == 200
    slugs = {row["slug"] for row in response.data["results"]}
    assert "kit-dn65-intent" in slugs
    assert "kit-dn15-intent" not in slugs


@pytest.mark.django_db
def test_site_search_kit_phrase_returns_komplekty_skus(client) -> None:
    """GET /api/search/?q=кран с приводом includes published kit SKUs."""
    kits = Category.objects.create(name="Комплекты", slug="komplekty")
    product = Product.objects.create(name="H8102", slug="h8102-site", category=kits)
    SKU.objects.create(
        product=product,
        name="H8102-BV215A-24AS | Электрический шаровой кран",
        slug="h8102-site-intent",
        sku_code="H8102-SITE-INTENT",
        is_published=True,
    )

    response = client.get("/api/search/", {"q": "кран с приводом"})
    assert response.status_code == 200
    sku_slugs = {
        row["slug"]
        for row in response.data["results"]
        if row.get("type") == "sku"
    }
    assert "h8102-site-intent" in sku_slugs


@pytest.mark.django_db
def test_site_search_kit_phrase_with_residual_uses_fts(client) -> None:
    """Site search keeps komplekty scope and FTS-filters residual tokens."""
    kits = Category.objects.create(name="Комплекты", slug="komplekty")
    product = Product.objects.create(name="Kits", slug="kits-site-res", category=kits)
    SKU.objects.create(
        product=product,
        name="Электрический шаровой кран DN65 комплект",
        slug="kit-site-dn65",
        sku_code="KIT-SITE-DN65",
        is_published=True,
    )
    SKU.objects.create(
        product=product,
        name="Электрический шаровой кран DN15 комплект",
        slug="kit-site-dn15",
        sku_code="KIT-SITE-DN15",
        is_published=True,
    )

    response = client.get("/api/search/", {"q": "кран с приводом DN65"})
    assert response.status_code == 200
    sku_slugs = {
        row["slug"]
        for row in response.data["results"]
        if row.get("type") == "sku"
    }
    assert "kit-site-dn65" in sku_slugs
    assert "kit-site-dn15" not in sku_slugs
