"""Regression: SupportWidget must not measure/scroll the message list while closed.

Setting ``scrollTop`` on a hidden list still forces a layout. The effect that
auto-scrolls to the bottom is now guarded by the ``open`` flag.
"""

from __future__ import annotations

from pathlib import Path

TS_PATH = Path(__file__).resolve().parents[2] / "frontend" / "src" / "components" / "SupportWidget.tsx"


def test_scroll_to_bottom_is_guarded_by_open() -> None:
    source = TS_PATH.read_text()
    scroll_marker = "el.scrollTop = el.scrollHeight;"
    scroll_pos = source.find(scroll_marker)
    assert scroll_pos != -1, f"scroll-to-bottom assignment not found in {TS_PATH}"

    # Find the useEffect block that encloses the scroll assignment.
    effect_start = source.rfind("useEffect(() => {", 0, scroll_pos)
    assert effect_start != -1, "scroll assignment is not inside a useEffect"
    open_brace = source.find("{", effect_start)
    depth = 0
    for i, ch in enumerate(source[open_brace:], start=open_brace):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                effect_body = source[open_brace + 1 : i]
                break
    else:
        raise AssertionError("Could not find matching brace for useEffect")

    assert "if (!el || !open) return;" in effect_body, "scroll effect must be guarded by open"
