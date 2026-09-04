"""Release version sync (Admin + frontend + health)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from config.release import (
    RELEASE_CHANNEL,
    RELEASE_VERSION,
    display_version,
    package_version,
    release_label,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VERSION_CORE = re.compile(r"^\d+\.\d+(?:\.\d+)?$")


def test_release_label_ga_format() -> None:
    """Display string is ``vMAJOR.MINOR`` / ``MAJOR.MINOR`` after GA."""
    assert RELEASE_CHANNEL == ""
    assert RELEASE_VERSION == "1.4"
    assert _VERSION_CORE.match(RELEASE_VERSION)
    assert release_label() == f"v{display_version()}"
    assert release_label(with_v=False) == display_version()


def test_package_version_pads_two_part() -> None:
    """After GA, packaging SemVer gets patch ``0``."""
    assert package_version("1.0") == "1.0.0"
    assert package_version("1.99") == "1.99.0"
    assert package_version("0.1.0") == "0.1.0"


def test_display_version_drops_patch_after_ga() -> None:
    """Stable channel shows two-part ``MAJOR.MINOR``."""
    assert display_version("1.0", channel="") == "1.0"
    assert display_version("1.0.0", channel="") == "1.0"
    assert display_version("0.1.0", channel="beta") == "0.1.0"


def test_package_version_rejects_invalid() -> None:
    """Malformed version raises ValueError."""
    with pytest.raises(ValueError, match="Invalid RELEASE_VERSION"):
        package_version("not-a-version")


def test_display_version_edge_cases() -> None:
    """Invalid raw passthrough; two-part with channel; GA label without channel."""
    assert display_version("weird", channel="beta") == "weird"
    assert display_version("1.2", channel="beta") == "1.2"
    import config.release as release_mod

    previous = release_mod.RELEASE_CHANNEL
    try:
        release_mod.RELEASE_CHANNEL = ""
        assert release_label() == f"v{display_version()}"
        assert release_label(with_v=False) == display_version()
    finally:
        release_mod.RELEASE_CHANNEL = previous


def test_pyproject_and_package_json_match_release_module() -> None:
    """pyproject.toml and frontend/package.json stay in sync with release.py."""
    pyproject = (_REPO_ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    package = (_REPO_ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
    frontend_ts = (_REPO_ROOT / "frontend" / "src" / "release.ts").read_text(
        encoding="utf-8",
    )
    pkg = package_version()
    assert f'version = "{pkg}"' in pyproject
    assert f'"version": "{pkg}"' in package
    assert f'RELEASE_VERSION = "{RELEASE_VERSION}"' in frontend_ts
    assert f'RELEASE_CHANNEL = "{RELEASE_CHANNEL}"' in frontend_ts


@pytest.mark.django_db
def test_health_exposes_version_and_channel(client) -> None:
    """GET /api/health/ returns version + channel for smoke probes."""
    body = client.get("/api/health/").json()
    assert body["version"] == RELEASE_VERSION
    assert body["channel"] == RELEASE_CHANNEL
