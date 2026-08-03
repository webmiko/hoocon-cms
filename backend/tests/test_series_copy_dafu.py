"""Tests for DAFU series copy and manual-override canon."""

from __future__ import annotations

import pytest

from catalog.etl.series_copy_dafu import (
    SERIES_INSTRUCTIONS,
    SHARED_ATTRS,
    TORQUE_SPECS,
    apply_dafu_enrichment,
    parse_dafu_torque_nm,
)
from catalog.etl.tech_copy import MANUAL_OVERRIDE_NONE, normalize_manual_override_value
from catalog.models import SKU, AttributeValue, Category, Product


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Открыто/закрыто", MANUAL_OVERRIDE_NONE),
        ("Пропорциональное", MANUAL_OVERRIDE_NONE),
        ("without", MANUAL_OVERRIDE_NONE),
        ("кнопка с самовозвратом", "кнопка с самовозвратом"),
        ("есть", "есть"),
        ("", MANUAL_OVERRIDE_NONE),
    ],
)
def test_normalize_manual_override_rejects_control_leak(raw: str, expected: str) -> None:
    assert normalize_manual_override_value(raw) == expected


def test_is_control_mode_attribute_excludes_manual_override() -> None:
    from catalog.etl.tech_copy import is_control_mode_attribute

    assert is_control_mode_attribute(name="Управление", slug="control") is True
    assert is_control_mode_attribute(name="Ручное управление", slug="manual-override") is False
    assert is_control_mode_attribute(name="Ручное управление", slug="") is False
    assert is_control_mode_attribute(name="Управляющий сигнал Y", slug="control-signal") is False


def test_parse_dafu_torque_nm() -> None:
    assert parse_dafu_torque_nm("DA5FU24-D") == 5
    assert parse_dafu_torque_nm("da10fu230-ds") == 10
    assert parse_dafu_torque_nm("DA8MQU24-A") is None


def test_shared_attrs_include_manual_none() -> None:
    by_slug = {row[1]: row[3] for row in SHARED_ATTRS}
    assert by_slug["manual-override"] == MANUAL_OVERRIDE_NONE
    assert "–40" in by_slug["storage-temp"] or "−40" in by_slug["storage-temp"]
    assert "> 50" in by_slug["shaft-length"]
    assert "10…16" in by_slug["shaft-diameter"]
    assert "7×7" in by_slug["shaft-diameter"]
    assert by_slug["cable-length"] == "1000 мм"


def test_da5_dimensions_from_datasheet_drawing() -> None:
    """DA3/DA5 housing Ш×В×Г from DA5FU dimension photo."""
    assert TORQUE_SPECS[5]["dimensions"] == "98 × 156 × 84 мм"
    assert TORQUE_SPECS[3]["dimensions"] == TORQUE_SPECS[5]["dimensions"]


@pytest.mark.django_db
def test_sku_attribute_rows_do_not_rewrite_manual_override_as_control() -> None:
    """Regression: «управл» in «Ручное управление» must not run control canon."""
    from catalog.etl.attr_write import set_sku_attribute
    from catalog.serializers import _sku_attribute_rows

    cat, _ = Category.objects.get_or_create(
        slug="elektroprivody-s-pruzhinnym-vozvratom",
        defaults={"name": "Пружина"},
    )
    product = Product.objects.create(name="DA5", slug="dafu-ser-test", category=cat)
    sku = SKU.objects.create(
        product=product,
        sku_code="DA5FU24-D",
        name="DA5FU24-D",
        slug="da5fu24-d-ser-test",
        is_published=True,
    )
    set_sku_attribute(
        sku,
        slug="manual-override",
        value=MANUAL_OVERRIDE_NONE,
        name="Ручное управление",
    )
    set_sku_attribute(
        sku,
        slug="control",
        value="Открыто/закрыто",
        name="Управление",
    )
    sku = (
        SKU.objects.filter(pk=sku.pk)
        .select_related("product", "product__category")
        .prefetch_related("attribute_values__attribute")
        .get()
    )
    by_slug = {r["slug"]: r["value"] for r in _sku_attribute_rows(sku, {})}
    assert by_slug["manual-override"] == MANUAL_OVERRIDE_NONE
    assert by_slug["control"] == "Открыто/закрыто"


