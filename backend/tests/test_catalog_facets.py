"""Tests for catalog ТТХ facets and list highlights."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.urls import reverse


def _seed_with_attrs():
    from catalog.models import (
        SKU,
        Attribute,
        AttributeValue,
        Category,
        Product,
    )

    cat = Category.objects.create(name="Воздушные", slug="vozdushnie")
    product = Product.objects.create(name="DAFU", slug="dafu", category=cat)
    sku5 = SKU.objects.create(
        product=product,
        name="DA5FU",
        slug="privod-dafu-5nm",
        sku_code="da5fu24-d",
        price=Decimal("100.00"),
        is_published=True,
    )
    sku10 = SKU.objects.create(
        product=product,
        name="DA10FU",
        slug="privod-dafu-10nm",
        sku_code="da10fu24-d",
        is_published=True,
    )
    # Opaque Tilda-style slug (real ETL shape).
    moment = Attribute.objects.create(
        name="Крутящий момент",
        slug="attr-moment-opaque",
    )
    voltage = Attribute.objects.create(
        name="Напряжение (В)",
        slug="attr-voltage-opaque",
    )
    AttributeValue.objects.create(sku=sku5, attribute=moment, value="5 Нм")
    AttributeValue.objects.create(sku=sku5, attribute=voltage, value="24 В")
    AttributeValue.objects.create(sku=sku10, attribute=moment, value="10 Нм")
    AttributeValue.objects.create(sku=sku10, attribute=voltage, value="230 В")
    return {"sku5": sku5, "sku10": sku10}


@pytest.mark.django_db
def test_facets_endpoint_lists_moment_and_voltage(client) -> None:
    """GET /api/catalog/facets/ returns canonical ТТХ options."""
    _seed_with_attrs()
    response = client.get(reverse("catalog-facet-list"))
    assert response.status_code == 200
    by_key = {row["key"]: row for row in response.data["results"]}
    assert "moment" in by_key
    assert "voltage" in by_key
    moment_values = {v["value"] for v in by_key["moment"]["values"]}
    assert "5 Нм" in moment_values
    assert "10 Нм" in moment_values


@pytest.mark.django_db
def test_sku_filter_by_canonical_moment_alias(client) -> None:
    """?moment=5 Нм filters via name-based facet (not Attribute.slug)."""
    _seed_with_attrs()
    response = client.get(reverse("catalog-sku-list"), {"moment": "5 Нм"})
    assert response.status_code == 200
    slugs = {row["slug"] for row in response.data["results"]}
    assert slugs == {"privod-dafu-5nm"}

    loose = client.get(reverse("catalog-sku-list"), {"moment": "5"})
    assert {row["slug"] for row in loose.data["results"]} == {"privod-dafu-5nm"}


@pytest.mark.django_db
def test_analog_facet_from_belimo_code(client) -> None:
    """«Аналоги» facet lists SKU.analog_belimo_code and filters by it."""
    seeded = _seed_with_attrs()
    seeded["sku5"].analog_belimo_code = "LM24A-S"
    seeded["sku5"].save(update_fields=["analog_belimo_code"])
    seeded["sku10"].analog_belimo_code = "NM230A"
    seeded["sku10"].save(update_fields=["analog_belimo_code"])

    facets = client.get(reverse("catalog-facet-list"))
    assert facets.status_code == 200
    by_key = {row["key"]: row for row in facets.data["results"]}
    assert "analog" in by_key
    assert by_key["analog"]["label"] == "Аналоги"
    codes = {v["value"] for v in by_key["analog"]["values"]}
    assert codes == {"LM24A-S", "NM230A"}

    filtered = client.get(reverse("catalog-sku-list"), {"analog": "LM24A-S"})
    assert filtered.status_code == 200
    assert {row["slug"] for row in filtered.data["results"]} == {"privod-dafu-5nm"}

    # Case-insensitive match for Belimo article codes.
    loose = client.get(reverse("catalog-sku-list"), {"analog": "lm24a-s"})
    assert {row["slug"] for row in loose.data["results"]} == {"privod-dafu-5nm"}


@pytest.mark.django_db
def test_sku_list_includes_highlights(client) -> None:
    """List cards expose compact highlights for moment/voltage."""
    _seed_with_attrs()
    response = client.get(reverse("catalog-sku-list"))
    row = next(r for r in response.data["results"] if r["slug"] == "privod-dafu-5nm")
    keys = [h["key"] for h in row["highlights"]]
    assert "moment" in keys
    assert "voltage" in keys
    by_key = {h["key"]: h["value"] for h in row["highlights"]}
    assert by_key["moment"] == "5 Нм"
    from catalog.etl.tech_copy import VOLTAGE_24_CANON

    assert by_key["voltage"] == VOLTAGE_24_CANON


@pytest.mark.django_db
def test_sku_detail_dedupes_parallel_attributes(client) -> None:
    """Duplicate Tilda Attribute clones are collapsed in detail payload."""
    from catalog.models import Attribute, AttributeValue

    seed = _seed_with_attrs()
    sku = seed["sku5"]
    twin = Attribute.objects.create(name="Напряжение (В)", slug="attr-voltage-twin")
    AttributeValue.objects.create(sku=sku, attribute=twin, value="24 В")
    power = Attribute.objects.create(name="Мощность", slug="attr-power-mislabel")
    AttributeValue.objects.create(sku=sku, attribute=power, value="5 Нм")

    response = client.get(reverse("catalog-sku-detail", kwargs={"slug": sku.slug}))
    assert response.status_code == 200
    names = [a["name"] for a in response.data["attributes"]]
    assert names.count("Напряжение (В)") == 1
    assert "Мощность" not in names
    assert "Крутящий момент" in names


@pytest.mark.django_db
def test_facets_voltage_collapses_to_belimo_forms(client) -> None:
    """Voltage chips use Belimo canon; filter matches any stored spelling."""
    from catalog.etl.tech_copy import VOLTAGE_24_CANON, VOLTAGE_230_CANON
    from catalog.models import (
        SKU,
        Attribute,
        AttributeValue,
        Category,
        Product,
    )

    cat = Category.objects.create(name="Volt", slug="volt-facet-test")
    product = Product.objects.create(name="DA", slug="da-volt", category=cat)
    sku24 = SKU.objects.create(
        product=product,
        name="DA24",
        slug="da24-volt-test",
        sku_code="da5fu24-d-volt",
        is_published=True,
    )
    sku230 = SKU.objects.create(
        product=product,
        name="DA230",
        slug="da230-volt-test",
        sku_code="da5fu230-d-volt",
        is_published=True,
    )
    voltage = Attribute.objects.create(name="Напряжение (В)", slug="attr-volt-test")
    AttributeValue.objects.create(
        sku=sku24,
        attribute=voltage,
        value="AC/DC 24 В (диапазон 19.2−28.8 В)",
    )
    AttributeValue.objects.create(
        sku=sku230,
        attribute=voltage,
        value="AC 100−240V 50/60 Гц",
    )

    response = client.get(reverse("catalog-facet-list"))
    assert response.status_code == 200
    by_key = {row["key"]: row for row in response.data["results"]}
    assert "voltage" in by_key
    values = {v["value"] for v in by_key["voltage"]["values"]}
    assert VOLTAGE_24_CANON in values
    assert VOLTAGE_230_CANON in values
    assert "AC/DC 24 В (диапазон 19.2−28.8 В)" not in values
    assert "24 В" not in values or VOLTAGE_24_CANON in values

    filtered = client.get(
        reverse("catalog-sku-list"),
        {"voltage": VOLTAGE_24_CANON},
    )
    assert filtered.status_code == 200
    slugs = {row["slug"] for row in filtered.data["results"]}
    assert "da24-volt-test" in slugs
    assert "da230-volt-test" not in slugs


@pytest.mark.django_db
def test_facets_area_normalizes_unit_and_spacing(client) -> None:
    """Area chips always use «до N м²»; exact and up-to merge."""
    from catalog.models import (
        SKU,
        Attribute,
        AttributeValue,
        Category,
        Product,
    )

    cat = Category.objects.create(name="Area", slug="area-facet-test")
    product = Product.objects.create(name="DA", slug="da-area", category=cat)
    area = Attribute.objects.create(name="Площадь заслонки", slug="damper-area-norm")
    specs = (
        ("da-area-a", "da-area-a", "до 0,5"),
        ("da-area-b", "da-area-b", "до 0,5 м²"),
        ("da-area-c", "da-area-c", "3, 2 м²"),
        ("da-area-d", "da-area-d", "0,3 м² (для огнезадерживающих клапанов НО)"),
        ("da-area-e", "da-area-e", "0,5 м²"),
    )
    for slug, code, raw in specs:
        sku = SKU.objects.create(
            product=product,
            name=code,
            slug=slug,
            sku_code=code,
            is_published=True,
        )
        AttributeValue.objects.create(sku=sku, attribute=area, value=raw)

    response = client.get(reverse("catalog-facet-list"))
    assert response.status_code == 200
    by_key = {row["key"]: row for row in response.data["results"]}
    assert "area" in by_key
    values = {v["value"]: v["count"] for v in by_key["area"]["values"]}
    assert "до 0,5 м²" in values
    assert values["до 0,5 м²"] == 3
    assert "до 0,5" not in values
    assert "до 3,2 м²" in values
    assert "3,2 м²" not in values
    assert "3, 2 м²" not in values
    assert "до 0,3 м²" in values
    assert "0,3 м²" not in values
    assert not any("огнезадерж" in v for v in values)

    filtered = client.get(
        reverse("catalog-sku-list"),
        {"area": "до 0,5 м²"},
    )
    assert filtered.status_code == 200
    slugs = {row["slug"] for row in filtered.data["results"]}
    assert "da-area-a" in slugs
    assert "da-area-b" in slugs


def test_normalize_area_attribute_value() -> None:
    """All damper-area labels become «до N м²»."""
    from catalog.facets import normalize_area_attribute_value

    assert normalize_area_attribute_value("до 0,5") == "до 0,5 м²"
    assert normalize_area_attribute_value("до 1") == "до 1 м²"
    assert normalize_area_attribute_value("3, 2 м²") == "до 3,2 м²"
    assert normalize_area_attribute_value("1,6 м²") == "до 1,6 м²"
    assert normalize_area_attribute_value("0,5 м²") == "до 0,5 м²"
    assert normalize_area_attribute_value("0,3 м² (для огнезадерживающих клапанов НО)") == "до 0,3 м²"


def test_facet_sort_key_kvs_numeric() -> None:
    """Kvs chips sort by numeric value, not lexicographically."""
    from catalog.facets import _facet_sort_key

    values = ["10", "1,6", "63", "2,5", "10,1", "4,0"]
    ordered = sorted(values, key=lambda v: _facet_sort_key("kvs", v))
    assert ordered == ["1,6", "2,5", "4,0", "10", "10,1", "63"]


@pytest.mark.django_db
def test_highlights_proportional_includes_y_u_signals() -> None:
    """Modulating control always exposes Belimo Y and U signal rows."""
    from catalog.etl.tech_copy import (
        CONTROL_SIGNAL_Y_CANON,
        CONTROL_SIGNAL_Y_LABEL,
        FEEDBACK_SIGNAL_U_CANON,
        FEEDBACK_SIGNAL_U_LABEL,
    )
    from catalog.facets import highlights_for_sku
    from catalog.models import (
        SKU,
        Attribute,
        AttributeValue,
        Category,
        Product,
    )

    cat = Category.objects.create(
        name="MU",
        slug="elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata",
    )
    product = Product.objects.create(name="DA", slug="da-mod", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="DA8MU",
        slug="da8mu-mod-hl",
        sku_code="DA8MU24-A",
        is_published=True,
    )
    control = Attribute.objects.create(name="Управление", slug="control")
    AttributeValue.objects.create(
        sku=sku,
        attribute=control,
        value="Пропорциональное",
    )

    rows = highlights_for_sku(
        list(sku.attribute_values.select_related("attribute")),
        limit=7,
        sku_code=sku.sku_code,
        category_slug=cat.slug,
    )
    by_key = {r["key"]: r for r in rows}
    assert by_key["control"]["value"] == "Пропорциональное"
    assert by_key["control_signal"]["name"] == CONTROL_SIGNAL_Y_LABEL
    assert by_key["control_signal"]["value"] == CONTROL_SIGNAL_Y_CANON
    assert by_key["feedback_signal"]["name"] == FEEDBACK_SIGNAL_U_LABEL
    assert by_key["feedback_signal"]["value"] == FEEDBACK_SIGNAL_U_CANON
    keys = [r["key"] for r in rows]
    assert keys.index("control") < keys.index("control_signal")
    assert keys.index("control_signal") < keys.index("feedback_signal")

    # ON/OFF must not get Y/U.
    AttributeValue.objects.filter(sku=sku, attribute=control).update(
        value="Открыто/закрыто",
    )
    rows_off = highlights_for_sku(
        list(sku.attribute_values.select_related("attribute")),
        limit=7,
        sku_code="DA8MU24-D",
        category_slug=cat.slug,
    )
    assert "control_signal" not in {r["key"] for r in rows_off}
    assert "feedback_signal" not in {r["key"] for r in rows_off}


@pytest.mark.django_db
def test_facets_control_excludes_manual_override(client) -> None:
    """«Ручное управление» must not appear as an «Управление» facet chip."""
    from catalog.models import (
        SKU,
        Attribute,
        AttributeValue,
        Category,
        Product,
    )

    cat = Category.objects.create(name="FU", slug="fu-ctrl-test")
    product = Product.objects.create(name="SA", slug="sa-ctrl", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="SA3FU",
        slug="sa3fu-ctrl-test",
        sku_code="sa3fu24-ds",
        is_published=True,
    )
    control = Attribute.objects.create(name="Управление", slug="control")
    manual = Attribute.objects.create(
        name="Ручное управление",
        slug="manual-override",
    )
    AttributeValue.objects.create(
        sku=sku,
        attribute=control,
        value="2-/3-позиционное",
    )
    AttributeValue.objects.create(
        sku=sku,
        attribute=manual,
        value="шестигранным ключом с фиксацией положения",
    )

    response = client.get(reverse("catalog-facet-list"))
    assert response.status_code == 200
    by_key = {row["key"]: row for row in response.data["results"]}
    assert "control" in by_key
    values = {v["value"] for v in by_key["control"]["values"]}
    assert "Открыто/закрыто" in values
    assert "шестигранным ключом с фиксацией положения" not in values


def test_format_aux_switch_display_hides_absent() -> None:
    """Hero omits «Нет»; «Да» becomes SPDT-1 / SPDT-2 from SKU / description."""
    from catalog.facets import (
        AUX_SWITCH_SPDT_1,
        AUX_SWITCH_SPDT_2,
        format_aux_switch_display,
        normalize_aux_switch_value,
    )

    assert format_aux_switch_display("Нет") is None
    assert format_aux_switch_display("Да", sku_code="da5fu24-as") == AUX_SWITCH_SPDT_2
    assert format_aux_switch_display("Да", sku_code="da5fu24-ds") == AUX_SWITCH_SPDT_1
    assert format_aux_switch_display("Да", description="1 SPDT") == AUX_SWITCH_SPDT_1
    assert format_aux_switch_display("2 SPDT") == AUX_SWITCH_SPDT_2
    assert normalize_aux_switch_value("Да", sku_code="da5fu24-d") == "Нет"
    assert normalize_aux_switch_value("Нет") == "Нет"


@pytest.mark.django_db
def test_facets_aux_switch_spdt_only(client) -> None:
    """Aux facet exposes SPDT-1 / SPDT-2 only (no «Нет» chip)."""
    from catalog.facets import AUX_SWITCH_NONE, AUX_SWITCH_SPDT_1, AUX_SWITCH_SPDT_2
    from catalog.models import (
        SKU,
        Attribute,
        AttributeValue,
        Category,
        Product,
    )

    cat = Category.objects.create(name="Aux", slug="aux-facet-test")
    product = Product.objects.create(name="DA", slug="da-aux", category=cat)
    specs = (
        ("da-aux-none", "da5fu24-d-aux", "Нет"),
        ("da-aux-ds", "da5fu24-ds-aux", "Да"),
        ("da-aux-as", "da5fu24-as-aux", "Да"),
    )
    attr = Attribute.objects.create(
        name="Вспомогательный переключатель",
        slug="aux-switch-test",
    )
    for slug, code, raw in specs:
        sku = SKU.objects.create(
            product=product,
            name=code,
            slug=slug,
            sku_code=code,
            is_published=True,
        )
        AttributeValue.objects.create(sku=sku, attribute=attr, value=raw)

    response = client.get(reverse("catalog-facet-list"))
    assert response.status_code == 200
    by_key = {row["key"]: row for row in response.data["results"]}
    assert "aux_switch" in by_key
    values = {v["value"] for v in by_key["aux_switch"]["values"]}
    assert values == {AUX_SWITCH_SPDT_1, AUX_SWITCH_SPDT_2}
    assert AUX_SWITCH_NONE not in values
    assert "Да" not in values

    filtered = client.get(
        reverse("catalog-sku-list"),
        {"aux_switch": AUX_SWITCH_SPDT_1},
    )
    assert filtered.status_code == 200
    slugs = {row["slug"] for row in filtered.data["results"]}
    assert "da-aux-ds" in slugs
    assert "da-aux-as" not in slugs
    assert "da-aux-none" not in slugs


def test_format_sku_heading_uses_glossary_control() -> None:
    """Heading drops edition trailer and «Нет»; keeps short product name."""
    from catalog.facets import format_sku_heading_name

    out = format_sku_heading_name(
        "DA8MQU | 8Нм Электропривод воздушный ускоренного срабатывания "
        "без возвратной пружины - 8 Нм - 230 В - Плавное управление - Нет",
    )
    assert out == ("DA8MQU | Электропривод воздушный ускоренного срабатывания без возвратной пружины")


def test_format_sku_heading_drops_modulating_parenthetical() -> None:
    """Product titles keep «пропорциональное управление» without (модулирующее)."""
    from catalog.facets import format_sku_heading_name

    out = format_sku_heading_name(
        "DA8MU | Привод пропорциональное (модулирующее) управление",
        sku_code="DA8MU24-A",
    )
    assert "модулирующ" not in out.casefold()
    assert "пропорциональное управление" in out.casefold()
    assert out.startswith("DA8MU24-A |")


def test_format_sku_heading_unique_with_sku_code() -> None:
    """Article from sku_code makes edition titles unique."""
    from catalog.facets import format_sku_heading_name

    out = format_sku_heading_name(
        "DA8MU | Привод воздушный без возвратной пружины",
        sku_code="DA8MU24-D",
    )
    assert out.startswith("DA8MU24-D |")
    assert "без возвратной пружины" in out


def test_format_sku_heading_maps_present_aux_to_spdt() -> None:
    """AS/DS titles keep short name; SPDT stays in highlights, not H1."""
    from catalog.facets import format_sku_heading_name

    out = format_sku_heading_name(
        "DA3FU | 3 Нм Привод - 3 Нм - 230 В - Открыто/Закрыто - Да",
        description="2 SPDT",
    )
    assert "2 SPDT" not in out
    assert "Нет" not in out
    assert "Да" not in out
    assert "3 Нм - 230" not in out
    assert "нм" not in out.casefold()
    assert out.startswith("DA3FU |")


def test_format_sku_heading_never_keeps_torque_unit() -> None:
    """Display titles must not echo «N Нм» (moment is a highlight only).

    Bare «Привод» is normalized to SEO-valuable «Электропривод» to match the
    category names («Электроприводы …»).
    """
    from catalog.facets import format_sku_heading_name

    out = format_sku_heading_name(
        "DA5FU | 5 Нм Привод воздушный с возвратной пружиной - 5 Нм - 24 В - Открыто/Закрыто - Нет",
        sku_code="da5fu24-d",
    )
    assert "нм" not in out.casefold()
    assert out == "da5fu24-d | Электропривод воздушный с возвратной пружиной"


def test_format_sku_heading_strips_valve_facet_trailer() -> None:
    """Valve CSV trailers stripped; Kvs appended for uniqueness on cards."""
    from catalog.facets import format_sku_heading_name

    out = format_sku_heading_name(
        "BV215 | Шаровой кран 2-ходовый DN 15 - 2-ходовый - 15 - 1,6",
        sku_code="8100-bv215a",
        kvs="1,6",
    )
    assert out == "BV215A | Шаровой кран 2-ходовый DN 15, Kvs 1,6"


def test_format_sku_heading_strips_baked_control_tail() -> None:
    """HVA/HVD bodies drop control-type tail; noun → Электропривод.

    «пропорциональное управление» / «управление 2-/3-позиционное» / «позиционное
    управление» are baked into the body before the edition trailer. Control
    type belongs in highlights, not H1.
    """
    from catalog.facets import format_sku_heading_name

    proportional = format_sku_heading_name(
        "HVA-5 | 5 НМ Привод воздушный без возвратной пружины "
        "пропорциональное (модулирующее) управление "
        "- 5 Нм - 230 В - Пропорциональное (модулирующее) управление - Нет",
        sku_code="HVA230-5",
    )
    assert proportional == ("HVA230-5 | Электропривод воздушный без возвратной пружины")

    positional = format_sku_heading_name(
        "HVD-10 | 10Нм Привод воздушный без возвратной пружины управление 2-/3-позиционное - 10 Нм - 230 В - Нет",
        sku_code="HVD230-10",
    )
    assert positional == ("HVD230-10 | Электропривод воздушный без возвратной пружины")

    fast_positional = format_sku_heading_name(
        "HVD-40Q | 40 Нм Привод воздушный без возвратной пружины "
        "ускоренный позиционное управление - 40 Нм - 230 В - Нет",
        sku_code="HVD230-40Q",
    )
    assert fast_positional == ("HVD230-40Q | Электропривод воздушный без возвратной пружины ускоренный")


def test_format_sku_heading_unifies_fast_actuator_word_order() -> None:
    """HVA-5Q reorders to DA8MQU canon: «ускоренного срабатывания без …».

    Same product family in one category must read identically regardless of
    the raw store CSV word order.
    """
    from catalog.facets import format_sku_heading_name

    hva = format_sku_heading_name(
        "HVA-5Q | 5 НМ Привод воздушный без возвратной пружины "
        "ускоренного срабатывания "
        "- 5 Нм - 230 В - Пропорциональное (модулирующее) управление - Нет",
        sku_code="HVA230-5Q",
    )
    assert hva == ("HVA230-5Q | Электропривод воздушный ускоренного срабатывания без возвратной пружины")


def test_strip_heading_echo_from_description() -> None:
    """Description tab drops sentences already shown as H1 / lead."""
    from catalog.facets import strip_heading_echo_from_description

    desc = (
        "Электропривод воздушной заслонки ускоренного срабатывания без "
        "возвратной пружины. Используется в воздушных клапанах систем ОВК.\n\n"
        "– Крутящий момент: 8 Нм\n"
    )
    out = strip_heading_echo_from_description(
        desc,
        heading=("DA8MQU | Электропривод воздушный ускоренного срабатывания без возвратной пружины"),
        lead="Используется в воздушных клапанах систем ОВК.",
    )
    assert "Электропривод" not in out
    assert "Используется" not in out
    assert "Крутящий момент" in out


def test_strip_attribute_echo_from_text() -> None:
    """Specs/description bullets that match EAV rows are removed."""
    from catalog.facets import strip_attribute_echo_from_text

    text = (
        "Электрические параметры (24 В):\n"
        "– Номинальное напряжение: AC/DC 24 В 50/60 Гц\n"
        "– Потребляемая мощность: 12 Вт / 0,8 Вт (удержание)\n"
        "– Мощность трансформатора: 18 В·А\n\n"
        "Функциональные параметры:\n"
        "– Крутящий момент: 8 Нм\n"
        "– Уровень шума: 65 дБ(A)\n"
        "– Сечение подключаемых проводов: 0,5 мм²\n"
    )
    attrs = [
        {"name": "Напряжение", "value": "AC/DC 24 В 50/60 Гц"},
        {"name": "Потребляемая мощность", "value": "12 Вт / 0,8 Вт (удержание)"},
        {"name": "Мощность трансформатора", "value": "18"},
        {"name": "Крутящий момент", "value": "8 Нм"},
        {"name": "Уровень шума", "value": "65"},
    ]
    out = strip_attribute_echo_from_text(text, attrs)
    assert "Крутящий момент" not in out
    assert "Номинальное напряжение" not in out
    assert "Уровень шума" not in out
    assert "Сечение подключаемых проводов" in out
    assert "Электрические параметры" not in out  # orphan header dropped
    assert "Функциональные параметры" in out


def test_extract_sku_lead_picks_prose() -> None:
    """Lead prefers application blurb over bullet ТТХ."""
    from catalog.facets import extract_sku_lead

    desc = (
        "– Крутящий момент: 8Nm\n\n"
        "Управление:\n\n"
        "– 2-/3-позиционное\n\n"
        "Электропривод воздушный ускоренного срабатывания без возвратной "
        "пружины. Используется в воздушных клапанах систем ОВК\n"
    )
    lead = extract_sku_lead(desc)
    assert "воздушных клапанах" in lead
    assert "Крутящий момент" not in lead
    assert lead.startswith("Используется")
