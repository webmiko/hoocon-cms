"""Coverage tests for Admin template context processors."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from django.test import RequestFactory, override_settings

from config.context_processors import (
    new_leads_sticker,
    release_info,
    static_version,
)


@override_settings(DEBUG=True, BUILD_SHA="")
def test_static_version_uses_mtime_in_debug() -> None:
    """Without BUILD_SHA, DEBUG uses max mtime of theme CSS/JS when present."""
    base = Path(__file__).resolve().parents[1] / "static/admin"
    css = base / "css/hoocon-unfold-extras.css"
    assert css.is_file()
    ctx = static_version(RequestFactory().get("/"))
    assert ctx["STATIC_VERSION"].isdigit()
    assert int(ctx["STATIC_VERSION"]) == int(css.stat().st_mtime) or int(
        ctx["STATIC_VERSION"],
    ) >= int(css.stat().st_mtime)


@override_settings(DEBUG=False, BUILD_SHA="")
def test_static_version_falls_back_to_dev() -> None:
    """Non-DEBUG without BUILD_SHA → ``dev``."""
    ctx = static_version(RequestFactory().get("/"))
    assert ctx["STATIC_VERSION"] == "dev"


@override_settings(BUILD_SHA="abc1234")
def test_static_version_prefers_build_sha() -> None:
    """BUILD_SHA always wins."""
    ctx = static_version(RequestFactory().get("/"))
    assert ctx["STATIC_VERSION"] == "abc1234"


def test_release_info_exposes_label() -> None:
    """RELEASE_LABEL comes from config.release."""
    ctx = release_info(RequestFactory().get("/"))
    assert "RELEASE_LABEL" in ctx
    assert ctx["RELEASE_LABEL"].startswith("v")


@pytest.mark.django_db
def test_new_leads_sticker_empty_for_anon() -> None:
    """Anonymous request gets zero count and empty URLs."""
    request = RequestFactory().get("/admin/")
    request.user = MagicMock(is_authenticated=False)
    ctx = new_leads_sticker(request)
    assert ctx["HOOCON_NEW_LEADS_COUNT"] == 0
    assert ctx["HOOCON_NEW_LEADS_URL"] == ""