@pytest.mark.django_db
def test_apply_dafu_enrichment_fixes_manual_override() -> None:
    cat, _ = Category.objects.get_or_create(
        slug="elektroprivody-s-pruzhinnym-vozvratom",
        defaults={"name": "Пружина"},
    )
    product, _ = Product.objects.get_or_create(
        slug="privod-vozdushniy-pruzhina-dafu-5nm",
        defaults={"name": "DA5FU", "category": cat},
    )
    if product.category_id != cat.pk:
        product.category = cat
        product.save(update_fields=["category"])
    sku, _ = SKU.objects.update_or_create(
        sku_code="DA5FU24-D",
        defaults={
            "product": product,
            "name": "bad",
            "slug": "da5fu24-d",
            "is_published": True,
        },
    )
    from catalog.etl.attr_write import set_sku_attribute

    set_sku_attribute(
        sku,
        slug="manual-override",
        value="Открыто/закрыто",
        name="Ручное управление",
    )
    set_sku_attribute(
        sku,
        slug="storage-temp",
        value="-30...+80°C",
        name="Температура хранения",
    )

    stats = apply_dafu_enrichment()
    assert stats["skus"] >= 1
    sku.refresh_from_db()
    by_slug = {
        av.attribute.slug: av.value for av in AttributeValue.objects.filter(sku=sku).select_related("attribute")
    }
    assert by_slug["manual-override"] == MANUAL_OVERRIDE_NONE
    assert by_slug["control"] == "Открыто/закрыто"
    assert by_slug["voltage"] == "AC/DC 24 В, 50/60 Гц"
    assert by_slug["moment"] == TORQUE_SPECS[5]["moment"]
    assert by_slug["weight"] == TORQUE_SPECS[5]["weight"]
    assert "–40" in by_slug["storage-temp"] or "−40" in by_slug["storage-temp"]
    assert by_slug["shaft-length"] == "> 50 мм"
    product.refresh_from_db()
    assert product.instructions == SERIES_INSTRUCTIONS
    assert "> 50 мм" in product.instructions
    assert "10…16" in product.instructions
    assert "PE к приводу не подключается" in product.instructions
    assert "≥90" not in product.instructions
    assert "8–21" not in product.instructions
    assert "–40…+70" in product.instructions or "−40…+70" in product.instructions


def test_series_instructions_align_with_shared_attrs() -> None:
    """Install tab numbers stay in sync with Характеристики canon."""
    by_slug = {row[1]: row[3] for row in SHARED_ATTRS}
    assert by_slug["shaft-length"] in SERIES_INSTRUCTIONS
    assert "10…16" in SERIES_INSTRUCTIONS and "7×7" in SERIES_INSTRUCTIONS
    assert by_slug["cable-length"] in SERIES_INSTRUCTIONS
    assert "0,5 мм²" in SERIES_INSTRUCTIONS
    assert "IP54" in SERIES_INSTRUCTIONS
    assert MANUAL_OVERRIDE_NONE in SERIES_INSTRUCTIONS
    # Manufacturer Attention block (glossary «Предупреждения»).
    assert "ВНИМАНИЕ:" in SERIES_INSTRUCTIONS
    assert "авиационной" in SERIES_INSTRUCTIONS
    assert "бытовыми отходами" in SERIES_INSTRUCTIONS
    # Class II 230 V: no protective earth on the actuator.
    assert "PE" in SERIES_INSTRUCTIONS
    assert "L и N" in SERIES_INSTRUCTIONS
    assert "L, N, PE" not in SERIES_INSTRUCTIONS
    # Aux: all DA..FU -DS/-AS = 2 SPDT.
    assert "-DS / -AS: 2 SPDT" in SERIES_INSTRUCTIONS
    # One physical line per bullet — no indented soft-wrap orphans.
    for line in SERIES_INSTRUCTIONS.splitlines():
        assert not line.startswith("  "), line
    assert "мультиметр для проверки напряжения." in SERIES_INSTRUCTIONS
    tools = [line for line in SERIES_INSTRUCTIONS.splitlines() if "мультиметр" in line or "Ключи для фиксации" in line]
    assert len(tools) == 1
    assert "Ключи" in tools[0] and "мультиметр" in tools[0]


@pytest.mark.django_db
def test_dafu_all_aux_editions_are_spdt_2() -> None:
    """All DA..FU -DS/-AS editions are SPDT-2 (including DA5FU)."""
    from catalog.facets.aux import AUX_SWITCH_SPDT_2, aux_spdt_count_from_sku

    for code in (
        "da5fu24-as",
        "da5fu24-ds",
        "da5fu230-ds",
        "da3fu24-ds",
        "da10fu24-as",
        "da10fu24-ds",
        "da20fu230-ds",
    ):
        assert aux_spdt_count_from_sku(code) == 2, code

    cat, _ = Category.objects.get_or_create(
        slug="elektroprivody-s-pruzhinnym-vozvratom",
        defaults={"name": "Пружина"},
    )
    p5, _ = Product.objects.get_or_create(
        slug="privod-vozdushniy-pruzhina-dafu-5nm",
        defaults={"name": "DA5FU", "category": cat},
    )
    p10, _ = Product.objects.get_or_create(
        slug="privod-vozdushniy-pruzhina-dafu-10nm",
        defaults={"name": "DA10FU", "category": cat},
    )
    for code, slug, product in (
        ("DA5FU24-AS", "da5fu24-as", p5),
        ("DA5FU24-DS", "da5fu24-ds", p5),
        ("DA10FU24-AS", "da10fu24-as", p10),
        ("DA10FU24-DS", "da10fu24-ds", p10),
    ):
        SKU.objects.update_or_create(
            sku_code=code,
            defaults={
                "product": product,
                "name": code,
                "slug": slug,
                "is_published": True,
            },
        )
    apply_dafu_enrichment()
    for code in ("DA5FU24-AS", "DA5FU24-DS", "DA10FU24-AS", "DA10FU24-DS"):
        sku = SKU.objects.get(sku_code=code)
        aux = AttributeValue.objects.get(sku=sku, attribute__slug="aux-switch").value
        assert aux == AUX_SWITCH_SPDT_2, code
        assert "2 SPDT" in (sku.description or ""), code
