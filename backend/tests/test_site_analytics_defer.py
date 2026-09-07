"""Regression: first-party analytics hit must not compete with LCP.

PageSpeed Insights reported the analytics hit in the critical network chain.
``trackSitePageView`` now waits for ``window.load`` before scheduling the hit,
so the request starts after the page has rendered.
"""

from __future__ import annotations

from pathlib import Path

TS_PATH = Path(__file__).resolve().parents[2] / "frontend" / "src" / "utils" / "siteAnalytics.ts"


def test_track_site_page_view_defers_until_load() -> None:
    source = TS_PATH.read_text()
    assert "afterLoad(" in source, "trackSitePageView should wrap scheduling in afterLoad"
    assert 'window.addEventListener("load"' in source, "afterLoad should listen to window.load"
    assert 'document.readyState === "complete"' in source, "afterLoad should fire immediately if already complete"
