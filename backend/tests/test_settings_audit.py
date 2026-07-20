"""Settings helpers from audit P0-4."""

from __future__ import annotations


def test_env_bool_default_false() -> None:
    """_env_bool returns default when env var is missing."""
    from config.settings import _env_bool

    assert _env_bool("HOCON_MISSING_DEBUG_FLAG_XYZ", default=False) is False
    assert _env_bool("HOCON_MISSING_DEBUG_FLAG_XYZ", default=True) is True
