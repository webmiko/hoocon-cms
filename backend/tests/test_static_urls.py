"""Tests for versioned static URLs."""

from __future__ import annotations

from django.test import override_settings

from config.static_urls import versioned_static


@override_settings(BUILD_SHA="abc1234")
def test_versioned_static_appends_build_sha() -> None:
    """Deploy SHA busts immutable nginx cache for stable PNG paths."""
    url = versioned_static("admin/img/pwa-admin-192.png")
    assert url.endswith("pwa-admin-192.png?v=abc1234")


@override_settings(DEBUG=False, BUILD_SHA="")
def test_versioned_static_without_token() -> None:
    """Prod without BUILD_SHA keeps plain static path."""
    url = versioned_static("admin/img/pwa-admin-192.png")
    assert url.endswith("pwa-admin-192.png")
    assert "?v=" not in url
