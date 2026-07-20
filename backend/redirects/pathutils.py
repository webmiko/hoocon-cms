"""Path helpers for Redirect: normalize and reject open redirects."""

from __future__ import annotations

from django.core.exceptions import ValidationError


def validate_internal_path(value: str) -> None:
    """Reject open redirects: only absolute site paths without scheme/host.

    Args:
        value: Candidate path (e.g. ``/catalog``).

    Raises:
        ValidationError: If the value is empty, relative, protocol-relative,
            or contains a URL scheme / backslash.
    """
    if not value or not value.startswith("/") or value.startswith("//"):
        raise ValidationError("Path must start with a single '/'.")
    if "://" in value or "\\" in value or "\n" in value or "\r" in value:
        raise ValidationError("External URLs and control characters are not allowed.")


def normalize_path(path: str) -> str:
    """Normalize a request or stored path for lookup (no trailing slash).

    Args:
        path: Raw path, optionally without a leading slash.

    Returns:
        Path starting with ``/`` and without a trailing slash (except ``/``).
    """
    cleaned = path.strip() or "/"
    if not cleaned.startswith("/"):
        cleaned = f"/{cleaned}"
    if len(cleaned) > 1 and cleaned.endswith("/"):
        cleaned = cleaned.rstrip("/")
    return cleaned
