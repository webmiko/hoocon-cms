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


def test_default_cors_includes_local_vite_5174_in_debug() -> None:
    """Pinned dev port 5174 is trusted for CORS/CSRF out of the box in DEBUG."""
    from config.settings import origins_from_env

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("CORS_ALLOWED_ORIGINS", None)
        assert "http://localhost:5174" in origins_from_env("CORS_ALLOWED_ORIGINS", debug=True)
        assert "http://127.0.0.1:5174" in origins_from_env("CORS_ALLOWED_ORIGINS", debug=True)


def test_prod_without_env_trusts_no_localhost_origin() -> None:
    """DEBUG=False without CORS/CSRF env silently trusted localhost — now fails closed."""
    from config.settings import origins_from_env

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("CSRF_TRUSTED_ORIGINS", None)
        assert origins_from_env("CSRF_TRUSTED_ORIGINS", debug=False) == []
    with patch.dict(os.environ, {"CSRF_TRUSTED_ORIGINS": "https://hoocon.ru, https://www.hoocon.ru"}):
        assert origins_from_env("CSRF_TRUSTED_ORIGINS", debug=False) == ["https://hoocon.ru", "https://www.hoocon.ru"]


def test_e2e_server_trusts_its_own_vite_origin() -> None:
    """CI e2e runs with DJANGO_DEBUG=false, so the webserver script must pass its origins."""
    from pathlib import Path

    script = (Path(__file__).resolve().parents[2] / "scripts" / "e2e-webserver.sh").read_text(encoding="utf-8")
    assert 'export CSRF_TRUSTED_ORIGINS="${CSRF_TRUSTED_ORIGINS:-${E2E_ORIGINS}}"' in script
    assert script.index("CSRF_TRUSTED_ORIGINS") < script.index("runserver")


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
