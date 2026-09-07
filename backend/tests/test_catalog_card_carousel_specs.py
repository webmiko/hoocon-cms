"""Regression: carousel SKU card spec rows must not collapse the label.

A long value track with ``max-content`` stole all width from the label,
so narrow carousel cards rendered labels like "Совместимый привод"
vertically, letter by letter.
"""

from __future__ import annotations

from pathlib import Path

CSS_PATH = Path(__file__).resolve().parents[2] / "frontend" / "src" / "pages" / "CatalogPage.module.css"


def _declarations(css: str, selector: str) -> str:
    """Return the declaration block for a simple top-level selector."""
    marker = f"{selector} {{"
    pos = css.find(marker)
    assert pos != -1, f"Selector {selector!r} not found in {CSS_PATH}"
    open_brace = css.find("{", pos)
    close_brace = css.find("}", open_brace)
    assert close_brace != -1
    return css[open_brace + 1 : close_brace]


def test_carousel_spec_row_uses_equal_columns() -> None:
    block = _declarations(CSS_PATH.read_text(), ".card.cardCarousel .cardSpecs li")
    assert "grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);" in block
    assert "align-items: flex-start;" in block


def test_carousel_spec_value_is_left_aligned() -> None:
    block = _declarations(CSS_PATH.read_text(), ".card.cardCarousel .cardSpecValue")
    assert "text-align: left;" in block


def test_carousel_spec_row_is_not_value_max_content() -> None:
    """The root cause: a max-content value column starved the label."""
    block = _declarations(CSS_PATH.read_text(), ".card.cardCarousel .cardSpecs li")
    assert "minmax(0, max-content)" not in block
