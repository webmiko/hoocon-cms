"""Hoocon CMS release version (Admin + frontend + /api/health/).

Canonical version lives here; keep ``backend/pyproject.toml`` and
``frontend/package.json`` in sync via :func:`package_version` (tested).

- Beta: ``RELEASE_VERSION`` = ``X.Y.Z``, channel ``beta`` → ``v0.1.0 beta``.
- After GA: ``RELEASE_VERSION`` = ``MAJOR.MINOR.PATCH``, channel ``""``.
  PATCH is the internal build counter (feature on ``develop``); public
  display is ``vMAJOR.MINOR`` and changes only with a prod release (MINOR).

Policy: _docs/releases.md. Bump: ``scripts/bump-release.py``.
"""

from __future__ import annotations

import re
from typing import Literal

# Beta: three-part + channel; after GA: MAJOR.MINOR.PATCH (see _docs/releases.md).
RELEASE_VERSION = "3.2.0"

# Pre-release channel: "beta" | "rc" | "" (stable / GA).
RELEASE_CHANNEL = ""

MINOR_MAX = 99

_VERSION_CORE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?$")

BumpPart = Literal["patch", "minor", "major"]


def _parse(raw: str) -> tuple[int, int, int]:
    match = _VERSION_CORE.fullmatch(raw.strip())
    if match is None:
        msg = f"Invalid RELEASE_VERSION {raw!r}; expected X.Y or X.Y.Z"
        raise ValueError(msg)
    return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)


def package_version(version: str | None = None) -> str:
    """SemVer ``X.Y.Z`` for pyproject.toml / package.json.

    Args:
        version: Override (default ``RELEASE_VERSION``).

    Returns:
        Three-part version; two-part versions get patch ``0``.

    Raises:
        ValueError: If ``version`` is not ``X.Y`` or ``X.Y.Z``.
    """
    major, minor, patch = _parse(version if version is not None else RELEASE_VERSION)
    return f"{major}.{minor}.{patch}"


def bump_version(version: str, part: BumpPart) -> str:
    """Next ``MAJOR.MINOR.PATCH`` after GA.

    ``patch`` — internal build (prod label unchanged); ``minor`` — prod
    release (patch reset to 0); ``major`` — only on explicit command.

    Raises:
        ValueError: Malformed version, unknown part, or MINOR past ``MINOR_MAX``.
    """
    major, minor, patch = _parse(version)
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    if part == "minor":
        if minor + 1 > MINOR_MAX:
            msg = f"MINOR would exceed {MINOR_MAX}; bump MAJOR explicitly"
            raise ValueError(msg)
        return f"{major}.{minor + 1}.0"
    if part == "major":
        return f"{major + 1}.0.0"
    msg = f"Unknown bump part {part!r}"
    raise ValueError(msg)


def display_version(version: str | None = None, *, channel: str | None = None) -> str:
    """Public version core without channel (two-part after GA).

    Args:
        version: Override (default ``RELEASE_VERSION``).
        channel: Override (default ``RELEASE_CHANNEL``). Empty → GA display.

    Returns:
        ``0.1.0`` in beta; ``1.2`` after GA (internal PATCH hidden).
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


def unfold_environment_badge() -> tuple[str, str]:
    """Unfold ``UNFOLD['ENVIRONMENT']``: ``(label, type)`` for ``label.html``.

    A plain string breaks the template: ``environment.0`` on ``"v2.0"`` is only
    the first character.
    """
    return (release_label(), "")


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
