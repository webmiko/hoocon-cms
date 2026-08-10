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
    """DA5 and DA24 get distinct moment / area / running-time from manuals."""
    cat = Category.objects.create(
        name="MQU",
        slug="elektroprivody-uskorennye-bez-pruzhinnogo-vozvrata",
    )
    p5 = Product.objects.create(
        category=cat,
        name="old",
        slug="privod-vozdushniy-da5mqu-5nm",
    )
    p24 = Product.objects.create(
        category=cat,
        name="old",
        slug="privod-vozdushniy-da24mqu-24nm",
    )
    sku5 = SKU.objects.create(
        product=p5,
        name="old",
        slug="da5mqu24-d-test",
        sku_code="DA5MQU24-D",
        is_published=True,
    )
    sku24 = SKU.objects.create(
        product=p24,
        name="old",
        slug="da24mqu24-d-test",
        sku_code="DA24MQU24-D",
        is_published=True,
    )

    stats = apply_damqu_enrichment()
    assert stats["products"] == 2
    assert stats["skus"] == 2

    by5 = {av.attribute.slug: av.value for av in AttributeValue.objects.filter(sku=sku5).select_related("attribute")}
    by24 = {av.attribute.slug: av.value for av in AttributeValue.objects.filter(sku=sku24).select_related("attribute")}
    assert by5["moment"] == "5 Нм"
    assert by5["damper-area"] == "до 0,5"
    assert by5["transformer-va"] == "18"
    assert by5["ip-rating"] == "IP44"
    assert by5["power-consumption"].startswith("12 Вт")
    assert "6…16" in by5["shaft-diameter"] or "6...16" in by5["shaft-diameter"]
    assert by5["rotation-direction"] == "выбирается с помощью переключателя"
    assert by24["moment"] == "24 Нм"
    assert by24["damper-area"] == "до 2,4"
    assert by24["running-time"] == "< 45 с (95°)"
    assert by24["transformer-va"] == "25"
    assert by24["ip-rating"] == "IP44"
    assert by24["noise"] == "55"


@pytest.mark.django_db
def test_retire_damqu_noncanonical_nm_redirects() -> None:
    """DA10/DA20 unpublished; 301 to DA8/DA24 same edition."""
    from catalog.etl.series_copy_damqu import retire_damqu_noncanonical_nm
    from redirects.models import Redirect

    cat = Category.objects.create(
        name="MQU",
        slug="elektroprivody-uskorennye-bez-pruzhinnogo-vozvrata",
    )
    p8 = Product.objects.create(
        category=cat,
        name="DA8",
        slug="privod-vozdushniy-da8mqu-8nm",
    )
    p10 = Product.objects.create(
        category=cat,
        name="DA10",
        slug="privod-vozdushniy-da10mqu-10nm",
    )
    p20 = Product.objects.create(
        category=cat,
        name="DA20",
        slug="privod-vozdushniy-da20mqu-20nm",
    )
    p24 = Product.objects.create(
        category=cat,
        name="DA24",
        slug="privod-vozdushniy-da24mqu-24nm",
    )
    target8 = SKU.objects.create(
        product=p8,
        name="t8",
        slug="da8mqu24-a-tgt",
        sku_code="DA8MQU24-A",
        is_published=True,
    )
    legacy10 = SKU.objects.create(
        product=p10,
        name="l10",
        slug="da10mqu24-a-legacy",
        sku_code="DA10MQU24-A",
        is_published=True,
    )
    target24 = SKU.objects.create(
        product=p24,
        name="t24",
        slug="da24mqu24-a-tgt",
        sku_code="DA24MQU24-A",
        is_published=True,
    )
    legacy20 = SKU.objects.create(
        product=p20,
        name="l20",
        slug="da20mqu24-a-legacy",
        sku_code="DA20MQU24-A",
        is_published=True,
    )

    stats = retire_damqu_noncanonical_nm()
    assert stats["skus_unpublished"] == 2
    assert stats["redirects"] == 2

    legacy10.refresh_from_db()
    legacy20.refresh_from_db()
    assert legacy10.is_published is False
    assert legacy20.is_published is False
    assert target8.is_published is True
    assert target24.is_published is True

    r10 = Redirect.objects.get(from_path__contains="da10mqu24-a-legacy")
    assert "da8mqu24-a-tgt" in r10.to_path
    assert r10.status_code == 301
    r20 = Redirect.objects.get(from_path__contains="da20mqu24-a-legacy")
    assert "da24mqu24-a-tgt" in r20.to_path


@pytest.mark.django_db
def test_apply_damqu_enrichment_manual_aligned_da8_and_da16() -> None:
    """DA8/DA16MQU ТТХ match EN ``da8_16_24mqu`` manuals."""
    cat = Category.objects.create(name="MQU8", slug="zaslonki-damqu-manual")
    p8 = Product.objects.create(category=cat, name="old", slug=PRODUCT_SLUG)
    p16 = Product.objects.create(
        category=cat,
        name="old",
        slug="privod-vozdushniy-da16mqu-16nm",
    )
    sku8 = SKU.objects.create(
        product=p8,
        name="old",
        slug="da8mqu24-a-manual",
        sku_code="DA8MQU24-A",
        is_published=True,
    )
    sku16 = SKU.objects.create(
        product=p16,
        name="old",
        slug="da16mqu24-a-manual",
        sku_code="DA16MQU24-A",
        is_published=True,
    )
    apply_damqu_enrichment()
    by8 = {av.attribute.slug: av.value for av in AttributeValue.objects.filter(sku=sku8).select_related("attribute")}
    by16 = {av.attribute.slug: av.value for av in AttributeValue.objects.filter(sku=sku16).select_related("attribute")}
    assert by8["ip-rating"] == "IP44"
    assert by8["noise"] == "55"
    assert by8["power-consumption"] == "12 Вт (работа) / 1 Вт (удержание)"
    assert "95°" in by8["running-time"]
    assert "95°" in by8["rotation-angle"]
    assert by8["weight"] == "1,2…1,3"
    assert "DIP" in by8["rotation-direction"]
    assert by16["moment"] == "16 Нм"
    assert by16["damper-area"] == "до 1,6"
    assert by16["running-time"] == "< 16 с (95°)"
    assert by16["noise"] == "55"
    p8.refresh_from_db()
    assert "IP44" in p8.description
    assert "IP54" not in p8.description


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
