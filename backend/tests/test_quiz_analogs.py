"""Tests for quiz cross-category analog bundles (kit → valve + drive + bracket)."""

from __future__ import annotations

import pytest
from rest_framework.test import APIRequestFactory

from catalog.etl.attr_write import set_sku_attribute
from catalog.models import SKU, Category, Product
from catalog.quiz_analogs import (
    build_kit_bundle_for_valve,
    family_matches_voltage,
    find_kit_analog_bundles,
    format_drive_sku_code,
    pick_drive_family,
    quiz_drive_suffix,
    resolve_published_bracket,
    resolve_published_drive,
)


def test_quiz_drive_suffix_maps_control_and_aux() -> None:
    assert quiz_drive_suffix("onoff", "no") == "-D"
    assert quiz_drive_suffix("onoff", "yes") == "-DS"
    assert quiz_drive_suffix("modulating", "no") == "-A"
    assert quiz_drive_suffix("modulating", "yes") == "-AS"
    assert quiz_drive_suffix("skip", "skip") == "-D"


def test_family_matches_voltage_24_and_230() -> None:
    assert family_matches_voltage("DA6MU24", "24") is True
    assert family_matches_voltage("DA6MU24", "230") is False
    assert family_matches_voltage("DA6MU230", "230") is True
    assert family_matches_voltage("DA6MU24", "skip") is True


def test_format_drive_sku_code() -> None:
    assert format_drive_sku_code("DA6MU24", "-D") == "DA6MU24-D"


def test_pick_drive_family_returns_none_when_voltage_mismatch() -> None:
    assert pick_drive_family(["DA6MU24"], "230") is None


def test_resolve_published_bracket_empty_code() -> None:
    assert resolve_published_bracket("") is None


def test_pick_drive_family_prefers_in_stock() -> None:
    drive = SKU(sku_code="DA6MU24-D", stock_qty=3)
    family = pick_drive_family(
        ["DA5FU24", "DA6MU24"],
        "24",
        drive_by_family={"DA6MU24": drive},
    )
    assert family == "DA6MU24"


def test_pick_drive_family_falls_back_to_first_match_without_stock() -> None:
    drive = SKU(sku_code="DA6MU24-D", stock_qty=0)
    family = pick_drive_family(
        ["DA6MU24"],
        "24",
        drive_by_family={"DA6MU24": drive},
    )
    assert family == "DA6MU24"


@pytest.mark.django_db
def test_resolve_published_drive_by_family_and_suffix() -> None:
    cat = Category.objects.create(name="Приводы", slug="elektroprivody")
    product = Product.objects.create(name="DA6MU", slug="da6mu", category=cat)
    SKU.objects.create(
        product=product,
        name="DA6MU24-D",
        slug="da6mu24-d",
        sku_code="DA6MU24-D",
        is_published=True,
    )
    found = resolve_published_drive("DA6MU24", "-D")
    assert found is not None
    assert found.sku_code == "DA6MU24-D"


@pytest.mark.django_db
def test_build_kit_bundle_for_valve_pairs_valve_drive_bracket() -> None:
    valve_cat = Category.objects.create(name="Шаровые краны", slug="sharovye-krany")
    drive_cat = Category.objects.create(name="Приводы", slug="elektroprivody")
    adapter_cat = Category.objects.create(name="Адаптеры", slug="adaptery")

    valve_product = Product.objects.create(
        name="BV220",
        slug="sharovoy-kran-bv220",
        category=valve_cat,
    )
    valve = SKU.objects.create(
        product=valve_product,
        name="BV220A",
        slug="8100-bv220a",
        sku_code="8100-BV220A",
        is_published=True,
        stock_qty=2,
    )
    set_sku_attribute(
        valve,
        slug="compatible-actuators",
        value="DA5FU24, DA6MU24 (−D/−DS/−A/−AS)",
        name="Совместимый привод",
        unit="",
    )
    set_sku_attribute(
        valve,
        slug="bracket",
        value="BR-M / BR-ML (для DA5FU)",
        name="Кронштейн",
        unit="",
    )

    drive_product = Product.objects.create(name="DA6MU", slug="da6mu", category=drive_cat)
    drive = SKU.objects.create(
        product=drive_product,
        name="DA6MU24-D",
        slug="da6mu24-d",
        sku_code="DA6MU24-D",
        is_published=True,
        stock_qty=1,
    )
    _ = drive

    adapter_product = Product.objects.create(name="BR-M", slug="br-m", category=adapter_cat)
    SKU.objects.create(
        product=adapter_product,
        name="BR-M",
        slug="br-m-sku",
        sku_code="BR-M",
        is_published=True,
        stock_qty=5,
    )

    bundle = build_kit_bundle_for_valve(valve, "24", "onoff", "no")
    assert bundle is not None
    assert bundle["valve"].sku_code == "8100-BV220A"
    assert bundle["drive"].sku_code == "DA6MU24-D"
    assert bundle["bracket"] is not None
    assert bundle["bracket"].sku_code == "BR-M"
    assert bundle["drive_code"] == "DA6MU24-D"
    assert bundle["in_stock"] is True


