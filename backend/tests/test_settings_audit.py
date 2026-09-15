"""Settings helpers from audit P0 — PostgreSQL-only database config."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from django.core.exceptions import ImproperlyConfigured


def test_env_bool_default_false() -> None:
    """_env_bool returns default when env var is missing."""
    from config.settings import _env_bool

    assert _env_bool("HOCON_MISSING_DEBUG_FLAG_XYZ", default=False) is False
    assert _env_bool("HOCON_MISSING_DEBUG_FLAG_XYZ", default=True) is True


def test_resolve_default_database_requires_db_name() -> None:
    """Missing DB_NAME must fail fast — no SQLite fallback."""
    from config.settings import resolve_default_database

    with patch.dict(os.environ, {"DB_NAME": ""}, clear=False):
        with pytest.raises(ImproperlyConfigured, match="DB_NAME is required"):
            resolve_default_database()


def test_default_cors_includes_local_vite_5174() -> None:
    """Pinned dev port 5174 is trusted for CORS/CSRF out of the box."""
    from config import settings

    assert "http://localhost:5174" in settings.CORS_ALLOWED_ORIGINS
    assert "http://127.0.0.1:5174" in settings.CSRF_TRUSTED_ORIGINS


def test_drf_public_api_uses_session_auth_only() -> None:
    """Public API must not enable HTTP Basic on every endpoint."""
    from config import settings

    classes = settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"]
    assert classes == ["rest_framework.authentication.SessionAuthentication"]


def test_resolve_default_database_postgres() -> None:
    """Configured DB_NAME maps to django.db.backends.postgresql."""
    from config.settings import resolve_default_database

    with patch.dict(
        os.environ,
        {
            "DB_NAME": "hoocon_test",
            "DB_USER": "hoocon",
            "DB_PASSWORD": "secret",
            "DB_HOST": "127.0.0.1",
            "DB_PORT": "5432",
        },
        clear=False,
    ):
        cfg = resolve_default_database()
    assert cfg["default"]["ENGINE"] == "django.db.backends.postgresql"
    assert cfg["default"]["NAME"] == "hoocon_test"
