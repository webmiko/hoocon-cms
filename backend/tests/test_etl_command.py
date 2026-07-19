"""Tests for the etl_hoocon management command (TDD: red → green → refactor).

End-to-end: JSON fixture → command → catalog rows + quarantine CSV.
Spec: docs/data-quality-etl.md §6 — scripts/etl_hoocon_data.py orchestration.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command

FIXTURE = Path(__file__).parent / "fixtures" / "etl_catalog_sample.json"


def _run_command(tmp_path: Path, source: Path | None = None) -> tuple[str, str]:
    """Run etl_hoocon and return (stdout, stderr)."""
    src = source or FIXTURE
    quarantine = tmp_path / "quarantine.csv"
    out = StringIO()
    err = StringIO()
    call_command(
        "etl_hoocon",
        source=str(src),
        quarantine=str(quarantine),
        stdout=out,
        stderr=err,
    )
    return out.getvalue(), err.getvalue()


@pytest.mark.django_db
def test_command_loads_catalog_from_fixture(tmp_path) -> None:
    """etl_hoocon creates categories, products, SKUs from the sample fixture."""
    from catalog.models import SKU, Category, Product

    _run_command(tmp_path)
    assert Category.objects.count() == 5
    # 2 products with buttonlink (3rd is quarantined — empty buttonlink).
    assert Product.objects.count() == 2
    # 2 editions on product 1 + 1 edition on product 2 = 3 SKUs.
    assert SKU.objects.count() == 3


@pytest.mark.django_db
def test_command_writes_quarantine_csv(tmp_path) -> None:
    """Products with empty buttonlink are written to quarantine CSV."""
    quarantine = tmp_path / "quarantine.csv"
    _run_command(tmp_path)
    assert quarantine.exists()
    content = quarantine.read_text(encoding="utf-8")
    assert "empty slug" in content or "invalid slug" in content
    # The BV215 product (uid 128211704224) should be in quarantine.
    assert "BV215" in content or "128211704224" in content


@pytest.mark.django_db
def test_command_is_idempotent(tmp_path) -> None:
    """Running the command twice does not duplicate rows."""
    from catalog.models import SKU, Category, Product

    _run_command(tmp_path)
    counts_after_first = (
        Category.objects.count(),
        Product.objects.count(),
        SKU.objects.count(),
    )
    _run_command(tmp_path)
    counts_after_second = (
        Category.objects.count(),
        Product.objects.count(),
        SKU.objects.count(),
    )
    assert counts_after_first == counts_after_second


@pytest.mark.django_db
def test_command_preserves_canonical_slugs(tmp_path) -> None:
    """Product slugs match the Tilda buttonlink (SEO preservation)."""
    from catalog.models import Product

    _run_command(tmp_path)
    assert Product.objects.filter(slug="privod-protivipozharniy-3nm").exists()
    assert Product.objects.filter(slug="privod-vozdushniy-pruzhina-dafu-3nm").exists()


@pytest.mark.django_db
def test_command_reports_stats_to_stdout(tmp_path) -> None:
    """Command output reports counts of loaded / quarantined rows."""
    out, _err = _run_command(tmp_path)
    assert "categories" in out.lower()
    assert "products" in out.lower()
    assert "quarantine" in out.lower()


@pytest.mark.django_db
def test_command_handles_missing_file(tmp_path) -> None:
    """Missing source file raises CommandError (not silent failure)."""
    from django.core.management import CommandError

    quarantine = tmp_path / "quarantine.csv"
    out = StringIO()
    with pytest.raises(CommandError):
        call_command(
            "etl_hoocon",
            source=str(tmp_path / "nonexistent.json"),
            quarantine=str(quarantine),
            stdout=out,
        )