@pytest.mark.django_db
def test_find_kit_analog_bundles_filters_by_dn_facet() -> None:
    valve_cat = Category.objects.create(name="Шаровые краны", slug="sharovye-krany")
    drive_cat = Category.objects.create(name="Приводы", slug="elektroprivody")
    adapter_cat = Category.objects.create(name="Адаптеры", slug="adaptery")

    for dn, code in (("25", "8100-BV225A"), ("40", "8100-BV240A")):
        product = Product.objects.create(
            name=f"BV{code[-4:]}",
            slug=f"sharovoy-kran-{code[-6:].casefold()}",
            category=valve_cat,
        )
        sku = SKU.objects.create(
            product=product,
            name=code,
            slug=code.casefold(),
            sku_code=code,
            is_published=True,
            stock_qty=1,
        )
        set_sku_attribute(sku, slug="dn", value=dn, name="DN", unit="")
        set_sku_attribute(
            sku,
            slug="compatible-actuators",
            value="DA6MU24 (−D/−DS/−A/−AS)",
            name="Совместимый привод",
            unit="",
        )

    drive_product = Product.objects.create(name="DA6MU", slug="da6mu", category=drive_cat)
    SKU.objects.create(
        product=drive_product,
        name="DA6MU24-D",
        slug="da6mu24-d",
        sku_code="DA6MU24-D",
        is_published=True,
        stock_qty=1,
    )
    adapter_product = Product.objects.create(name="BR-M", slug="br-m", category=adapter_cat)
    SKU.objects.create(
        product=adapter_product,
        name="BR-M",
        slug="br-m-sku",
        sku_code="BR-M",
        is_published=True,
        stock_qty=1,
    )

    factory = APIRequestFactory()
    request = factory.get(
        "/api/catalog/quiz-analogs/",
        {
            "need": "kit",
            "quiz_voltage": "24",
            "quiz_control": "onoff",
            "quiz_aux": "no",
            "dn": "25",
        },
    )
    bundles = find_kit_analog_bundles(request)
    assert len(bundles) == 1
    assert bundles[0]["valve"].sku_code == "8100-BV225A"


@pytest.mark.django_db
def test_build_kit_bundle_none_for_non_ball_valve() -> None:
    cat = Category.objects.create(name="Приводы", slug="elektroprivody")
    product = Product.objects.create(name="DA6MU", slug="da6mu", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="DA6MU24-D",
        slug="da6mu24-d",
        sku_code="DA6MU24-D",
        is_published=True,
    )
    assert build_kit_bundle_for_valve(sku, "24", "onoff", "no") is None


@pytest.mark.django_db
def test_build_kit_bundle_modulating_aux_suffix() -> None:
    valve_cat = Category.objects.create(name="Шаровые краны", slug="sharovye-krany")
    drive_cat = Category.objects.create(name="Приводы", slug="elektroprivody")

    product = Product.objects.create(
        name="BV220",
        slug="sharovoy-kran-bv220",
        category=valve_cat,
    )
    valve = SKU.objects.create(
        product=product,
        name="BV220A",
        slug="8100-bv220a",
        sku_code="8100-BV220A",
        is_published=True,
        stock_qty=0,
    )
    set_sku_attribute(
        valve,
        slug="compatible-actuators",
        value="DA6MU24 (−D/−DS/−A/−AS)",
        name="Совместимый привод",
        unit="",
    )

    drive_product = Product.objects.create(name="DA6MU", slug="da6mu", category=drive_cat)
    SKU.objects.create(
        product=drive_product,
        name="DA6MU24-AS",
        slug="da6mu24-as",
        sku_code="DA6MU24-AS",
        is_published=True,
        stock_qty=1,
    )

    bundle = build_kit_bundle_for_valve(valve, "24", "modulating", "yes")
    assert bundle is not None
    assert bundle["drive_code"] == "DA6MU24-AS"
    assert bundle["in_stock"] is False


