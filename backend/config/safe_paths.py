"""Same-site path checks for ``next`` / push targets (open-redirect guard)."""

from __future__ import annotations

from django.utils.http import url_has_allowed_host_and_scheme


def is_same_site_path(raw: str) -> bool:
    """True for a relative path that every browser resolves on this host.

    Plain ``startswith("/") and not startswith("//")`` lets ``/\\evil.com``
    through, which browsers read as ``//evil.com``; Django's helper treats
    backslashes, tabs and newlines the way browsers do.
    """
    return raw.startswith("/") and url_has_allowed_host_and_scheme(raw, allowed_hosts=set())


def safe_same_site_path(raw: str | None, *, fallback: str = "/", max_length: int = 500) -> str:
    """``raw`` stripped (and capped) when it is a same-site path, else ``fallback``."""
    candidate = (raw or "").strip()
    if not candidate or not is_same_site_path(candidate):
        return fallback
    return candidate[:max_length]
