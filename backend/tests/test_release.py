"""Release version sync (Admin + frontend + health)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from config.release import RELEASE_CHANNEL, RELEASE_VERSION, release_label

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def test_release_label_beta_format() -> None:
    """Display string matches ``v0.0.N beta`` while channel is beta."""
    assert RELEASE_CHANNEL == "beta"
    assert _SEMVER.match(RELEASE_VERSION)
    assert release_label() == f"v{RELEASE_VERSION} beta"
    assert release_label(with_v=False) == f"{RELEASE_VERSION} beta"


def test_pyproject_and_package_json_match_release_module() -> None:
    """pyproject.toml and frontend/package.json stay in sync with release.py."""
    pyproject = (_REPO_ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    package = (_REPO_ROOT / "frontend" / "package.json").read_text(encoding="utf-8")
    frontend_ts = (_REPO_ROOT / "frontend" / "src" / "release.ts").read_text(
        encoding="utf-8",
    )
    assert f'version = "{RELEASE_VERSION}"' in pyproject
    assert f'"version": "{RELEASE_VERSION}"' in package
    assert f'RELEASE_VERSION = "{RELEASE_VERSION}"' in frontend_ts
    assert f'RELEASE_CHANNEL = "{RELEASE_CHANNEL}"' in frontend_ts


@pytest.mark.django_db
def test_health_exposes_version_and_channel(client) -> None:
    """GET /api/health/ returns SemVer + channel for smoke probes."""
    body = client.get("/api/health/").json()
    assert body["version"] == RELEASE_VERSION
    assert body["channel"] == RELEASE_CHANNEL
