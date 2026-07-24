"""Tests for series specification category mapping."""

from __future__ import annotations

from catalog.series_categories import (
    classify_series_category,
    resolve_alias,
    spec_categories,
    spec_order_case,
)


def test_spec_categories_match_article_families() -> None:
    """Six actuator families from the series table, plus ball valves and kits."""
    slugs = [c.slug for c in spec_categories()]
    assert slugs == [
        "elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata",
        "elektroprivody-uskorennye-bez-pruzhinnogo-vozvrata",
        "elektronnye-otkazoustoychivye-vozdushnye-privody",
        "elektroprivody-s-pruzhinnym-vozvratom",
        "elektroprivody-protivopozharnye-i-dymovye",
        "elektroprivody-dlya-klapanov-dymoudaleniya",
        "sharovye-krany",
        "komplekty",
    ]


def test_classify_series_by_sku_codes() -> None:
    """SKU masks drive the specification bucket."""
    assert classify_series_category("x", ["DA3FU230-D"]) == "elektroprivody-s-pruzhinnym-vozvratom"
    assert classify_series_category("x", ["DA8MQU24-A"]) == "elektroprivody-uskorennye-bez-pruzhinnogo-vozvrata"
    assert (
        classify_series_category(
            "privod-vozdushniy-bez-pruzhini-damu-16nm",
            ["DA16MU24-D"],
        )
        == "elektroprivody-vozdushnye-bez-pruzhinnogo-vozvrata"
    )
    assert classify_series_category("x", ["SA5FU24-DS"]) == "elektroprivody-protivopozharnye-i-dymovye"
    assert classify_series_category("x", ["SA10MU230-DST"]) == "elektroprivody-dlya-klapanov-dymoudaleniya"
    assert classify_series_category("sharovoy-kran-bv215", ["8100-bv215a"]) == "sharovye-krany"
    assert classify_series_category("sharovoy-kran-h8101-bv215a", ["H8101-BV215A-24A"]) == "komplekty"
    assert classify_series_category("h8101", ["H8101-BV215A-24A"]) == "komplekty"
    assert classify_series_category("sharovoy-kran-h8205-lav232", ["H8205-LAV232-24A"]) == "komplekty"


def test_resolve_legacy_tilda_aliases() -> None:
    """Old Tilda subcategory slugs map onto the series table."""
    assert resolve_alias("elektroprivod-vozdushniy-s-vozvratnoy-pruzhinoy") == "elektroprivody-s-pruzhinnym-vozvratom"
    assert resolve_alias("sharoviy-kran-3-hodovoy") == "sharovye-krany"


def test_spec_order_case_includes_tilda_aliases() -> None:
    """Legacy and canonical slugs share the same sidebar sort index."""
    from django.db.models import Case

    expr = spec_order_case()
    assert isinstance(expr, Case)
    # When clauses: one per canonical + each alias that maps to a known spec.
    assert len(expr.cases) >= len(spec_categories()) + 3
