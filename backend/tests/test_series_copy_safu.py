"""Tests for SA..FU series copy and aux SPDT count."""

from __future__ import annotations

import pytest

from catalog.etl.series_copy_safu import (
    SERIES_INSTRUCTIONS,
    SHARED_ATTRS,
    TEMP_SENSOR_NONE,
    TEMP_SENSOR_SAF72,
    TORQUE_SPECS,
    apply_safu_enrichment,
    parse_safu_torque_nm,
)
from catalog.etl.tech_copy import MANUAL_OVERRIDE_BUTTON_SELF_RESET
from catalog.facets.aux import AUX_SWITCH_SPDT_2, aux_spdt_count_from_sku, normalize_aux_switch_value
from catalog.models import SKU, AttributeValue, Category, Product


def test_parse_safu_torque_nm() -> None:
    assert parse_safu_torque_nm("SA5FU24-DS") == 5
    assert parse_safu_torque_nm("sa10fu230-dst") == 10
    assert parse_safu_torque_nm("DA5FU24-D") is None


def test_safu_aux_spdt_is_two() -> None:
    assert aux_spdt_count_from_sku("sa3fu24-ds") == 2
    assert aux_spdt_count_from_sku("sa5fu230-dst") == 2
    assert normalize_aux_switch_value("SPDT-1", sku_code="sa3fu24-ds") == AUX_SWITCH_SPDT_2
    # DAFU DS remains SPDT-1.
    assert aux_spdt_count_from_sku("da5fu24-ds") == 1


def test_shared_attrs_manual_override_button() -> None:
    by_slug = {row[1]: row[3] for row in SHARED_ATTRS}
    assert by_slug["manual-override"] == MANUAL_OVERRIDE_BUTTON_SELF_RESET
    assert "12×12" in by_slug["shaft-diameter"]


def test_sa3_specs_from_manual() -> None:
    row = TORQUE_SPECS[3]
    assert row["damper-area"] == "до 0,3 м²"
    assert "< 75 с" in row["running-time"]
    assert "50 дБ" in row["noise"]
    assert row["dimensions"] == "132 × 87 × 59 мм"
    assert "> 50" in row["shaft-length"]


def test_sa5_shaft_and_noise_differ_from_sa3() -> None:
    assert "< 90" in TORQUE_SPECS[5]["shaft-length"]
    assert "62 дБ" in TORQUE_SPECS[5]["noise"]
    assert "50 дБ" in TORQUE_SPECS[3]["noise"]


def test_instructions_mention_saf72_and_pe() -> None:
    assert "SAF72" in SERIES_INSTRUCTIONS
    assert "класс II" in SERIES_INSTRUCTIONS.casefold() or "класс защиты II" in SERIES_INSTRUCTIONS


def test_instructions_include_safety_attention() -> None:
    assert "ВНИМАНИЕ:" in SERIES_INSTRUCTIONS
    assert "авиационной" in SERIES_INSTRUCTIONS
    assert "бытовыми отходами" in SERIES_INSTRUCTIONS
    assert "Утилизация:" in SERIES_INSTRUCTIONS


@pytest.mark.django_db
def test_apply_safu_enrichment_writes_attrs() -> None:
    cat, _ = Category.objects.get_or_create(
        slug="elektroprivody-protivopozharnye",
        defaults={"name": "Противопожарные"},
    )
    product = Product.objects.create(
        name="SA3",
        slug="privod-protivopozharniy-3nm-test",
        category=cat,
    )
    ds = SKU.objects.create(
        product=product,
        sku_code="sa3fu24-ds",
        name="sa3fu24-ds",
        slug="sa3fu24-ds-safu-test",
        is_published=True,
    )
    dst = SKU.objects.create(
        product=product,
        sku_code="sa3fu24-dst",
        name="sa3fu24-dst",
        slug="sa3fu24-dst-safu-test",
        is_published=True,
    )

    stats = apply_safu_enrichment(dry_run=False)
    assert stats["skus"] >= 2

    product.refresh_from_db()
    assert product.instructions
    assert "SA..FU" in product.instructions or "противопожар" in product.instructions.casefold()

    by_ds = {av.attribute.slug: av.value for av in AttributeValue.objects.filter(sku=ds).select_related("attribute")}
    by_dst = {av.attribute.slug: av.value for av in AttributeValue.objects.filter(sku=dst).select_related("attribute")}
    assert by_ds["aux-switch"] == AUX_SWITCH_SPDT_2
    assert by_ds["temp-sensor"] == TEMP_SENSOR_NONE
    assert by_dst["temp-sensor"] == TEMP_SENSOR_SAF72
    assert by_ds["manual-override"] == MANUAL_OVERRIDE_BUTTON_SELF_RESET
    assert by_ds["moment"] == "3 Нм"
    assert by_ds["ip-rating"] == "IP54"
