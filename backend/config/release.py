"""Hoocon CMS release version (Admin + frontend + /api/health/).

Canonical version lives here; keep ``backend/pyproject.toml`` and
``frontend/package.json`` in sync via :func:`package_version` (tested).

- Beta: ``RELEASE_VERSION`` = ``X.Y.Z``, channel ``beta`` → ``v0.1.0 beta``.
- After GA: ``RELEASE_VERSION`` = ``MAJOR.MINOR`` (MINOR 0…99), channel ``""``
  → display ``v1.0``; packaging SemVer = ``MAJOR.MINOR.0``.

Policy: docs/releases.md.
"""

from __future__ import annotations

import re

# Beta: three-part; after GA: two-part MAJOR.MINOR (see docs/releases.md).
RELEASE_VERSION = "0.1.9"

# Pre-release channel: "beta" | "rc" | "" (stable / GA).
RELEASE_CHANNEL = "beta"

_VERSION_CORE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?$")


def package_version(version: str | None = None) -> str:
    """SemVer ``X.Y.Z`` for pyproject.toml / package.json.

    Args:
        version: Override (default ``RELEASE_VERSION``).

    Returns:
        Three-part version; two-part GA versions get patch ``0``.

    Raises:
        ValueError: If ``version`` is not ``X.Y`` or ``X.Y.Z``.
    """
    raw = (version if version is not None else RELEASE_VERSION).strip()
    match = _VERSION_CORE.fullmatch(raw)
    if match is None:
        msg = f"Invalid RELEASE_VERSION {raw!r}; expected X.Y or X.Y.Z"
        raise ValueError(msg)
    major, minor, patch = match.group(1), match.group(2), match.group(3)
    return f"{major}.{minor}.{patch or '0'}"


def display_version(version: str | None = None, *, channel: str | None = None) -> str:
    """Public version core without channel (two-part after GA).

    Args:
        version: Override (default ``RELEASE_VERSION``).
        channel: Override (default ``RELEASE_CHANNEL``). Empty → GA display.

    Returns:
        ``0.1.0`` in beta; ``1.0`` after GA (drops trailing ``.0`` patch).
    """
    raw = (version if version is not None else RELEASE_VERSION).strip()
    ch = (RELEASE_CHANNEL if channel is None else channel).strip()
    match = _VERSION_CORE.fullmatch(raw)
    if match is None:
        return raw
    major, minor, patch = match.group(1), match.group(2), match.group(3)
    if not ch:
        return f"{major}.{minor}"
    if patch is None:
        return f"{major}.{minor}"
    return f"{major}.{minor}.{patch}"


def release_label(*, with_v: bool = True) -> str:
    """Human-readable release string for Admin / footer / docs.

    Args:
        with_v: Prefix with ``v`` (``v0.1.0 beta`` / ``v1.0``).

    Returns:
        Label such as ``v0.1.0 beta`` or ``v1.0`` when channel is empty.
    """
    prefix = "v" if with_v else ""
    core = f"{prefix}{display_version()}"
    channel = (RELEASE_CHANNEL or "").strip()
    if channel:
        return f"{core} {channel}"
    return core
