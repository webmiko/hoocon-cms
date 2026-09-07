"""Regression: ScrollProgress must not force reflow on every scroll.

Lighthouse flagged a forced reflow coming from the scroll handler reading
``document.documentElement.scrollHeight`` / ``clientHeight``. The handler now
uses a cached scrollable height and only reads cheap ``window.scrollY``.
"""

from __future__ import annotations

from pathlib import Path

TS_PATH = Path(__file__).resolve().parents[2] / "frontend" / "src" / "components" / "ScrollProgress.tsx"


def _effect_body(source: str) -> str:
    """Return the useEffect body (between the first { after useEffect and its matching })."""
    marker = "useEffect(() => {"
    pos = source.find(marker)
    assert pos != -1, f"useEffect not found in {TS_PATH}"
    open_brace = source.find("{", pos)
    depth = 0
    for i, ch in enumerate(source[open_brace:], start=open_brace):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return source[open_brace + 1 : i]
    raise AssertionError("Could not find matching brace for useEffect")


def test_scroll_handler_does_not_read_layout() -> None:
    body = _effect_body(TS_PATH.read_text())
    on_scroll = body[body.find("function onScroll()") :]
    assert "scrollHeight" not in on_scroll, "onScroll must not read scrollHeight"
    assert "clientHeight" not in on_scroll, "onScroll must not read clientHeight"
    assert "window.scrollY" in on_scroll, "onScroll should use window.scrollY"


def test_dims_are_cached_and_updated_only_on_resize() -> None:
    source = TS_PATH.read_text()
    body = _effect_body(source)
    assert "const dims = { scrollable: 0 }" in body, "scrollable height should be cached"
    assert "function updateDims()" in body, "updateDims helper should exist"
    assert 'window.addEventListener("resize"' in body, "dims should update on resize"
    assert 'window.addEventListener("scroll"' in body, "scroll listener should remain"
