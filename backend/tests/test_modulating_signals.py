"""Coverage tests for modulating Y/U signal EAV persistence."""

from __future__ import annotations

import pytest

from catalog.etl.tech_copy import (
    CONTROL_SIGNAL_Y_CANON,
    CONTROL_SIGNAL_Y_LABEL,
    CONTROL_SIGNAL_Y_SLUG,
    FEEDBACK_SIGNAL_U_CANON,
    FEEDBACK_SIGNAL_U_LABEL,
    FEEDBACK_SIGNAL_U_SLUG,
)
from catalog.facets.highlights import ensure_modulating_signal_attributes
from catalog.models import SKU, Attribute, AttributeValue, Category, Product


@pytest.mark.django_db
def test_ensure_modulating_skips_on_off_control() -> None:
    """Open/close control does not create Y/U attributes."""
    cat = Category.objects.create(name="Воздушные", slug="vozdushnye")
    product = Product.objects.create(name="DA", slug="da-mod-off", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="DA on/off",
        slug="da-on-off-mod",
        sku_code="DA5MU",
    )
    control = Attribute.objects.create(name="Управление", slug="control", unit="")
    AttributeValue.objects.create(sku=sku, attribute=control, value="Открыто/закрыто")
    assert ensure_modulating_signal_attributes(sku) == 0
    assert not AttributeValue.objects.filter(
        sku=sku,
        attribute__slug=CONTROL_SIGNAL_Y_SLUG,
    ).exists()


@pytest.mark.django_db
def test_ensure_modulating_creates_and_updates_y_u() -> None:
    """Proportional control creates Y/U; second call fixes stale values."""
    cat = Category.objects.create(name="Воздушные", slug="vozdushnye-mod")
    product = Product.objects.create(name="DA", slug="da-mod-on", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="DA mod",
        slug="da-modulating",
        sku_code="DA5FU",
    )
    control = Attribute.objects.create(name="Управление", slug="control", unit="")
    AttributeValue.objects.create(
        sku=sku,
        attribute=control,
        value="Пропорциональное (модулирующее)",
    )
    created = ensure_modulating_signal_attributes(sku)
    assert created == 2
    y = Attribute.objects.get(slug=CONTROL_SIGNAL_Y_SLUG)
    u = Attribute.objects.get(slug=FEEDBACK_SIGNAL_U_SLUG)
    assert y.name == CONTROL_SIGNAL_Y_LABEL
    assert u.name == FEEDBACK_SIGNAL_U_LABEL
    av_y = AttributeValue.objects.get(sku=sku, attribute=y)
    av_u = AttributeValue.objects.get(sku=sku, attribute=u)
    assert av_y.value == CONTROL_SIGNAL_Y_CANON
    assert av_u.value == FEEDBACK_SIGNAL_U_CANON

    av_y.value = "stale"
    av_y.save(update_fields=["value"])
    y.name = "Old Y"
    y.save(update_fields=["name"])
    updated = ensure_modulating_signal_attributes(sku)
    assert updated == 1
    av_y.refresh_from_db()
    y.refresh_from_db()
    assert av_y.value == CONTROL_SIGNAL_Y_CANON
    assert y.name == CONTROL_SIGNAL_Y_LABEL
