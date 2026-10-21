"""SAMU (SA..MU) enrichment — RU manuals are DS only, no SAF72."""

from __future__ import annotations

import pytest

from catalog.etl.series_copy_samu import apply_samu_enrichment
from catalog.facets.temp_sensor import TEMP_SENSOR_NONE
from catalog.models import SKU, AttributeValue, Category, Product


@pytest.mark.django_db
def test_samu_enrichment_sets_temp_sensor_saf72_on_dst() -> None:
    """RU SA..MU manuals have no DST/SAF72: both editions store «Нет»."""
    cat = Category.objects.create(
        name="Дымоудаление",
        slug="elektroprivody-dlya-klapanov-dymoudaleniya",
    )
    product = Product.objects.create(
        name="SA10MU",
        slug="privod-dimoudaleniya-10nm-samu-temp-test",
        category=cat,
    )
    ds = SKU.objects.create(
        product=product,
        name="SA10MU24-DS",
        slug="sa10mu24-ds-samu-temp-test",
        sku_code="SA10MU24-DS",
        is_published=True,
    )
    dst = SKU.objects.create(
        product=product,
        name="SA10MU24-DST",
        slug="sa10mu24-dst-samu-temp-test",
        sku_code="SA10MU24-DST",
        is_published=True,
    )

    stats = apply_samu_enrichment(dry_run=False)
    assert stats["skus"] >= 2
    assert stats["unpublished_dst"] >= 1

    ds.refresh_from_db()
    dst.refresh_from_db()
    assert ds.is_published is True
    assert dst.is_published is False

    by_ds = {av.attribute.slug: av.value for av in AttributeValue.objects.filter(sku=ds).select_related("attribute")}
    by_dst = {av.attribute.slug: av.value for av in AttributeValue.objects.filter(sku=dst).select_related("attribute")}
    assert by_ds["temp-sensor"] == TEMP_SENSOR_NONE
    assert by_dst["temp-sensor"] == TEMP_SENSOR_NONE
    assert by_ds["dimensions"] == by_dst["dimensions"] == "160 × 102 × 62 мм"
    assert by_ds["weight"] == by_dst["weight"] == "≈ 1,7 кг"
    assert "SAF72" not in (dst.description or "")
    assert "без датчика" in (ds.description or "").casefold()
    assert by_ds["humidity"] == "5…95 % относительной влажности, без конденсата / EN 60730-1"


@pytest.mark.django_db
def test_samu_family_dimensions_shared_across_sku_mass_per_torque() -> None:
    """Same Nm family shares dimensions; mass comes from the torque row."""
    from catalog.etl.series_copy_samu import TORQUE_SPECS

    cat = Category.objects.create(
        name="Дымоудаление",
        slug="elektroprivody-dlya-klapanov-dymoudaleniya-dims",
    )
    product = Product.objects.create(
        name="SA30MU",
        slug="privod-dimoudaleniya-30nm-samu-dims-test",
        category=cat,
    )
    a = SKU.objects.create(
        product=product,
        name="SA30MU24-DS",
        slug="sa30mu24-ds-samu-dims-test",
        sku_code="SA30MU24-DS",
        is_published=True,
    )
    b = SKU.objects.create(
        product=product,
        name="SA30MU230-DST",
        slug="sa30mu230-dst-samu-dims-test",
        sku_code="SA30MU230-DST",
        is_published=True,
    )

    apply_samu_enrichment(dry_run=False)

    by_a = {av.attribute.slug: av.value for av in AttributeValue.objects.filter(sku=a).select_related("attribute")}
    by_b = {av.attribute.slug: av.value for av in AttributeValue.objects.filter(sku=b).select_related("attribute")}
    assert by_a["dimensions"] == by_b["dimensions"] == TORQUE_SPECS[30]["dimensions"]
    assert by_a["weight"] == by_b["weight"] == TORQUE_SPECS[30]["weight"]


@pytest.mark.django_db
def test_sa15_power_and_shaft_match_ru_manual() -> None:
    """SA15MU RU manual: 5 W / 1 W and shaft ≥ 90 mm; DST is not SAF72."""
    cat = Category.objects.create(
        name="Дымоудаление",
        slug="elektroprivody-dlya-klapanov-dymoudaleniya-sa15",
    )
    product = Product.objects.create(
        name="SA15MU",
        slug="privod-dimoudaleniya-15nm-sa15-manual",
        category=cat,
    )
    ds = SKU.objects.create(
        product=product,
        name="SA15MU230-DS",
        slug="sa15mu230-ds-manual",
        sku_code="SA15MU230-DS",
        is_published=True,
    )
    dst = SKU.objects.create(
        product=product,
        name="SA15MU230-DST",
        slug="sa15mu230-dst-manual",
        sku_code="SA15MU230-DST",
        is_published=False,
    )
    apply_samu_enrichment(dry_run=False)
    by_ds = {av.attribute.slug: av.value for av in AttributeValue.objects.filter(sku=ds).select_related("attribute")}
    by_dst = {av.attribute.slug: av.value for av in AttributeValue.objects.filter(sku=dst).select_related("attribute")}
    assert by_ds["power-consumption"] == "5 Вт (работа) / 1 Вт (удержание)"
    assert by_ds["shaft-length"] == "≥ 90"
    assert by_dst["temp-sensor"] == TEMP_SENSOR_NONE
