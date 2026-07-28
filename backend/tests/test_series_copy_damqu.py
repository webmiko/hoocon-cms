"""Tests for DA..MQU series enricher (multi-Nm)."""

from __future__ import annotations

import pytest

from catalog.etl.series_copy_damqu import (
    PRODUCT_SLUG,
    TORQUE_SPECS,
    _sku_description,
    apply_damqu_enrichment,
)
from catalog.etl.sku_variant import parse_sku_variant
from catalog.models import SKU, AttributeValue, Category, Product


def test_sku_description_modulating_and_aux() -> None:
    """Modulating + aux editions add matching bullets."""
    text = _sku_description(
        parse_sku_variant("da8mqu24-as"),
        row=TORQUE_SPECS[8],
    )
    assert "пропорциональн" in text.casefold()
    assert "вспомогательн" in text.casefold()
    assert "0,8 м" in text or "0.8 м" in text.replace(",", ".")


def test_sku_description_on_off() -> None:
    """2-/3-позиционное edition mentions on/off control."""
    text = _sku_description(parse_sku_variant("da8mqu24-d"), row=TORQUE_SPECS[8])
    assert "2-/3" in text or "позицион" in text.casefold()


@pytest.mark.django_db
def test_apply_damqu_enrichment_missing_product() -> None:
    """No DA..MQU product → zero counters."""
    stats = apply_damqu_enrichment()
    assert stats["products"] == 0
    assert stats["skus"] == 0
    assert stats["attributes"] == 0


@pytest.mark.django_db
def test_apply_damqu_enrichment_24v_and_230v_editions() -> None:
    """Rewrites product copy and edition-specific voltage / control / aux."""
    cat = Category.objects.create(name="Заслонки", slug="zaslonki-damqu-test")
    product = Product.objects.create(
        category=cat,
        name="old",
        slug=PRODUCT_SLUG,
        description="old",
        specs_text="legacy specs",
    )
    sku_24 = SKU.objects.create(
        product=product,
        name="old",
        slug="da8mqu24-a-test",
        sku_code="da8mqu24-a",
        description="old",
        specs_text="x",
        is_published=True,
    )
    sku_230 = SKU.objects.create(
        product=product,
        name="old",
        slug="da8mqu230-ds-test",
        sku_code="da8mqu230-ds",
        description="old",
        is_published=True,
    )
    from catalog.models import Attribute

    legacy = Attribute.objects.create(name="Мусор", slug="legacy-junk")
    AttributeValue.objects.create(sku=sku_24, attribute=legacy, value="x")

    stats = apply_damqu_enrichment()
    assert stats["products"] == 1
    assert stats["skus"] == 2
    assert stats["attributes"] > 0

    product.refresh_from_db()
    assert product.specs_text == ""
    assert "DA8MQU" in product.name
    assert "электропривод" in product.description.casefold()

    by_24 = {
        av.attribute.slug: av.value
        for av in AttributeValue.objects.filter(sku=sku_24).select_related(
            "attribute",
        )
    }
    assert "legacy-junk" not in by_24
    assert "24" in by_24["voltage"]
    assert "пропорциональн" in by_24["control"].casefold()
    assert "aux-switch" not in by_24
    assert by_24["moment"] == "8 Нм"
    assert "running-time" in by_24

    by_230 = {
        av.attribute.slug: av.value
        for av in AttributeValue.objects.filter(sku=sku_230).select_related(
            "attribute",
        )
    }
    assert "100" in by_230["voltage"] or "230" in by_230["voltage"]
    assert "позицион" in by_230["control"].casefold() or "2-/3" in by_230["control"]
    assert by_230["aux-switch"] in {"SPDT-1", "SPDT-2"}


@pytest.mark.django_db
def test_apply_damqu_enrichment_multi_nm() -> None:
    """DA5 and DA20 get distinct moment / area / VA from TORQUE_SPECS."""
    cat = Category.objects.create(
        name="MQU",
        slug="elektroprivody-uskorennye-bez-pruzhinnogo-vozvrata",
    )
    p5 = Product.objects.create(
        category=cat,
        name="old",
        slug="privod-vozdushniy-da5mqu-5nm",
    )
    p20 = Product.objects.create(
        category=cat,
        name="old",
        slug="privod-vozdushniy-da20mqu-20nm",
    )
    sku5 = SKU.objects.create(
        product=p5,
        name="old",
        slug="da5mqu24-d-test",
        sku_code="DA5MQU24-D",
        is_published=True,
    )
    sku20 = SKU.objects.create(
        product=p20,
        name="old",
        slug="da20mqu24-d-test",
        sku_code="DA20MQU24-D",
        is_published=True,
    )

    stats = apply_damqu_enrichment()
    assert stats["products"] == 2
    assert stats["skus"] == 2

    by5 = {av.attribute.slug: av.value for av in AttributeValue.objects.filter(sku=sku5).select_related("attribute")}
    by20 = {av.attribute.slug: av.value for av in AttributeValue.objects.filter(sku=sku20).select_related("attribute")}
    assert by5["moment"] == "5 Нм"
    assert by5["damper-area"] == "до 0,5"
    assert by5["transformer-va"] == "18"
    assert by20["moment"] == "20 Нм"
    assert by20["damper-area"] == "до 2,0"
    assert by20["transformer-va"] == "25"


@pytest.mark.django_db
def test_apply_damqu_enrichment_no_n_plus_one_on_category_slug() -> None:
    """on_off control must not query product/category once per SKU."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    cat = Category.objects.create(name="Заслонки", slug="zaslonki-damqu-n1")
    product = Product.objects.create(
        category=cat,
        name="old",
        slug=PRODUCT_SLUG,
        description="old",
    )
    for idx in range(4):
        SKU.objects.create(
            product=product,
            name="old",
            slug=f"da8mqu24-d-n1-{idx}",
            sku_code=f"da8mqu24-d{idx}" if idx else "da8mqu24-d",
            is_published=True,
        )

    with CaptureQueriesContext(connection) as ctx:
        apply_damqu_enrichment()

    lazy_category = [
        q["sql"]
        for q in ctx.captured_queries
        if 'FROM "catalog_category"' in q["sql"] and "JOIN" not in q["sql"].upper()
    ]
    lazy_product = [
        q["sql"]
        for q in ctx.captured_queries
        if q["sql"].lstrip().upper().startswith("SELECT")
        and 'FROM "catalog_product"' in q["sql"]
        and "JOIN" not in q["sql"].upper()
    ]
    assert lazy_category == []
    assert lazy_product == []