@pytest.mark.django_db
def test_find_kit_analog_bundles_empty_when_no_valves() -> None:
    factory = APIRequestFactory()
    request = factory.get("/api/catalog/quiz-analogs/", {"need": "kit", "dn": "999"})
    assert find_kit_analog_bundles(request) == []


@pytest.mark.django_db
def test_build_kit_bundle_uses_compatible_actuators_when_kit_options_none() -> None:
    """H81 kit article in BV category: build_ball_valve_kit_options is None."""
    valve_cat = Category.objects.create(name="Шаровые краны", slug="sharovye-krany")
    drive_cat = Category.objects.create(name="Приводы", slug="elektroprivody")

    product = Product.objects.create(
        name="H8103-BV265",
        slug="sharovoy-kran-h8103-bv265",
        category=valve_cat,
    )
    valve = SKU.objects.create(
        product=product,
        name="H8103-BV265",
        slug="h8103-bv265-24d",
        sku_code="H8103-BV265-24D",
        is_published=True,
        stock_qty=1,
    )
    set_sku_attribute(
        valve,
        slug="compatible-actuators",
        value="DA16MU24 (−D/−DS/−A/−AS)",
        name="Совместимый привод",
        unit="",
    )
    set_sku_attribute(
        valve,
        slug="material",
        value="ВЧШГ",
        name="Материал",
        unit="",
    )

    drive_product = Product.objects.create(name="DA16MU", slug="da16mu", category=drive_cat)
    SKU.objects.create(
        product=drive_product,
        name="DA16MU24-D",
        slug="da16mu24-d",
        sku_code="DA16MU24-D",
        is_published=True,
        stock_qty=1,
    )

    bundle = build_kit_bundle_for_valve(valve, "24", "onoff", "no")
    assert bundle is not None
    assert bundle["bracket_code"] == "BR-H"


@pytest.mark.django_db
def test_quiz_analog_api_rejects_unknown_need(client) -> None:
    response = client.get("/api/catalog/quiz-analogs/", {"need": "actuator"})
    assert response.status_code == 400


@pytest.mark.django_db
def test_quiz_analog_api_returns_kit_components(client) -> None:
    valve_cat = Category.objects.create(name="Шаровые краны", slug="sharovye-krany")
    drive_cat = Category.objects.create(name="Приводы", slug="elektroprivody")
    adapter_cat = Category.objects.create(name="Адаптеры", slug="adaptery")

    product = Product.objects.create(
        name="BV220",
        slug="sharovoy-kran-bv220",
        category=valve_cat,
    )
    valve = SKU.objects.create(
        product=product,
        name="BV220A",
        slug="8100-bv220a",
        sku_code="8100-BV220A",
        is_published=True,
        stock_qty=1,
    )
    set_sku_attribute(
        valve,
        slug="compatible-actuators",
        value="DA6MU24 (−D/−DS/−A/−AS)",
        name="Совместимый привод",
        unit="",
    )

    drive_product = Product.objects.create(name="DA6MU", slug="da6mu", category=drive_cat)
    SKU.objects.create(
        product=drive_product,
        name="DA6MU24-D",
        slug="da6mu24-d",
        sku_code="DA6MU24-D",
        is_published=True,
        stock_qty=1,
    )
    adapter_product = Product.objects.create(name="BR-M", slug="br-m", category=adapter_cat)
    SKU.objects.create(
        product=adapter_product,
        name="BR-M",
        slug="br-m-sku",
        sku_code="BR-M",
        is_published=True,
        stock_qty=1,
    )

    response = client.get(
        "/api/catalog/quiz-analogs/",
        {
            "need": "kit",
            "quiz_voltage": "24",
            "quiz_control": "onoff",
            "quiz_aux": "no",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "kit_components"
    assert payload["count"] == 1
    bundle = payload["bundles"][0]
    assert bundle["valve"]["sku_code"] == "8100-BV220A"
    assert bundle["drive"]["sku_code"] == "DA6MU24-D"
    assert bundle["bracket"]["sku_code"] == "BR-M"
    assert bundle["drive_code"] == "DA6MU24-D"
    assert bundle["in_stock"] is True
    assert "отдельных позиций" in payload["note"]
