"""Tests for curated major-brand analogs (gap products)."""

from __future__ import annotations

import pytest

from catalog.etl.series_copy_major_analogs import (
    analogs_text_for_product,
    apply_major_analogs_enrichment,
    build_damqu_analogs,
    build_hvd_air_analogs,
    build_sa7mu_analogs,
)
from catalog.models import SKU, Category, Product


def test_build_damqu_analogs_major_brands_only() -> None:
    """DAMQU copy lists Belimo/Siemens/… and skips Chinese OEM clones."""
    text = build_damqu_analogs(5)
    assert "DA5MQU24-DS" in text
    assert "Belimo LMQ24A" in text or "Belimo LMQ24A-S" in text
    assert "Siemens" in text
    assert "Honeywell" in text
    for ban in ("Nanotek", "Dastech", "Lufberg", "BVM", "Sputnik"):
        assert ban not in text


def test_build_sa7mu_and_hvd_include_belimo() -> None:
    """Smoke SA7 and HVD air lists include Belimo BEE / LM families."""
    sa = build_sa7mu_analogs()
    assert "SA7MU24-DST" in sa
    assert "Belimo BEE24ST" in sa
    assert "Nanotek" not in sa
    hvd = build_hvd_air_analogs(40, fast=False)
    assert "HVD24-40" in hvd
    assert "Belimo GM24A" in hvd
    assert "Johnson Controls" in hvd


@pytest.mark.django_db
def test_apply_major_analogs_fills_empty_only() -> None:
    """Empty product gets curated text; filled product is skipped without force."""
    cat = Category.objects.create(name="Air", slug="air-major-analog")
    empty = Product.objects.create(
        name="DA5MQU",
        slug="privod-vozdushniy-da5mqu-5nm",
        category=cat,
        analogs_text="",
    )
    SKU.objects.create(
        product=empty,
        sku_code="DA5MQU24-DS",
        slug="da5mqu24-ds-major",
        name="DA5MQU24-DS",
    )
    filled = Product.objects.create(
        name="HVA-5",
        slug="privod-vozdushniy-hva-5nm",
        category=cat,
        analogs_text="Already has Belimo BM24-5-05",
    )
    stats = apply_major_analogs_enrichment(dry_run=False, force=False)
    empty.refresh_from_db()
    filled.refresh_from_db()
    assert empty.pk in [Product.objects.get(slug=s).pk for s in stats["slugs"]] or empty.slug in stats["slugs"]
    assert "Belimo" in (empty.analogs_text or "")
    assert filled.analogs_text == "Already has Belimo BM24-5-05"
    assert analogs_text_for_product(empty)
    sku = SKU.objects.get(sku_code="DA5MQU24-DS")
    assert "DA5MQU24-DS" in (sku.analogs_text or "") or "Belimo" in (sku.analogs_text or "")
