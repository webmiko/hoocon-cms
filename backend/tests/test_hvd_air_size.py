"""HVD air size backfill — family dimensions/weight for HVD-10 / HVD-40Q."""

from __future__ import annotations

import pytest

from catalog.etl.hvd_air_size import apply_hvd_air_size_backfill, parse_hvd_air_series
from catalog.models import SKU, AttributeValue, Category, Product


def test_parse_hvd_air_series() -> None:
    """Parse Nm and fast-Q flag from HVD air SKU codes."""
    assert parse_hvd_air_series("HVD24-10") == (10, False)
    assert parse_hvd_air_series("HVD24S-10") == (10, False)
    assert parse_hvd_air_series("HVD230-40Q") == (40, True)
    assert parse_hvd_air_series("HVD24S-3F") is None


@pytest.mark.django_db
def test_hvd_air_size_backfill_shares_family_dims() -> None:
    """All SKUs of one Nm family get the same dimensions and weight."""
    cat = Category.objects.create(name="Воздушные", slug="vozdushnye-hvd-size-test")
    product = Product.objects.create(
        name="HVD-10",
        slug="hvd-10-size-test",
        category=cat,
    )
    a = SKU.objects.create(
        product=product,
        name="HVD24-10",
        slug="hvd24-10-size-test",
        sku_code="HVD24-10",
        is_published=True,
    )
    b = SKU.objects.create(
        product=product,
        name="HVD230S-10",
        slug="hvd230s-10-size-test",
        sku_code="HVD230S-10",
        is_published=True,
    )

    stats = apply_hvd_air_size_backfill(dry_run=False)
    assert stats["updated"] >= 2

    by_a = {av.attribute.slug: av.value for av in AttributeValue.objects.filter(sku=a).select_related("attribute")}
    by_b = {av.attribute.slug: av.value for av in AttributeValue.objects.filter(sku=b).select_related("attribute")}
    assert by_a["dimensions"] == by_b["dimensions"] == "167,8 × 86,2 × 68 мм"
    assert by_a["weight"] == by_b["weight"] == "< 1,1 кг"
