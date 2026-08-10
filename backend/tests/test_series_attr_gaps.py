"""Tests for DA/SA/HV attribute gap audit helpers."""

from __future__ import annotations

import pytest
from django.core.management import call_command

from catalog.etl.series_attr_gaps import (
    build_series_attr_gap_report,
    series_base_model,
    series_family,
)
from catalog.models import SKU, Attribute, AttributeValue, Category, Product


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("DA24MU230-AS", "DAMU"),
        ("da3fu230-ds", "DAFU"),
        ("DA8MQU24-A", "DAMQU"),
        ("SA10MU24-DST", "SAMU"),
        ("sa5fu230-ds", "SAFU"),
        ("HVA24S-5Q", "HVA"),
        ("HVD230S-40Q", "HVD"),
        ("BV215-…", None),
    ],
)
def test_series_family(code: str, expected: str | None) -> None:
    assert series_family(code) == expected


@pytest.mark.parametrize(
    ("code", "family", "expected"),
    [
        ("DA24MU230-AS", "DAMU", "DA24MU"),
        ("da3fu230-ds", "DAFU", "DA3FU"),
        ("HVA24S-5Q", "HVA", "HVA-5Q"),
        ("HVA230-5", "HVA", "HVA-5"),
        ("HVD24S-10", "HVD", "HVD-10"),
        ("HVD230ST-3F", "HVD", "HVD-3F"),
    ],
)
def test_series_base_model(code: str, family: str, expected: str) -> None:
    assert series_base_model(code, family) == expected


@pytest.mark.django_db
def test_build_series_attr_gap_report_lists_model_gaps() -> None:
    cat = Category.objects.create(name="Воздух", slug="vozdushnie-gap-audit")
    product = Product.objects.create(name="DAMU", slug="damu-gap-audit", category=cat)
    sku = SKU.objects.create(
        product=product,
        name="DA2",
        slug="da2-gap-audit",
        sku_code="DA2MU24-D",
        is_published=True,
    )
    weight = Attribute.objects.create(name="Масса", slug="weight")
    AttributeValue.objects.create(sku=sku, attribute=weight, value="< 0,5 кг")
    # cable / wire absent on purpose

    report = build_series_attr_gap_report(
        attr_slugs=("weight", "cable-length", "wire-cross-section"),
    )
    by_model = {gap.model: gap for gap in report.model_gaps if gap.family == "DAMU"}
    assert "DA2MU" in by_model
    assert by_model["DA2MU"].missing_slugs == ("cable-length", "wire-cross-section")


@pytest.mark.django_db
def test_audit_series_attr_gaps_command(capsys) -> None:
    call_command("audit_series_attr_gaps", "--slugs", "weight")
    out = capsys.readouterr().out
    assert "Family coverage" in out
    assert "Models with gaps" in out
