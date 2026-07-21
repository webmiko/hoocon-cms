"""Hoocon CMS release version (Admin + frontend + /api/health/).

Canonical SemVer lives here; keep ``backend/pyproject.toml`` and
``frontend/package.json`` in sync (tested). Display: ``v0.0.5 beta``.

Policy: docs/releases.md.
"""

from __future__ import annotations

# SemVer core (no channel suffix). Feature bumps: 0.0.1 … 0.0.9; major: 1.0.0.
RELEASE_VERSION = "0.0.5"

# Pre-release channel: "beta" | "rc" | "" (stable / GA).
RELEASE_CHANNEL = "beta"


def release_label(*, with_v: bool = True) -> str:
    """Human-readable release string for Admin / footer / docs.

    Args:
        with_v: Prefix with ``v`` (``v0.0.5 beta``).

    Returns:
        Label such as ``v0.0.5 beta`` or ``0.0.5`` when channel is empty.
    """
    prefix = "v" if with_v else ""
    core = f"{prefix}{RELEASE_VERSION}"
    channel = (RELEASE_CHANNEL or "").strip()
    if channel:
        return f"{core} {channel}"
    return core
