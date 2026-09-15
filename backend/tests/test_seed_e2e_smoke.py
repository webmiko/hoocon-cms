"""Regression: Playwright seed command creates a published PDP target."""

from __future__ import annotations

import pytest
from django.core.management import call_command

from catalog.models import SKU


@pytest.mark.django_db
def test_seed_e2e_smoke_creates_published_sku() -> None:
    call_command("seed_e2e_smoke")
    sku = SKU.objects.get(slug="privod-hva-5nm")
    assert sku.is_published is True
    assert sku.product.category.slug == "vozdushnie"
