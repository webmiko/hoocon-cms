"""Tests for catalog.etl.load (TDD: red → green → refactor).

Spec: docs/data-quality-etl.md §4 — load validated records into Django ORM.
Idempotent via update_or_create; running twice must not duplicate rows.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "etl_catalog_sample.json"


def _load_raw() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.mark.django_db
def test_load_categories_creates_rows() -> None:
    """load_categories creates Category rows from normalized data."""
    from catalog.etl.extract import extract_categories
    from catalog.etl.load import load_categories
    from catalog.etl.normalize import normalize_category
    from catalog.models import Category

    raw = _load_raw()
    norm = [normalize_category(cid=cid, name=name, parent_id=parent) for cid, name, parent in extract_categories(raw)]
    stats, _cat_map, _q = load_categories(norm)
    assert stats.created >= 5
    assert Category.objects.count() == 5
    # Top-level category present.
    assert Category.objects.filter(slug="elektroprivod-vozdushnoy-zaslonki").exists()


@pytest.mark.django_db
def test_load_categories_links_parent() -> None:
    """Subcategories are linked to their parent via FK."""
    from catalog.etl.extract import extract_categories
    from catalog.etl.load import load_categories
    from catalog.etl.normalize import normalize_category
    from catalog.models import Category

    raw = _load_raw()
    norm = [normalize_category(cid=cid, name=name, parent_id=parent) for cid, name, parent in extract_categories(raw)]
    load_categories(norm)

    sub = Category.objects.get(slug="elektroprivod-protivopozharnogo-klapana")
    assert sub.parent is not None
    # ц → "ts" in our translit: "Специальная" → "spetsialnaya".
    assert sub.parent.slug == "spetsialnaya-protivopozharnaya-seriya"


@pytest.mark.django_db
def test_load_categories_quarantines_missing_parent() -> None:
    """Subcategory with unknown parent_id is not created as a top-level orphan."""
    from catalog.etl.load import load_categories
    from catalog.etl.normalize import NormalizedCategory
    from catalog.models import Category

    cats = [
        NormalizedCategory(
            tilda_id=1,
            name="Корень",
            slug="koren",
            parent_id=None,
        ),
        NormalizedCategory(
            tilda_id=2,
            name="Сирота",
            slug="sirota-podkategoriya",
            parent_id=999_999_999,
        ),
    ]
    stats, cat_map, quarantined = load_categories(cats)
    assert stats.created == 1
    assert 1 in cat_map
    assert 2 not in cat_map
    assert Category.objects.filter(slug="sirota-podkategoriya").count() == 0
    assert Category.objects.filter(parent__isnull=True).count() == 1
    assert len(quarantined) == 1
    assert "parent not found" in quarantined[0]["reason"]
    assert quarantined[0]["payload"]["parent_id"] == 999_999_999


@pytest.mark.django_db
def test_load_categories_resolves_nested_parent_order() -> None:
    """Child listed before its non-root parent still gets the correct FK."""
    from catalog.etl.load import load_categories
    from catalog.etl.normalize import NormalizedCategory
    from catalog.models import Category

    cats = [
        NormalizedCategory(tilda_id=1, name="Корень", slug="root-cat", parent_id=None),
        NormalizedCategory(
            tilda_id=3,
            name="Внук",
            slug="vnuk-cat",
            parent_id=2,
        ),
        NormalizedCategory(
            tilda_id=2,
            name="Сын",
            slug="syn-cat",
            parent_id=1,
        ),
    ]
    _stats, cat_map, quarantined = load_categories(cats)
    assert quarantined == []
    assert set(cat_map) == {1, 2, 3}
    vnuk = Category.objects.get(slug="vnuk-cat")
    assert vnuk.parent is not None
    assert vnuk.parent.slug == "syn-cat"
    assert vnuk.parent.parent is not None
    assert vnuk.parent.parent.slug == "root-cat"


@pytest.mark.django_db
def test_load_categories_is_idempotent() -> None:
    """Running load_categories twice does not duplicate rows."""
    from catalog.etl.extract import extract_categories
    from catalog.etl.load import load_categories
    from catalog.etl.normalize import normalize_category
    from catalog.models import Category

    raw = _load_raw()
    norm = [normalize_category(cid=cid, name=name, parent_id=parent) for cid, name, parent in extract_categories(raw)]
    load_categories(norm)
    stats, _, _q = load_categories(norm)
    assert stats.created == 0
    assert Category.objects.count() == 5


@pytest.mark.django_db
def test_load_product_creates_product_and_skus() -> None:
    """load_product creates Product + nested SKUs + AttributeValues."""
    from catalog.etl.extract import extract_categories
    from catalog.etl.load import load_categories, load_product
    from catalog.etl.normalize import normalize_category, normalize_product
    from catalog.models import SKU, AttributeValue, Product

    raw = _load_raw()
    cats = [normalize_category(cid=cid, name=name, parent_id=parent) for cid, name, parent in extract_categories(raw)]
    _stats, cat_map, _q = load_categories(cats)

    np = normalize_product(raw["products"][0])
    stats = load_product(np, category_map=cat_map)
    assert stats.products_created == 1
    assert stats.skus_created == 2

    product = Product.objects.get(slug="privod-protivopozharniy-3nm")
    assert product.category.slug == "elektroprivod-protivopozharnogo-klapana"
    assert SKU.objects.filter(product=product).count() == 2
    sku = SKU.objects.get(sku_code="sa3fu24-ds")
    assert sku.slug == "privod-protivopozharniy-3nm-sa3fu24-ds"
    attrs = {av.attribute.name: av.value for av in sku.attribute_values.all()}
    assert attrs["Мощность"] == "3 Нм"
    assert attrs["Напряжение (В)"] == "24 В"
    assert AttributeValue.objects.count() >= 4


@pytest.mark.django_db
def test_load_product_is_idempotent() -> None:
    """Running load_product twice updates, does not duplicate."""
    from catalog.etl.extract import extract_categories
    from catalog.etl.load import load_categories, load_product
    from catalog.etl.normalize import normalize_category, normalize_product
    from catalog.models import SKU, Product

    raw = _load_raw()
    cats = [normalize_category(cid=cid, name=name, parent_id=parent) for cid, name, parent in extract_categories(raw)]
    _stats, cat_map, _q = load_categories(cats)

    np = normalize_product(raw["products"][0])
    load_product(np, category_map=cat_map)
    stats = load_product(np, category_map=cat_map)
    assert stats.products_created == 0
    assert stats.skus_created == 0
    assert Product.objects.filter(slug=np.slug).count() == 1
    assert SKU.objects.filter(product__slug=np.slug).count() == 2


@pytest.mark.django_db
def test_load_product_creates_attributes_in_dictionary() -> None:
    """Attributes are created in the Attribute dictionary on first sight."""
    from catalog.etl.extract import extract_categories
    from catalog.etl.load import load_categories, load_product
    from catalog.etl.normalize import normalize_category, normalize_product
    from catalog.models import Attribute

    raw = _load_raw()
    cats = [normalize_category(cid=cid, name=name, parent_id=parent) for cid, name, parent in extract_categories(raw)]
    _stats, cat_map, _q = load_categories(cats)

    np = normalize_product(raw["products"][0])
    load_product(np, category_map=cat_map)
    assert Attribute.objects.filter(name="Мощность").exists()
    assert Attribute.objects.filter(name="Напряжение (В)").exists()
    assert Attribute.objects.filter(name="Управление").exists()


@pytest.mark.django_db
def test_load_product_uses_stable_attr_slug_fallback_for_cjk_titles() -> None:
    """Unsluggable titles must map to one deterministic Attribute slug."""
    from decimal import Decimal

    from catalog.etl.load import _slugify_attr, load_product
    from catalog.etl.normalize import (
        NormalizedAttribute,
        NormalizedProduct,
        NormalizedSKU,
    )
    from catalog.models import Attribute, Category

    cat = Category.objects.create(name="Test", slug="test-category")
    title = "中文属性"
    expected_slug = _slugify_attr(title)

    np = NormalizedProduct(
        tilda_uid="cjk-1",
        name="CJK Product",
        slug="cjk-product",
        description="",
        category_id=1,
        skus=(
            NormalizedSKU(
                sku_code="CJK-1",
                slug="cjk-product-cjk-1",
                name="CJK Product (CJK-1)",
                price=Decimal("0"),
                description="",
                attributes=(NormalizedAttribute(title=title, value="值"),),
            ),
        ),
    )

    load_product(np, category_map={1: cat})
    load_product(np, category_map={1: cat})

    assert expected_slug.startswith("attr-")
    assert Attribute.objects.filter(slug=expected_slug).count() == 1
    assert Attribute.objects.get(slug=expected_slug).name == title


@pytest.mark.django_db
def test_load_product_truncates_attribute_value_to_max_length() -> None:
    """Long EAV values must clip like set_sku_attribute (CharField max_length)."""
    from decimal import Decimal

    from catalog.etl.attr_write import _ATTR_VALUE_MAX_LEN
    from catalog.etl.load import load_product
    from catalog.etl.normalize import (
        NormalizedAttribute,
        NormalizedProduct,
        NormalizedSKU,
    )
    from catalog.models import AttributeValue, Category

    cat = Category.objects.create(name="Test", slug="test-long-attr")
    long_value = "я" * (_ATTR_VALUE_MAX_LEN + 40)
    np = NormalizedProduct(
        tilda_uid="long-1",
        name="Long Attr Product",
        slug="long-attr-product",
        description="",
        category_id=1,
        skus=(
            NormalizedSKU(
                sku_code="LONG-1",
                slug="long-attr-product-long-1",
                name="Long Attr Product (LONG-1)",
                price=Decimal("0"),
                attributes=(NormalizedAttribute(title="Примечание", value=long_value),),
            ),
        ),
    )
    load_product(np, category_map={1: cat})
    av = AttributeValue.objects.get(sku__sku_code="LONG-1", attribute__name="Примечание")
    assert len(av.value) == _ATTR_VALUE_MAX_LEN
    assert av.value == long_value[:_ATTR_VALUE_MAX_LEN]


@pytest.mark.django_db
def test_load_product_quarantines_when_category_missing() -> None:
    """If category_id is unknown, load_product raises QuarantineError.

    Product.category is NOT NULL — we cannot load a product without a
    category. The orchestrator catches this and writes to quarantine CSV.
    """
    from decimal import Decimal

    from catalog.etl.load import load_product
    from catalog.etl.normalize import (
        NormalizedProduct,
        NormalizedSKU,
        QuarantineError,
    )
    from catalog.models import Product

    np = NormalizedProduct(
        tilda_uid="999",
        name="Orphan Product",
        slug="orphan-product",
        description="",
        category_id=999999,  # not in category_map
        skus=(
            NormalizedSKU(
                sku_code="ORPH-1",
                slug="orphan-product-orph-1",
                name="Orphan Product (ORPH-1)",
                price=Decimal("0"),
                attributes=(),
            ),
        ),
    )
    with pytest.raises(QuarantineError) as exc_info:
        load_product(np, category_map={})
    assert "category not found" in exc_info.value.reason
    assert not Product.objects.filter(slug="orphan-product").exists()


@pytest.mark.django_db
def test_load_product_quarantines_when_category_id_none() -> None:
    """Empty partuids → category_id=None must not nullify Product.category.

    update_or_create must never write category=None (NOT NULL); quarantine
    instead so existing products keep their category.
    """
    from decimal import Decimal

    from catalog.etl.load import load_product
    from catalog.etl.normalize import (
        NormalizedProduct,
        NormalizedSKU,
        QuarantineError,
    )
    from catalog.models import Category, Product

    cat = Category.objects.create(name="Keep Me", slug="keep-me")
    Product.objects.create(
        name="Existing",
        slug="existing-product",
        category=cat,
        description="old",
    )
    np = NormalizedProduct(
        tilda_uid="1",
        name="Existing Updated",
        slug="existing-product",
        description="new",
        category_id=None,
        skus=(
            NormalizedSKU(
                sku_code="EX-1",
                slug="existing-product-ex-1",
                name="Existing (EX-1)",
                price=Decimal("0"),
                attributes=(),
            ),
        ),
    )
    with pytest.raises(QuarantineError) as exc_info:
        load_product(np, category_map={cat.pk: cat})
    assert "empty category_id" in exc_info.value.reason
    product = Product.objects.get(slug="existing-product")
    assert product.category_id == cat.pk
    assert product.description == "old"
