"""Tests for SKU-scoped install guide registry."""

from __future__ import annotations

from catalog.etl.sku_instructions import instructions_for_sku


def test_instructions_for_sku_covers_main_actuator_series() -> None:
    """Each major series gets a builder with edition-specific voltage."""
    cases = {
        "DA4MU24-D": ("DA4MU", "AC/DC 24 В", "100…240"),
        "DA5FU230-DS": ("DA5FU", "100…240", "AC/DC 24 В"),
        "SA5FU24-DST": ("SA5FU", "AC/DC 24 В", "100…240"),
        "SA10MU230-DS": ("SA10MU", "100…240", "AC/DC 24 В"),
        "HVD24ST-3F": ("HVD-3F", "AC/DC 24 В", "100…240"),
        "H8205-LAV232-24A": ("H8205", "AC/DC 24 В", "100…240"),
    }
    for code, (series, keep, drop) in cases.items():
        text = instructions_for_sku(code)
        assert series in text, code
        assert keep in text, code
        assert drop not in text, code


def test_instructions_for_sku_filters_stored_fallback() -> None:
    """Unknown series still scopes stored product instructions by voltage."""
    stored = """
Инструкция линейки

– Исполнения 24 В: AC/DC 24 В.
– Исполнения 230 В: AC 100…240 В.
– Сечение провода: 0,5 мм².
"""
    out = instructions_for_sku("BV215-24", stored_text=stored)
    assert "Исполнения 24 В" in out
    assert "Исполнения 230 В" not in out


def test_safu_thermal_chapter_only_on_dst() -> None:
    dst = instructions_for_sku("SA5FU230-DST")
    ds = instructions_for_sku("SA5FU230-DS")
    assert "Термодатчик SAF72" in dst
    assert "Термодатчик SAF72" not in ds
