"""Pytest configuration and fixtures for Hoocon CMS backend tests.

Shared fixtures across all test modules. Throttle cache is cleared between
tests so that rate-limit state from one test does not leak into another
(LocMemCache persists across the test session by default).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from django.core.cache import cache

_SPA_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "spa_index.html"


@pytest.fixture(autouse=True)
def _clear_throttle_cache() -> None:
    """Clear the cache (incl. DRF throttle counters) before each test.

    DRF's `ScopedRateThrottle` stores hit counts in the Django cache. With
    `LocMemCache` (the default in tests), this state would persist across
    tests in the same session, causing spurious 429s. Clearing before each
    test isolates throttle behaviour.
    """
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _spa_index_html(settings) -> None:
    """Serve the SPA SEO fixture for catch-all spa_index_view in tests."""
    settings.SPA_INDEX_HTML = str(_SPA_FIXTURE)
    settings.SITE_URL = "https://hoocon.ru"
    # Prod-like: hide future published_at (local .env may enable preview).
    settings.CONTENT_SHOW_SCHEDULED = False
    from config.seo.spa_index import clear_index_html_cache

    clear_index_html_cache()
    yield
    clear_index_html_cache()
