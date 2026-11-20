"""Regression: one-off map → card field sync."""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from catalog.models import SKU, AnalogMap, Category, Product


@pytest.mark.django_db
def test_sync_analog_field_from_map_aligns_primary_belimo_row() -> None:
    cat = Category.objects.create(name="Air", slug="air-sync-cmd")
    product = Product.objects.create(name="DA", slug="da-sync-cmd", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="DA8MU24-DS",
        slug="da8mu24-ds-sync-cmd",
        sku_code="DA8MU24-DS",
        is_published=True,
        analog_belimo_code="WRONG",
    )
    AnalogMap.objects.create(
        brand="Belimo",
        foreign_code="NM24A-S2",
        sku=sku,
        torque_nm=10,
        is_active=True,
    )
    call_command("sync_analog_field_from_map", stdout=StringIO())
    sku.refresh_from_db()
    assert sku.analog_belimo_code == "NM24A-S2"


@pytest.mark.django_db
def test_sync_analog_field_from_map_leaves_sku_without_map() -> None:
    cat = Category.objects.create(name="Air", slug="air-sync-cmd2")
    product = Product.objects.create(name="DA", slug="da-sync-cmd2", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="DA5MU24-D",
        slug="da5mu24-d-sync-cmd2",
        sku_code="DA5MU24-D",
        is_published=True,
        analog_belimo_code="LM24A",
    )
    call_command("sync_analog_field_from_map", stdout=StringIO())
    sku.refresh_from_db()
    assert sku.analog_belimo_code == "LM24A"
