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


# ── Description / analogs in the vector + pg_trgm ─────────────────────


@pytest.mark.django_db
def test_fts_search_vector_includes_description() -> None:
    """SKU.search_vector indexes description text (weight B, HTML-free)."""
    from django.contrib.postgres.search import SearchQuery

    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="C2", slug="c2-sv")
    product = Product.objects.create(name="P2", slug="p2-sv", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="H8205-LAV2100 | Клапан",
        slug="h8205-desc-vec",
        sku_code="H8205-VEC",
        description="<p>Уникальный термин супервентиляция в описании.</p>",
        is_published=True,
    )
    sku.refresh_from_db()
    query = SearchQuery("супервентиляция", config="russian")
    assert SKU.objects.filter(pk=sku.pk, search_vector=query).exists()
    # HTML tags must not leak into the vector.
    assert "'p':" not in str(sku.search_vector)


@pytest.mark.django_db
def test_fts_search_vector_updates_on_description_change() -> None:
    """Trigger re-computes the vector when description changes."""
    from django.contrib.postgres.search import SearchQuery

    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="C3", slug="c3-sv")
    product = Product.objects.create(name="P3", slug="p3-sv", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="Клапан простой",
        slug="klapan-desc-upd",
        sku_code="KLP-UPD",
        description="первый термин альфаполе",
        is_published=True,
    )
    sku.description = "второй термин бетаполе"
    sku.save()
    sku.refresh_from_db()
    old_q = SearchQuery("альфаполе", config="russian")
    new_q = SearchQuery("бетаполе", config="russian")
    assert not SKU.objects.filter(pk=sku.pk, search_vector=old_q).exists()
    assert SKU.objects.filter(pk=sku.pk, search_vector=new_q).exists()


@pytest.mark.django_db
def test_fts_vector_excludes_unverified_analogs_text(client) -> None:
    """Unverified ``analogs_text`` lines must NOT be indexed or searchable.

    Card policy ``_drop_unverified_analog_lines`` (95f9d311) hides analog
    rows without a datasheet-confirmed pair. Indexing raw analogs_text
    would publish those hidden codes via ?q= and /api/search/.
    """
    from django.contrib.postgres.search import SearchQuery

    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="C4", slug="c4-sv")
    product = Product.objects.create(name="P4", slug="p4-sv", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="Клапан скрытый аналог",
        slug="klapan-hidden-analog",
        sku_code="HDN-1",
        analogs_text="– Belimo QZN777XK\n",
        is_published=True,
    )
    sku.refresh_from_db()
    hidden_q = SearchQuery("QZN777XK", config="russian")
    assert not SKU.objects.filter(pk=sku.pk, search_vector=hidden_q).exists()
    # Functional surfaces: neither catalog ?q= nor global search may leak it.
    resp = client.get(reverse("catalog-sku-list"), {"q": "QZN777XK"})
    assert {row["slug"] for row in resp.data["results"]} == set()
    resp = client.get(reverse("api-search"), {"q": "QZN777XK"})
    assert {row["url"] for row in resp.data["results"]} == set()


@pytest.mark.django_db
def test_fts_vector_includes_verified_analog_belimo_code() -> None:
    """Verified ``analog_belimo_code`` stays indexed — sanctioned analog."""
    from django.contrib.postgres.search import SearchQuery

    from catalog.models import SKU, Category, Product

    cat = Category.objects.create(name="C5", slug="c5-sv")
    product = Product.objects.create(name="P5", slug="p5-sv", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="Клапан с верифицированным аналогом",
        slug="klapan-verified-analog",
        sku_code="VRF-1",
        analog_belimo_code="VRB555XQ",
        is_published=True,
    )
    sku.refresh_from_db()
    verified_q = SearchQuery("VRB555XQ", config="russian")
    assert SKU.objects.filter(pk=sku.pk, search_vector=verified_q).exists()


@pytest.mark.django_db
def test_sku_sku_code_trgm_index_exists() -> None:
    """GIN trigram index on catalog_sku.sku_code exists (typo tolerance)."""
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename = 'catalog_sku' "
            "  AND indexname = 'catalog_sku_code_trgm'",
        )
        assert cursor.fetchone(), "trigram index on sku_code not found"


@pytest.mark.django_db
def test_pg_trgm_extension_installed() -> None:
    """pg_trgm extension is installed (migrations guarantee it)."""
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")
        assert cursor.fetchone(), "pg_trgm extension missing"
