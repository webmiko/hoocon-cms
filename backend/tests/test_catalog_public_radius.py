"""Regression: public catalog radii stay on the proportional token scale.

Symptom we kept re-fixing: search / filter chips / dock CTAs mixed
``999px`` pills with hardcoded ``4px``/``1.25rem``, so equal-height controls
looked differently rounded. Loaded surfaces are the CSS modules Vite ships
for CatalogPage + CompareTray + CompareToggle (+ tokens.css).
"""

from __future__ import annotations

import re
from pathlib import Path

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"
_TOKENS = _FRONTEND / "styles" / "tokens.css"
_CATALOG = _FRONTEND / "pages" / "CatalogPage.module.css"
_TRAY = _FRONTEND / "components" / "CompareTray.module.css"
_TOGGLE = _FRONTEND / "components" / "CompareToggle.module.css"

# Full-pill radii are only OK for circular count badges / avatars — not controls.
_PILL = re.compile(r"border-radius:\s*999px\b")


def _rule_bodies(css: str, selector: str) -> list[str]:
    """Return every ``{...}`` body whose selector list contains ``selector``.

    Skips class-name prefixes (``.chat`` ≠ ``.chatIcon``) and pseudo
    continuations (``.cardNew`` ≠ ``.cardNew::before``).
    """
    bodies: list[str] = []
    start = 0
    while True:
        pos = css.find(selector, start)
        if pos == -1:
            break
        end = pos + len(selector)
        if end < len(css) and (css[end].isalnum() or css[end] in "-_:"):
            start = end
            continue
        open_at = css.find("{", end)
        if open_at == -1:
            break
        depth = 0
        close_at = -1
        for i, ch in enumerate(css[open_at:], start=open_at):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    close_at = i
                    break
        if close_at == -1:
            raise AssertionError(f"Unclosed CSS rule for {selector!r}")
        bodies.append(css[open_at + 1 : close_at])
        start = close_at + 1
    if not bodies:
        raise AssertionError(f"Selector {selector!r} not found")
    return bodies


def _border_radius(css: str, selector: str) -> str:
    """Extract the first ``border-radius`` declared for ``selector``."""
    for body in _rule_bodies(css, selector):
        match = re.search(r"border-radius:\s*([^;]+);", body)
        if match is not None:
            return match.group(1).strip()
    raise AssertionError(f"No border-radius in any rule for {selector!r}")


def _assert_not_pill(css: str, selector: str) -> None:
    for body in _rule_bodies(css, selector):
        if "border-radius:" not in body:
            continue
        assert not _PILL.search(body), f"{selector!r} must not use pill 999px:\n{body}"


def test_radius_token_scale_is_concentric() -> None:
    """Token ladder stays stepped so larger surfaces get larger radii."""
    css = _TOKENS.read_text(encoding="utf-8")
    assert "--radius-xs: 6px;" in css
    assert "--radius-sm: 10px;" in css
    assert "--radius-md: 14px;" in css
    assert "--radius-lg: 18px;" in css
    assert "--radius-xl: 24px;" in css
    assert "--radius: var(--radius-md);" in css


def test_catalog_search_and_filter_controls_share_sm_radius() -> None:
    """Search bar and filter rows (~40px) use radius-sm — not full pills."""
    css = _CATALOG.read_text(encoding="utf-8")
    assert _border_radius(css, ".searchForm") == "var(--radius-sm)"
    assert _border_radius(css, ".filterQuick .optionRowActive") == "var(--radius-sm)"
    assert _border_radius(css, ".categoryNav .optionRowActive") == "var(--radius-sm)"
    assert _border_radius(css, ".optionRowActive") == "var(--radius-sm)"
    for selector in (
        ".searchForm",
        ".filterQuick .optionRowActive",
        ".categoryNav .optionRowActive",
        ".optionRowActive",
    ):
        _assert_not_pill(css, selector)


def test_catalog_mobile_filters_shell_uses_md_not_lg() -> None:
    """Closed filter bar is ~search height → md; cards keep lg separately."""
    css = _CATALOG.read_text(encoding="utf-8")
    media_at = css.index("@media (max-width: 960px)")
    mobile_block = css[media_at:]
    assert _border_radius(mobile_block, ".filtersMobile") == "var(--radius-md)"
    _assert_not_pill(mobile_block, ".filtersMobile")


def test_catalog_card_chips_and_cta_use_token_radii_not_pills() -> None:
    """Stock/new chips and card CTA must stay soft-rect, not 999px pills."""
    css = _CATALOG.read_text(encoding="utf-8")
    assert _border_radius(css, ".cardStock") == "var(--radius-xs)"
    assert _border_radius(css, ".cardNew") == "var(--radius-xs)"
    assert _border_radius(css, ".cardCta") == "var(--radius-sm)"
    for selector in (".cardStock", ".cardNew", ".cardCta"):
        _assert_not_pill(css, selector)


def test_catalog_count_badge_may_stay_circular() -> None:
    """Near-square filter count badge is the intentional 999px exception."""
    css = _CATALOG.read_text(encoding="utf-8")
    assert _border_radius(css, ".filtersMobileBadge") == "999px"


def test_compare_tray_dock_ctas_use_md_thumbs_use_xs() -> None:
    """Dock buttons (~44px) → md; 28px thumbs → xs (no hardcoded 4/5px)."""
    css = _TRAY.read_text(encoding="utf-8")
    for selector in (".chat", ".summary", ".secondary", ".compare"):
        assert _border_radius(css, selector) == "var(--radius-md)", selector
        _assert_not_pill(css, selector)
    for selector in (".panelThumb", ".stackThumb", ".remove"):
        value = _border_radius(css, selector)
        assert value == "var(--radius-xs)", f"{selector} → {value}"
    assert "border-radius: 4px" not in css
    assert "border-radius: 5px" not in css


def test_compare_toggle_overlay_uses_sm_not_pill() -> None:
    """Card «КП» overlay control matches catalog control radius (sm)."""
    css = _TOGGLE.read_text(encoding="utf-8")
    assert _border_radius(css, ".checkboxWrap") == "var(--radius-sm)"
    assert _border_radius(css, ".checkboxUi") == "var(--radius-xs)"
    assert _border_radius(css, ".buttonActive") == "var(--radius-sm)"
    _assert_not_pill(css, ".checkboxWrap")
    assert "border-radius: 4px" not in css
