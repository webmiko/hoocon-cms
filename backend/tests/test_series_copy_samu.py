"""SAMU (SA..MU) enrichment — temp-sensor SAF72 on -DST."""

from __future__ import annotations

import pytest

from catalog.etl.series_copy_samu import apply_samu_enrichment
from catalog.facets.temp_sensor import TEMP_SENSOR_NONE, TEMP_SENSOR_SAF72
from catalog.models import SKU, AttributeValue, Category, Product


@pytest.mark.django_db
def test_samu_enrichment_sets_temp_sensor_saf72_on_dst() -> None:
    """DST editions get ``temp-sensor=SAF72``; DS get ``Нет``."""
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

    ds.refresh_from_db()
    dst.refresh_from_db()

    by_ds = {av.attribute.slug: av.value for av in AttributeValue.objects.filter(sku=ds).select_related("attribute")}
    by_dst = {av.attribute.slug: av.value for av in AttributeValue.objects.filter(sku=dst).select_related("attribute")}
    assert by_ds["temp-sensor"] == TEMP_SENSOR_NONE
    assert by_dst["temp-sensor"] == TEMP_SENSOR_SAF72
    assert by_ds["dimensions"] == by_dst["dimensions"] == "см. «Габаритные размеры»"
    assert by_ds["weight"] == by_dst["weight"] == "≈ 1,7 кг"
    assert "SAF72" in (dst.description or "")
    assert "без датчика" in (ds.description or "").casefold()


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
