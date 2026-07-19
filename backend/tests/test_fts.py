"""Tests for Postgres FTS on SKU (TDD: red → green → refactor).

Spec: ПЛАН §6 Iter 2 — FTS по SKU (SearchVector на SKU+артикул);
docs/readiness-backend-ux.md §2.3 (?q= search).

Postgres Full-Text Search replaces icontains: stemming, ranking, russian
config for Cyrillic. Article/News FTS — Iter 3 (when content app exists).
"""

from __future__ import annotations

import pytest
from django.urls import reverse


def _seed_for_fts():
    """Seed SKUs with distinct names/codes for FTS tests."""
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="Воздушные", slug="vozdushnie-fts")
    product = Product.objects.create(name="HVA", slug="hva-fts", category=cat)

    SKU.objects.create(
        product=product,
        name="Привод воздушный HVA 5 ньютон-метр",
        slug="privod-vozdushniy-hva-5nm-fts",
        sku_code="HVA-5NM",
        is_published=True,
    )
    SKU.objects.create(
        product=product,
        name="Привод противопожарный SA3 3 ньютон-метр",
        slug="privod-protivopozharniy-sa3-fts",
        sku_code="SA3FU-3NM",
        is_published=True,
    )
    SKU.objects.create(
        product=product,
        name="Шаровой кран BV215 DN15",
        slug="sharovoy-kran-bv215-fts",
        sku_code="BV215",
        is_published=True,
    )
    return product


@pytest.mark.django_db
def test_fts_q_finds_sku_by_name_word(client) -> None:
    """?q=привод finds SKUs whose name contains 'привод' (stemmed)."""
    _seed_for_fts()
    response = client.get(reverse("catalog-sku-list"), {"q": "привод"})
    assert response.status_code == 200
    slugs = {row["slug"] for row in response.data["results"]}
    # Both 'Привод воздушный' and 'Привод противопожарный' should match.
    assert "privod-vozdushniy-hva-5nm-fts" in slugs
    assert "privod-protivopozharniy-sa3-fts" in slugs
    # Шаровой кран does not contain 'привод'.
    assert "sharovoy-kran-bv215-fts" not in slugs


@pytest.mark.django_db
def test_fts_q_finds_sku_by_sku_code(client) -> None:
    """?q=BV215 finds the ball valve by article (sku_code)."""
    _seed_for_fts()
    response = client.get(reverse("catalog-sku-list"), {"q": "BV215"})
    assert response.status_code == 200
    slugs = {row["slug"] for row in response.data["results"]}
    assert slugs == {"sharovoy-kran-bv215-fts"}


@pytest.mark.django_db
def test_fts_q_stemming_russian(client) -> None:
    """Russian stemming: 'приводы' (plural) matches 'привод' (singular)."""
    _seed_for_fts()
    response = client.get(reverse("catalog-sku-list"), {"q": "приводы"})
    assert response.status_code == 200
    slugs = {row["slug"] for row in response.data["results"]}
    # Stemming should match both 'Привод ...' SKUs.
    assert "privod-vozdushniy-hva-5nm-fts" in slugs


@pytest.mark.django_db
def test_fts_q_ranks_by_relevance(client) -> None:
    """Results are ordered by SearchRank (name match ranks higher than slug)."""
    _seed_for_fts()
    # 'HVA' appears in name and sku_code of the first SKU.
    response = client.get(reverse("catalog-sku-list"), {"q": "HVA"})
    assert response.status_code == 200
    results = response.data["results"]
    assert len(results) >= 1
    # The HVA-5NM SKU should be the top hit (name + sku_code both match).
    assert results[0]["sku_code"] == "HVA-5NM"


@pytest.mark.django_db
def test_fts_q_empty_returns_all_published(client) -> None:
    """Empty ?q= returns all published SKUs (no FTS filter)."""
    _seed_for_fts()
    response = client.get(reverse("catalog-sku-list"), {"q": ""})
    assert response.status_code == 200
    assert len(response.data["results"]) == 3


@pytest.mark.django_db
def test_fts_q_no_match_returns_empty(client) -> None:
    """?q= with no matches returns empty results list."""
    _seed_for_fts()
    response = client.get(reverse("catalog-sku-list"), {"q": "несуществующий-артикул-xyz"})
    assert response.status_code == 200
    assert response.data["results"] == []


@pytest.mark.django_db
def test_fts_q_combined_with_category_filter(client) -> None:
    """?q= + ?category= compose (FTS + category FK filter)."""
    _seed_for_fts()
    response = client.get(
        reverse("catalog-sku-list"),
        {"q": "привод", "category": "vozdushnie-fts"},
    )
    assert response.status_code == 200
    slugs = {row["slug"] for row in response.data["results"]}
    # Both Привод SKUs are in the 'vozdushnie-fts' category.
    assert "privod-vozdushniy-hva-5nm-fts" in slugs
    assert "privod-protivopozharniy-sa3-fts" in slugs


@pytest.mark.django_db
def test_fts_search_vector_field_exists() -> None:
    """SKU model has a search_vector field (Postgres SearchVectorField)."""
    from catalog.models import SKU

    field = SKU._meta.get_field("search_vector")
    assert field is not None
    # The field is a SearchVectorField (postgres-specific).
    from django.contrib.postgres.search import SearchVectorField

    assert isinstance(field, SearchVectorField)


@pytest.mark.django_db
def test_fts_search_vector_auto_populated_on_save() -> None:
    """Saving a SKU populates search_vector from name + sku_code + slug."""
    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="C", slug="c-sv")
    product = Product.objects.create(name="P", slug="p-sv", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="Тестовый привод XYZ",
        slug="testoviy-privod-xyz",
        sku_code="XYZ-123",
        is_published=True,
    )
    sku.refresh_from_db()
    # search_vector should be non-null after save (auto via trigger or signal).
    assert sku.search_vector is not None
