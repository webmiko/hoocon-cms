"""CSS slicing helpers for layout regression tests (assert properties, not comments)."""

from __future__ import annotations


def css_rule_body(css: str, selector: str) -> str:
    """Return the first ``{...}`` body after ``selector`` (brace-balanced)."""
    start = css.index(selector)
    open_at = css.index("{", start)
    depth = 0
    for i, ch in enumerate(css[open_at:], start=open_at):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return css[open_at + 1 : i]
    raise AssertionError(f"Unclosed CSS rule for {selector!r}")
