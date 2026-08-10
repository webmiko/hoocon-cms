"""Tests for canonical warranty copy helpers."""

from __future__ import annotations

from config.warranty import (
    WARRANTY_BULLET,
    WARRANTY_COMPANY_LI,
    WARRANTY_DURATION,
    WARRANTY_LINE,
    WARRANTY_MONTHS,
    warranty_duration,
    warranty_months_word,
)


def test_warranty_months_default_is_24() -> None:
    """RF product warranty length is 24 months."""
    assert WARRANTY_MONTHS == 24
    assert WARRANTY_DURATION == "24 месяца"
    assert WARRANTY_LINE == "Гарантия: 24 месяца."
    assert WARRANTY_BULLET == "– Гарантия: 24 месяца."
    assert "24 месяца" in WARRANTY_COMPANY_LI
    assert "3 года" not in WARRANTY_COMPANY_LI


def test_warranty_months_word_pluralization() -> None:
    """Russian месяц forms follow number grammar."""
    assert warranty_months_word(1) == "месяц"
    assert warranty_months_word(2) == "месяца"
    assert warranty_months_word(3) == "месяца"
    assert warranty_months_word(4) == "месяца"
    assert warranty_months_word(5) == "месяцев"
    assert warranty_months_word(11) == "месяцев"
    assert warranty_months_word(12) == "месяцев"
    assert warranty_months_word(21) == "месяц"
    assert warranty_months_word(22) == "месяца"
    assert warranty_months_word(24) == "месяца"
    assert warranty_months_word(36) == "месяцев"
    assert warranty_duration(12) == "12 месяцев"
