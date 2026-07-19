"""Pytest configuration and fixtures for Hoocon CMS backend tests.

Shared fixtures across all test modules. Throttle cache is cleared between
tests so that rate-limit state from one test does not leak into another
(LocMemCache persists across the test session by default).
"""

from __future__ import annotations

import pytest
from django.core.cache import cache


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
