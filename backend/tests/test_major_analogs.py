"""Tests for curated major-brand analogs (gap products)."""

from __future__ import annotations

import pytest

from catalog.etl.series_copy_damu_analogs import build_damu_analogs
from catalog.etl.series_copy_major_analogs import (
    analogs_text_for_product,
    apply_major_analogs_enrichment,
    build_damqu_analogs,
    build_hvd_air_analogs,
    build_sa7mu_analogs,
)
from catalog.etl.series_copy_spring_analogs import (
    build_dafu_analogs,
    build_safu_analogs,
    build_samu_analogs,
)
from catalog.models import SKU, Category, Product


def test_build_damu_analogs_belimo_bands() -> None:
    """DAMU 16/32 Нм map to SM/GM — not NM (10 Нм) from old Tilda cards."""
    d16 = build_damu_analogs(16)
    assert "DA16MU24-D" in d16
    assert "Belimo SM24A" in d16
    assert "Belimo NM24A" not in d16
    assert "16 Нм" in d16.splitlines()[0]
    d24 = build_damu_analogs(24)
    assert "DA.MU 16 Нм" not in d24
    assert "24 Нм" in d24.splitlines()[0]
    assert "Belimo SM24A" in d24
    d32 = build_damu_analogs(32)
    assert "Belimo GM24A" in d32
    assert "Belimo SM24A" not in d32
    d2 = build_damu_analogs(2)
    assert "Belimo TMC24A" in d2
    assert "Belimo TMC230A-SR" in d2


def test_build_samu_analogs_no_emf_or_cm() -> None:
    """SA10/15 smoke use BEN/BLE — not invented EMF / CM 2 Нм."""
    sa10 = build_samu_analogs(10)
    assert "Belimo BEN24" in sa10
    assert "EMF" not in sa10
    assert "CM24" not in sa10
    sa15 = build_samu_analogs(15)
    assert "Belimo BLE24" in sa15 or "Belimo BEN24" in sa15
    assert "Belimo BLE24-T" in sa15 or "Belimo BEN24-T" in sa15


def test_build_dafu_safu_belimo_families() -> None:
    """DA15FU → SF (not BF/BX); SA20FU → BF (not BFL-20N)."""
    da15 = build_dafu_analogs(15)
    assert "Belimo SF24A" in da15
    assert "BX24" not in da15
    assert "Belimo BF24" not in da15
    sa20 = build_safu_analogs(20)
    assert "Belimo BF24" in sa20
    assert "BFL24-20" not in sa20
    assert "BLF230-20" not in sa20


def test_build_damqu_analogs_major_brands_only() -> None:
    """DAMQU copy lists Belimo/Siemens/… and skips Chinese OEM clones."""
    text = build_damqu_analogs(5)
    assert "DA5MQU24-DS" in text
    assert "Belimo LMQ24A" in text or "Belimo LMQ24A-S" in text
    assert "Siemens" in text
    assert "Honeywell" in text
    for ban in ("Nanotek", "Dastech", "Lufberg", "BVM", "Sputnik"):
        assert ban not in text


def test_build_damqu_analogs_distinct_belimo_by_nm() -> None:
    """5/8/16/24 Нм map to LMQ / NMQ / SMQ / GMQ — never share one Belimo family."""
    from catalog.etl.series_copy_major_analogs import belimo_fast_family

    assert belimo_fast_family(5) == "LMQ"
    assert belimo_fast_family(8) == "NMQ"
    assert belimo_fast_family(16) == "SMQ"
    assert belimo_fast_family(24) == "GMQ"
    assert "Belimo SMQ24A-SR" in build_damqu_analogs(16)
    assert "Belimo GMQ24A-SR" in build_damqu_analogs(24)
    assert "Belimo NMQ24A-SR" not in build_damqu_analogs(16)
    assert "Belimo NMQ24A-SR" not in build_damqu_analogs(24)


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
