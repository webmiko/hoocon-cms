"""Release version sync (Admin + frontend + health)."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from config.release import (
    RELEASE_CHANNEL,
    RELEASE_VERSION,
    bump_version,
    display_version,
    package_version,
    release_label,
    unfold_environment_badge,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VERSION_CORE = re.compile(r"^\d+\.\d+(?:\.\d+)?$")


def test_release_label_ga_format() -> None:
    """Internal ``MAJOR.MINOR.PATCH``; prod label is ``vMAJOR.MINOR`` only."""
    assert RELEASE_CHANNEL == ""
    assert re.fullmatch(r"\d+\.\d+\.\d+", RELEASE_VERSION), RELEASE_VERSION
    major, minor, _patch = RELEASE_VERSION.split(".")
    assert release_label() == f"v{major}.{minor}"
    assert release_label(with_v=False) == f"{major}.{minor}"


def test_patch_bump_keeps_prod_label_minor_bump_changes_it() -> None:
    """PATCH is internal (label unchanged); MINOR is the prod release."""
    assert bump_version("1.1.0", "patch") == "1.1.1"
    assert bump_version("1.1.1", "minor") == "1.2.0"
    assert bump_version("1.17.4", "major") == "2.0.0"
    assert bump_version("3.2", "patch") == "3.2.1"
    assert display_version("1.1.1", channel="") == display_version("1.1.0", channel="")
    assert display_version("1.2.0", channel="") == "1.2"


def test_bump_version_rejects_minor_past_limit_and_unknown_part() -> None:
    """MINOR stops at 99 (MAJOR only on explicit command)."""
    with pytest.raises(ValueError, match="MINOR would exceed"):
        bump_version("1.99.3", "minor")
    with pytest.raises(ValueError, match="Unknown bump part"):
        bump_version("1.2.0", "build")  # type: ignore[arg-type]


def test_bump_release_script_check_passes_on_repo() -> None:
    """``scripts/bump-release.py --check``: all four version files agree."""
    script = _REPO_ROOT / "scripts" / "bump-release.py"
    result = subprocess.run(
        [sys.executable, str(script), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_merge_release_pr_requires_new_prod_minor() -> None:
    """Prod merge refuses when develop still has prod's ``MAJOR.MINOR``."""
    script = (_REPO_ROOT / "scripts" / "merge-release-pr.sh").read_text(encoding="utf-8")
    guard = script.index('"${prod_public}" == "${next_public}"')
    assert guard < script.index("gh pr merge")
    assert "RELEASE_ALLOW_SAME_MINOR" in script
    assert "bump-release.py minor" in script


def test_unfold_environment_badge_is_full_label_tuple() -> None:
    """Unfold ENVIRONMENT must be (label, type) — not a bare string."""
    badge = unfold_environment_badge()
    assert badge == (release_label(), "")
    assert len(badge[0]) > 1


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
