"""Tests for 3-way 8100 flow-scheme gallery attach."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.core.files.base import ContentFile

from catalog.etl.ball_valve_flow_scheme import (
    apply_ball_valve_flow_scheme,
    is_8100_three_way_edition,
)
from catalog.etl.generate_ball_valve_flow_scheme import write_pack
from catalog.models import SKU, Category, Product, ProductImage


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("8100-bv315a", True),
        ("8100-BV350B", True),
        ("8100-bv215a", False),
        ("8100-bv315", False),
        ("BR-M", False),
    ],
)
def test_is_8100_three_way_edition(code: str, expected: bool) -> None:
    assert is_8100_three_way_edition(code) is expected


@pytest.mark.django_db
def test_apply_flow_scheme_only_three_way(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Flow WebP lands on BV3xx only; 2-way untouched; hero kept."""
    from catalog.etl import ball_valve_flow_scheme as mod

    pack = tmp_path / "flow"
    write_pack(pack_dir=pack)
    monkeypatch.setattr(mod, "_PACK_DIR", pack)

    cat = Category.objects.create(name="Краны", slug="sharovye-flow")
    two = Product.objects.create(category=cat, name="BV215", slug="8100-bv215")
    three = Product.objects.create(category=cat, name="BV315", slug="8100-bv315")
    sku2 = SKU.objects.create(
        product=two,
        name="BV215A",
        slug="8100-bv215a",
        sku_code="8100-bv215a",
        is_published=True,
    )
    sku3 = SKU.objects.create(
        product=three,
        name="BV315A",
        slug="8100-bv315a",
        sku_code="8100-bv315a",
        is_published=True,
    )
    hero_bytes = (pack / "flow-3way.webp").read_bytes()
    hero = ProductImage(
        sku=sku3,
        alt="hero",
        source_url="https://hoocon.ru/.local-assets/media-webp/3way-brass-dn15-product.webp",
        sort_order=0,
        is_published=True,
    )
    hero.image.save("hero.webp", ContentFile(hero_bytes), save=True)

    summary = apply_ball_valve_flow_scheme(dry_run=False)
    assert summary["created"] == 1
    assert summary["updated"] == 0
    assert not ProductImage.objects.filter(
        sku=sku2,
        source_url="https://hoocon.ru/.local-assets/flow-scheme/flow-3way.webp",
    ).exists()
    flow = ProductImage.objects.get(
        sku=sku3,
        source_url="https://hoocon.ru/.local-assets/flow-scheme/flow-3way.webp",
    )
    assert flow.is_published
    assert flow.sort_order == 25
    assert "направления потока" in flow.alt.casefold()
    hero.refresh_from_db()
    assert hero.is_published and hero.sort_order == 0
