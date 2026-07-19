"""Tests for catalog.etl.normalize (TDD: red → green → refactor).

Spec: docs/data-quality-etl.md §4.1 — extract → normalize/validate → load.
Падающий ряд → QuarantineError, не в prod без review.

Normalize — чистые функции без Django ORM: тестируются быстро и изолированно.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "etl_catalog_sample.json"


def _load_raw() -> dict:
    """Load the sample fixture as the raw Tilda API payload."""
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


# ── extract ────────────────────────────────────────────────────────


def test_extract_products_returns_list() -> None:
    """extract_products yields raw product dicts from JSON payload."""
    from catalog.etl.extract import extract_products

    raw = _load_raw()
    products = list(extract_products(raw))
    assert len(products) == 3
    assert products[0]["title"].startswith("SA3FU")


def test_extract_categories_returns_tree() -> None:
    """extract_categories yields (parent, child) tuples from filters."""
    from catalog.etl.extract import extract_categories

    raw = _load_raw()
    cats = list(extract_categories(raw))
    # 2 top-level + 3 subcategories = 5 total entries.
    assert len(cats) == 5
    # Each entry: (id, name, parent_id_or_None)
    top_names = {c[1] for c in cats if c[2] is None}
    assert "Электропривод воздушной заслонки" in top_names
    assert "Специальная противопожарная серия" in top_names


# ── normalize_slug ──────────────────────────────────────────────────


def test_normalize_slug_strips_leading_slash() -> None:
    """buttonlink '/privod-...-3nm' → 'privod-...-3nm'."""
    from catalog.etl.normalize import normalize_slug

    assert normalize_slug("/privod-protivipozharniy-3nm") == "privod-protivipozharniy-3nm"


def test_normalize_slug_rejects_empty() -> None:
    """Empty slug raises QuarantineError."""
    from catalog.etl.normalize import QuarantineError, normalize_slug

    with pytest.raises(QuarantineError):
        normalize_slug("")
    with pytest.raises(QuarantineError):
        normalize_slug("   ")


def test_normalize_slug_rejects_uppercase_and_spaces() -> None:
    """Slug must be [a-z0-9-]+ — uppercase/spaces rejected."""
    from catalog.etl.normalize import QuarantineError, normalize_slug

    with pytest.raises(QuarantineError):
        normalize_slug("Privod-3NM")
    with pytest.raises(QuarantineError):
        normalize_slug("privod 3nm")


def test_normalize_slug_accepts_valid_lowercase() -> None:
    """Valid lowercase slugs pass."""
    from catalog.etl.normalize import normalize_slug

    assert normalize_slug("privod-vozdushniy-hva-5nm") == "privod-vozdushniy-hva-5nm"
    assert normalize_slug("sharovoy-kran-bv215") == "sharovoy-kran-bv215"


# ── normalize_product ──────────────────────────────────────────────


def test_normalize_product_with_buttonlink_succeeds() -> None:
    """Product with valid buttonlink normalizes to NormalizedProduct."""
    from catalog.etl.normalize import NormalizedProduct, normalize_product

    raw = _load_raw()
    np = normalize_product(raw["products"][0])
    assert isinstance(np, NormalizedProduct)
    assert np.slug == "privod-protivipozharniy-3nm"
    assert np.name.startswith("SA3FU")
    assert len(np.skus) == 2
    assert np.skus[0].sku_code == "sa3fu24-ds"
    assert np.skus[1].sku_code == "sa3fu24-as"


def test_normalize_product_without_buttonlink_quarantines() -> None:
    """Product with empty buttonlink raises QuarantineError (BV-series)."""
    from catalog.etl.normalize import QuarantineError, normalize_product

    raw = _load_raw()
    with pytest.raises(QuarantineError):
        normalize_product(raw["products"][2])


def test_normalize_product_extracts_category_from_partuids() -> None:
    """Category is resolved from product.partuids (deepest subcategory)."""
    from catalog.etl.normalize import normalize_product

    raw = _load_raw()
    np = normalize_product(raw["products"][0])
    # partuids=[368052664042, 826899277672]; 368052664042 is the subcategory
    # "Электропривод противопожарного клапана".
    assert np.category_id == 368052664042


def test_normalize_product_handles_partuids_as_json_string() -> None:
    """Tilda sometimes stores partuids as a JSON-encoded string, not a list.

    Regression guard: real hoocon_catalog_api.json has partuids as
    '[368052664042,826899277672]' (string), not [368052664042, 826899277672].
    """
    from catalog.etl.normalize import normalize_product

    raw = _load_raw()
    product = raw["products"][0]
    # Simulate the real-world string encoding.
    import json

    product["partuids"] = json.dumps(product["partuids"])
    np = normalize_product(product)
    assert np.category_id == 368052664042


def test_normalize_product_extracts_attributes_from_editions() -> None:
    """Edition option values (Мощность, Напряжение) become SKU attributes."""
    from catalog.etl.normalize import normalize_product

    raw = _load_raw()
    np = normalize_product(raw["products"][0])
    sku0 = np.skus[0]
    attrs = {a.title: a.value for a in sku0.attributes}
    assert attrs["Мощность"] == "3 Нм"
    assert attrs["Напряжение (В)"] == "24 В"
    assert attrs["Управление"] == "Открыто/закрыто"


def test_normalize_edition_without_sku_quarantines() -> None:
    """Edition with empty sku raises QuarantineError."""
    from catalog.etl.normalize import QuarantineError, normalize_product

    raw = _load_raw()
    product = raw["products"][0]
    product["editions"][0]["sku"] = ""
    with pytest.raises(QuarantineError):
        normalize_product(product)


def test_normalize_sku_slug_derived_from_product_and_sku_code() -> None:
    """SKU slug = product_slug + '-' + sku_code (URL-stable, unique)."""
    from catalog.etl.normalize import normalize_product

    raw = _load_raw()
    np = normalize_product(raw["products"][0])
    assert np.skus[0].slug == "privod-protivipozharniy-3nm-sa3fu24-ds"
    assert np.skus[1].slug == "privod-protivipozharniy-3nm-sa3fu24-as"


def test_normalize_product_price_empty_becomes_none() -> None:
    """Empty string price in edition becomes None (RFQ policy)."""
    from catalog.etl.normalize import normalize_product

    raw = _load_raw()
    np = normalize_product(raw["products"][0])
    assert np.skus[0].price is None


def test_normalize_product_price_numeric_parsed() -> None:
    """Numeric string price is parsed to Decimal."""
    from decimal import Decimal

    from catalog.etl.normalize import normalize_product

    raw = _load_raw()
    product = raw["products"][0]
    product["editions"][0]["price"] = "1234.50"
    np = normalize_product(product)
    assert np.skus[0].price == Decimal("1234.50")


# ── normalize_category ─────────────────────────────────────────────


def test_normalize_category_generates_slug_from_name() -> None:
    """Category slug is slugified from Russian name (no Tilda path for cats)."""
    from catalog.etl.normalize import normalize_category

    cat = normalize_category(
        cid=431110420892,
        name="Электропривод воздушной заслонки",
        parent_id=None,
    )
    assert cat.slug == "elektroprivod-vozdushnoy-zaslonki"
    assert cat.name == "Электропривод воздушной заслонки"
    assert cat.tilda_id == 431110420892


def test_normalize_category_subcategory_keeps_parent() -> None:
    """Subcategory normalizes with parent_id preserved."""
    from catalog.etl.normalize import normalize_category

    cat = normalize_category(
        cid=494950843642,
        name="Электропривод воздушный с возвратной пружиной",
        parent_id=431110420892,
    )
    assert cat.parent_id == 431110420892
    assert cat.slug == "elektroprivod-vozdushniy-s-vozvratnoy-pruzhinoy"


# ── quarantine ──────────────────────────────────────────────────────


def test_quarantine_error_carries_reason_and_payload() -> None:
    """QuarantineError exposes .reason and .payload for CSV logging."""
    from catalog.etl.normalize import QuarantineError

    err = QuarantineError("empty slug", {"uid": "123", "title": "BV215"})
    assert err.reason == "empty slug"
    assert err.payload["uid"] == "123"
