"""Regression: support chat header status must not overlap the surface switch.

Inline status + inline button flowed on one row in a narrow panel and collided.
"""

from __future__ import annotations

from pathlib import Path

CSS_PATH = Path(__file__).resolve().parents[2] / "frontend" / "src" / "components" / "SupportWidget.module.css"


def _declarations(css: str, selector: str) -> str:
    marker = f"{selector} {{"
    pos = css.find(marker)
    assert pos != -1, f"Selector {selector!r} not found in {CSS_PATH}"
    open_brace = css.find("{", pos)
    close_brace = css.find("}", open_brace)
    assert close_brace != -1
    return css[open_brace + 1 : close_brace]


def test_header_text_stacks_status_and_surface_switch() -> None:
    block = _declarations(CSS_PATH.read_text(), ".headerText")
    assert "flex-direction: column;" in block


def test_status_is_block_level_not_inline() -> None:
    block = _declarations(CSS_PATH.read_text(), ".status")
    assert "display: flex;" in block
    assert "inline-flex" not in block
